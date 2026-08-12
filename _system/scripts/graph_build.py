#!/usr/bin/env python3
"""Deterministic full rebuild of the workspace graph (_system/graph/graph.db).

The graph is a projection, never a store (first principle #1 of
``_system/graph/README.md``): every node and edge is derived from files already
in the repo, so the database can be deleted and rebuilt at any time and can
never drift from reality. Agents change the repo; the graph follows.

Sources projected (see the spec's node table):

  * Lanes + Commits  -- one ``git log`` call parsed against the lane regexes in
    ``_system/graph/graph_sources.json``.
  * Runs             -- ``_system/data/runs/*.json`` receipts.
  * Wave             -- ``_system/data/contract_backfill_queue.json``.
  * Tickers/Contracts/Components/Facts -- registry + streamed per-ticker
    ``valuation_contract.json`` / ``valuation_fact_ledger.json`` (833 tickers;
    each file is loaded, projected and discarded).
  * Falsifiers       -- component/monitoring prose strings, plus typed specs
    from optional ``{TICKER}/research/falsifier_specs.json`` sidecars.
  * Blockers         -- contract ``evidence.blockers[]`` strings; each becomes
    a Blocker node with a BLOCKS edge to its Contract.
  * Outcomes         -- ``_system/research/falsifier_outcomes.jsonl`` if present.
  * Beliefs          -- MEMORY.md bullets and company-table rows.
  * Proposals        -- ``_system/memory/triage_ledger.json`` decisions plus
    undecided daily-log ``[PROPOSED]`` bullets (matched by the triage builder's
    own fingerprint hashing, imported from ``build_memory_triage``).
  * Corrections      -- corrections.md table rows; GUARDED_BY comes from the
    guard registry in ``graph_sources.json`` (a correction whose fix is prose
    has no guard entry -- invariant P1's job is to surface that).
  * Validators/CIJobs -- the five script prefixes, INVOKED_BY from grepping
    ``.github/workflows/*.yml`` for each basename.
  * Evaluations      -- extreme-IRR adjudications and calibration stores.

Determinism: all globs and dict walks are sorted, ``data_json`` is serialized
with ``sort_keys=True``, and the content hash stored in ``meta`` is computed
over a canonical serialization that excludes volatile fields (build timestamp,
duration). Two consecutive builds at the same git HEAD produce identical
counts and identical hashes. Output is ASCII-only (Windows cp1252 console).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_memory_triage  # noqa: E402  (parse_file/dedupe/fingerprint reuse)
import falsifier_specs  # noqa: E402  (shared forecast schema/identity)

GIT_WINDOW = 400
VALIDATOR_PREFIXES = ("scan_", "check_", "validate_", "audit_", "calibrate_")
SMALL_RUN_TICKERS = 20  # PRODUCED_BY only for targeted runs, not 833-wide sweeps
TEXT_LIMIT = 400

STATUS_TAG = re.compile(
    r"`\[(active|superseded|disproven)\s+(\d{4}-\d{2}-\d{2})([^\]]*)\]`\s*$"
)
BACKTICK_SPAN = re.compile(r"`([^`]+)`")
SECTION = re.compile(r"^##\s+(.*)$")
CORRECTION_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
WORKFLOW_NAME = re.compile(r"^name:\s*(.+?)\s*$")
QUOTED_PHRASE = re.compile(r'"([^"]{8,})"')


def slugify(text: str, limit: int = 40) -> str:
    frag = re.sub(r"[^a-z0-9]+", "-", text[:limit].lower()).strip("-")
    return frag


def correction_slug(date: str, error: str) -> str:
    """Stable row id: date + first 40 chars of the error text, slugged."""
    return f"{date}-{slugify(error, 40)}"


def norm_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


class GraphBuilder:
    def __init__(self, root: Path):
        self.root = root
        self.nodes: dict[str, dict] = {}
        self.edges: dict[tuple[str, str, str], dict] = {}
        self.warnings: list[str] = []
        self.config = load_json(root / "_system" / "graph" / "graph_sources.json") or {}

    # ------------------------------------------------------------------ #
    # primitives
    #
    # Edge types emitted by this builder (the spec's full list is in
    # _system/graph/README.md "Edge types"):
    #   GUARDED_BY, ENFORCED_BY, INVOKED_BY          (procedural chain)
    #   ASSERTS, RESOLVED_BY, SCORES                 (epistemic chain)
    #   SUPPORTED_BY, SUPERSEDES, DISTILLED_FROM, DECIDED_AS,
    #   PRODUCED_BY, LANDED_IN, BLOCKS, ABOUT
    # CONTRADICTS is in the spec but deliberately has NO projector yet: no
    # repo surface records "claim A contradicts claim B" in a machine-readable
    # way (belief supersession is SUPERSEDES; disproven beliefs are a status,
    # not a pairwise relation). Projecting it from prose would be a guess, and
    # the graph never guesses -- the edge type stays at zero instances until
    # an honest source exists.
    # ------------------------------------------------------------------ #
    @staticmethod
    def _is_empty(value) -> bool:
        return value is None or value == "" or value == {} or value == []

    def node(self, node_id: str, plane: str, ntype: str, *, ticker: str | None = None,
             label: str = "", status: str = "", as_of: str = "", path: str = "",
             data: dict | None = None) -> str:
        incoming = {
            "id": node_id, "plane": plane, "type": ntype, "ticker": ticker,
            "label": label[:TEXT_LIMIT], "status": status, "as_of": as_of,
            "path": path, "data": data or {},
        }
        existing = self.nodes.get(node_id)
        if existing is None:
            self.nodes[node_id] = incoming
            return node_id
        # Merge, never clobber: an empty incoming value can never blank out a
        # non-empty existing one, and conflicts between two non-empty values
        # keep the first writer (deterministic, and build() orders the richest
        # source -- e.g. the registry for Ticker nodes -- first). This is what
        # lets ticker_node() stubs created by work-plane projectors coexist
        # with registry-projected Ticker nodes instead of discarding them.
        for field in ("plane", "type", "ticker", "label", "status", "as_of", "path"):
            if self._is_empty(existing[field]) and not self._is_empty(incoming[field]):
                existing[field] = incoming[field]
        for key, value in incoming["data"].items():
            if self._is_empty(existing["data"].get(key)) and not self._is_empty(value):
                existing["data"][key] = value
        return node_id

    def edge(self, src: str, dst: str, etype: str, data: dict | None = None) -> None:
        key = (src, dst, etype)
        if key not in self.edges:
            self.edges[key] = {"src": src, "dst": dst, "type": etype, "data": data or {}}

    def ticker_node(self, ticker: str) -> str:
        return self.node(f"ticker:{ticker}", "knowledge", "Ticker", ticker=ticker,
                         label=ticker)

    def source_node(self, ref: str) -> str:
        node_id = f"source:{ref}"
        if node_id not in self.nodes:
            exists = (self.root / ref).exists()
            self.node(node_id, "knowledge", "Source", label=ref, path=ref,
                      status="present" if exists else "missing",
                      data={"exists_on_disk": exists})
        return node_id

    # ------------------------------------------------------------------ #
    # work plane
    # ------------------------------------------------------------------ #
    def project_lanes_commits(self) -> None:
        lanes = self.config.get("lanes", [])
        try:
            out = subprocess.run(
                ["git", "log", os.environ.get("GRAPH_LANE_REF") or "HEAD",
                 f"--format=%H|%cI|%s", "-n", str(GIT_WINDOW)],
                cwd=self.root, capture_output=True, text=True, encoding="utf-8",
                errors="replace", check=True,
            ).stdout
        except (subprocess.CalledProcessError, OSError):
            out = ""
            self.warnings.append("git log unavailable; no Lane/Commit nodes")
        commits = []
        for line in out.splitlines():
            parts = line.split("|", 2)
            if len(parts) == 3:
                commits.append(parts)
        for lane in lanes:
            name = lane["name"]
            pattern = re.compile(lane["subject_regex"])
            matched = [(sha, ciso, subj) for sha, ciso, subj in commits
                       if pattern.search(subj)]
            self.node(f"lane:{name}", "work", "Lane", label=name, status="active",
                      as_of=matched[0][1] if matched else "",
                      data={
                          "subject_regex": lane["subject_regex"],
                          "freshness_hours": lane.get("freshness_hours", 48),
                          "commit_count_in_window": len(matched),
                          "last_commit_sha": matched[0][0] if matched else None,
                          "last_commit_iso": matched[0][1] if matched else None,
                      })
            for sha, ciso, subj in matched:
                self.node(f"commit:{sha[:12]}", "work", "Commit", label=subj,
                          as_of=ciso, data={"sha": sha, "lane": name})

    def project_runs(self) -> None:
        runs_dir = self.root / "_system" / "data" / "runs"
        for path in sorted(runs_dir.glob("*.json")):
            receipt = load_json(path)
            if not isinstance(receipt, dict):
                self.warnings.append(f"unreadable run receipt: {path.name}")
                continue
            stem = path.stem
            stages = receipt.get("stages", {})
            written = []
            contracts = stages.get("contracts", {})
            if isinstance(contracts, dict):
                for row in contracts.get("written", []) or []:
                    if isinstance(row, dict) and row.get("ticker"):
                        written.append(row["ticker"])
            data = {
                "scope": receipt.get("scope"),
                "dry_run": receipt.get("dry_run"),
                "ticker_count": receipt.get("ticker_count"),
                "stages": sorted(stages.keys()),
                "contracts_written": len(written),
            }
            run_id = self.node(f"run:{stem}", "work", "Run", label=stem,
                               as_of=receipt.get("as_of", ""), status="recorded",
                               path=str(path.relative_to(self.root)).replace("\\", "/"),
                               data=data)
            if len(written) <= SMALL_RUN_TICKERS:
                for ticker in written:
                    self.edge(f"contract:{ticker}", run_id, "PRODUCED_BY")
                    self.edge(run_id, self.ticker_node(ticker), "ABOUT")
            # LANDED_IN (Run -> Commit) is emitted only when a receipt carries an
            # explicit commit reference; current receipts do not, so the edge
            # type exists with zero instances rather than a fuzzy guess.
            commit_sha = receipt.get("commit") or receipt.get("commit_sha")
            if commit_sha:
                self.edge(run_id, f"commit:{str(commit_sha)[:12]}", "LANDED_IN")

    def project_wave(self) -> None:
        path = self.root / "_system" / "data" / "contract_backfill_queue.json"
        queue = load_json(path)
        if not isinstance(queue, dict):
            return
        tickers = queue.get("tickers", []) or []
        wave_id = self.node(
            "wave:contract_backfill", "work", "Wave", label="contract backfill wave",
            as_of=str(queue.get("updated", "")), status="active",
            path=str(path.relative_to(self.root)).replace("\\", "/"),
            data={
                "wave_size": queue.get("wave_size"),
                "total_pending": queue.get("total_pending"),
                "tickers": tickers,
                "dispatch_attempts": queue.get("dispatch_attempts"),
                "stall_breaker": queue.get("stall_breaker"),
                "reason": queue.get("reason"),
            })
        if len(tickers) <= 100:
            for ticker in tickers:
                self.edge(wave_id, self.ticker_node(str(ticker)), "ABOUT")

    # ------------------------------------------------------------------ #
    # knowledge plane: tickers, contracts, components, facts, falsifiers
    # ------------------------------------------------------------------ #
    def project_tickers(self) -> None:
        registry = load_json(self.root / "_system" / "portfolio" / "registry.json") or {}
        for section in ("holdings", "watchlist"):
            entries = registry.get(section, {})
            if not isinstance(entries, dict):
                continue
            for ticker in sorted(entries):
                info = entries[ticker] or {}
                cls = info.get("classification", {}) or {}
                self.node(f"ticker:{ticker}", "knowledge", "Ticker", ticker=ticker,
                          label=info.get("company", ticker),
                          status=cls.get("stance", ""),
                          as_of=info.get("onboarded", ""),
                          data={"market": info.get("market"),
                                "archetype": cls.get("archetype"),
                                "sleeve": cls.get("investment_sleeve"),
                                "registry_section": section})

    def project_contracts(self) -> None:
        """Stream every per-ticker contract + ledger; never hold them all."""
        for contract_path in sorted(self.root.glob("*/research/valuation_contract.json")):
            ticker = contract_path.parts[-3]
            contract = load_json(contract_path)
            if not isinstance(contract, dict):
                self.warnings.append(f"unreadable contract: {ticker}")
                continue
            rel = str(contract_path.relative_to(self.root)).replace("\\", "/")
            tid = self.ticker_node(ticker)
            cid = self.node(f"contract:{ticker}", "knowledge", "Contract",
                            ticker=ticker, label=f"{ticker} valuation contract",
                            status=str(contract.get("status", "")),
                            as_of=str(contract.get("as_of", "")), path=rel,
                            data={"method_route": contract.get("method_route")
                                  if isinstance(contract.get("method_route"), str)
                                  else None})
            self.edge(cid, tid, "ABOUT")
            falsifier_by_text: dict[str, str] = {}
            components = contract.get("economic_ownership_map") or []
            comp_ids: dict[str, str] = {}
            for comp in components:
                if not isinstance(comp, dict):
                    continue
                comp_key = str(comp.get("component_id", "unknown"))
                comp_id = self.node(
                    f"component:{ticker}:{comp_key}", "knowledge", "Component",
                    ticker=ticker, label=str(comp.get("label", comp_key)),
                    status=str(comp.get("valuation_status", "")), path=rel,
                    data={"method": comp.get("method"),
                          "category": comp.get("category"),
                          "treatment": comp.get("treatment")})
                comp_ids[comp_key] = comp_id
                self.edge(comp_id, tid, "ABOUT")
                text = comp.get("falsifier")
                if isinstance(text, str) and text.strip():
                    fals_id = self._prose_falsifier(ticker, text, rel)
                    falsifier_by_text[text.strip()] = fals_id
                    self.edge(comp_id, fals_id, "ASSERTS")
            monitoring = contract.get("monitoring") or {}
            for text in monitoring.get("falsifiers", []) or []:
                if not isinstance(text, str) or not text.strip():
                    continue
                fals_id = falsifier_by_text.get(text.strip())
                if fals_id is None:
                    fals_id = self._prose_falsifier(ticker, text, rel)
                    falsifier_by_text[text.strip()] = fals_id
                    self.edge(cid, fals_id, "ASSERTS")
            self._project_falsifier_specs(ticker, cid, comp_ids, contract)
            self._project_blockers(ticker, cid, contract, rel)
            self._project_fact_ledger(ticker, tid)

    def _project_blockers(self, ticker: str, contract_id: str, contract: dict,
                          rel: str) -> None:
        """Blocker nodes from ``evidence.blockers[]`` -> BLOCKS edges to the
        Contract, so the evidence_blocked book is traversable instead of a
        status string. Id = contract ticker + stable slug of the blocker text
        (plus a short digest so distinct texts sharing a 60-char prefix cannot
        collide)."""
        evidence = contract.get("evidence") or {}
        if not isinstance(evidence, dict):
            return
        for text in evidence.get("blockers", []) or []:
            if not isinstance(text, str) or not text.strip():
                continue
            text = text.strip()
            digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
            slug = slugify(text, 60) or digest
            blocker_id = self.node(
                f"blocker:{ticker}:{slug}-{digest}", "knowledge", "Blocker",
                ticker=ticker, label=text[:TEXT_LIMIT], status="open", path=rel,
                data={"text": text[:TEXT_LIMIT]})
            self.edge(blocker_id, contract_id, "BLOCKS")

    def _prose_falsifier(self, ticker: str, text: str, rel: str) -> str:
        digest = hashlib.sha1(text.strip().encode("utf-8")).hexdigest()[:10]
        return self.node(
            f"falsifier:{ticker}:{digest}", "knowledge", "Falsifier", ticker=ticker,
            label=text.strip()[:TEXT_LIMIT], status="prose", path=rel,
            data={"typed": False, "text": text.strip()[:TEXT_LIMIT]})

    def _project_falsifier_specs(self, ticker: str, contract_id: str,
                                 comp_ids: dict[str, str], contract: dict) -> None:
        """Optional typed sidecar, schema {specs: [{component_id, metric, ...}]}."""
        path = self.root / ticker / "research" / "falsifier_specs.json"
        if not path.is_file():
            return
        sidecar = load_json(path)
        if not isinstance(sidecar, dict):
            self.warnings.append(f"unreadable falsifier_specs: {ticker}")
            return
        rel = str(path.relative_to(self.root)).replace("\\", "/")
        for index, spec in enumerate(sidecar.get("specs", []) or []):
            if not isinstance(spec, dict):
                continue
            comp_key = str(spec.get("component_id", "unknown"))
            metric = str(spec.get("metric", "unknown"))
            errors = falsifier_specs.spec_errors(spec, index, contract=contract)
            resolvable, reason = falsifier_specs.metric_resolvable(
                ticker, spec, self.root)
            typed = not errors and not spec.get("untestable", False) and resolvable
            if spec.get("untestable", False):
                status = "untestable"
            elif typed:
                status = "typed"
            else:
                status = "invalid"
            if spec.get("spec_id"):
                identity = (f"falsifier:{ticker}:spec:{spec['spec_id']}:"
                            f"r{int(spec.get('spec_revision') or 1)}")
            else:
                identity = f"falsifier:{ticker}:spec:{comp_key}:{slugify(metric, 60)}"
            _measurement, observable, _deadline = falsifier_specs.forecast_dates(spec)
            fals_id = self.node(
                identity,
                "knowledge", "Falsifier", ticker=ticker,
                label=f"{metric} {spec.get('comparator', '')} {spec.get('threshold', '')}".strip(),
                status=status,
                as_of=(observable.isoformat() if observable else str(spec.get("due", ""))),
                path=rel,
                data={"typed": typed, "validation_errors": errors,
                      "resolvable": resolvable, "resolvability_reason": reason,
                      "spec_hash": falsifier_specs.spec_payload_hash(spec),
                      **{k: spec.get(k) for k in (
                    "spec_id", "spec_revision", "authored_at", "analysis_run_id",
                    "author", "model_id", "prompt_version",
                    "contract_hash", "method_id", "power_zone",
                    "component_id", "metric", "comparator", "threshold", "unit",
                    "due", "measurement_period_end", "observable_after",
                    "resolution_deadline", "source_hint", "probability_fires",
                    "severity", "derived_from", "untestable", "rationale")}})
            self.edge(comp_ids.get(comp_key, contract_id), fals_id, "ASSERTS")

    def _project_fact_ledger(self, ticker: str, tid: str) -> None:
        path = self.root / ticker / "research" / "valuation_fact_ledger.json"
        if not path.is_file():
            return
        ledger = load_json(path)
        if not isinstance(ledger, dict):
            self.warnings.append(f"unreadable fact ledger: {ticker}")
            return
        rel = str(path.relative_to(self.root)).replace("\\", "/")
        for fact in ledger.get("facts", []) or []:
            if not isinstance(fact, dict) or not fact.get("locked"):
                continue
            field_id = str(fact.get("field_id", "unknown"))
            source = fact.get("source") or {}
            fact_id = self.node(
                f"fact:{ticker}:{field_id}", "knowledge", "Fact", ticker=ticker,
                label=f"{ticker} {field_id}", status="locked",
                as_of=str(source.get("as_of", "")), path=rel,
                data={"unit": fact.get("unit"),
                      "confidence": fact.get("confidence"),
                      "fx_conversion": fact.get("fx_conversion")})
            ref = source.get("ref")
            if isinstance(ref, str) and ref:
                self.edge(fact_id, self.source_node(ref), "SUPPORTED_BY",
                          {"locator": str(source.get("locator", ""))[:TEXT_LIMIT]})

    def project_outcomes(self) -> None:
        path = self.root / "_system" / "research" / "falsifier_outcomes.jsonl"
        if not path.is_file():
            return
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                self.warnings.append(f"bad outcome line {i + 1}")
                continue
            digest = hashlib.sha1(line.encode("utf-8")).hexdigest()[:12]
            ticker = rec.get("ticker")
            outcome_id = self.node(
                f"outcome:{digest}", "knowledge", "Outcome", ticker=ticker,
                label=str(rec.get("verdict", rec.get("result", "outcome"))),
                status=str(rec.get("verdict", rec.get("result", ""))),
                as_of=str(rec.get("resolved_on", rec.get("resolved_at", rec.get("as_of", "")))),
                path="_system/research/falsifier_outcomes.jsonl", data=rec)
            fals_id = rec.get("falsifier_id")
            if fals_id and f"falsifier:{fals_id}" in self.nodes:
                self.edge(f"falsifier:{fals_id}", outcome_id, "RESOLVED_BY")
            elif ticker and rec.get("spec_id"):
                candidate = (f"falsifier:{ticker}:spec:{rec['spec_id']}:"
                             f"r{int(rec.get('spec_revision') or 1)}")
                if candidate in self.nodes:
                    self.edge(candidate, outcome_id, "RESOLVED_BY")
            elif ticker and rec.get("component_id") and rec.get("metric"):
                candidate = (f"falsifier:{ticker}:spec:{rec['component_id']}:"
                             f"{slugify(str(rec['metric']), 60)}")
                if candidate in self.nodes:
                    self.edge(candidate, outcome_id, "RESOLVED_BY")
            elif ticker and rec.get("component_id") and isinstance(rec.get("spec"), dict):
                metric = rec["spec"].get("metric")
                candidate = (f"falsifier:{ticker}:spec:{rec['component_id']}:"
                             f"{slugify(str(metric), 60)}")
                if metric and candidate in self.nodes:
                    self.edge(candidate, outcome_id, "RESOLVED_BY")
            method_id = rec.get("method_id")
            power_zone = rec.get("power_zone")
            if method_id and power_zone:
                bucket = self.node(
                    f"bucket:{method_id}:{power_zone}", "knowledge",
                    "CalibrationBucket", label=f"{method_id} x {power_zone}",
                    data={"method_id": method_id, "power_zone": power_zone})
                self.edge(outcome_id, bucket, "SCORES")
            if ticker:
                self.edge(outcome_id, self.ticker_node(str(ticker)), "ABOUT")

    # ------------------------------------------------------------------ #
    # knowledge plane: beliefs, proposals
    # ------------------------------------------------------------------ #
    def project_beliefs(self) -> None:
        path = self.root / "_system" / "memory" / "MEMORY.md"
        if not path.is_file():
            return
        rel = "_system/memory/MEMORY.md"
        lens = ""
        previous: dict | None = None  # for the adjacent-supersede heuristic
        for raw in path.read_text(encoding="utf-8").splitlines():
            section = SECTION.match(raw)
            if section:
                title = section.group(1)
                if "Approved beliefs" in title:
                    lens = title.split("—")[-1].strip() or title
                elif "Portfolio context" in title:
                    lens = "Portfolio context"
                else:
                    lens = ""
                previous = None
                continue
            if not lens:
                continue
            if raw.startswith("| ") and lens.lower().startswith("company"):
                self._belief_table_row(raw, rel)
                continue
            if not raw.startswith("- "):
                continue
            tag = STATUS_TAG.search(raw)
            if not tag:
                continue
            text = raw[2:tag.start()].rstrip()
            status, date, extra = tag.group(1), tag.group(2), tag.group(3)
            sources = self._source_paths(text)
            belief = self._belief_node(text, lens, status, date,
                                       "agent" in extra, sources, rel)
            # SUPERSEDES heuristic: an active bullet directly following a
            # superseded sibling that shares a cited source path replaced it.
            if (previous and previous["status"] == "superseded"
                    and status == "active"
                    and set(sources) & set(previous["sources"])):
                self.edge(belief["id"], previous["id"], "SUPERSEDES")
            previous = {"id": belief["id"], "status": status, "sources": sources}

    def _belief_node(self, text: str, lens: str, status: str, date: str,
                     agent: bool, sources: list[str], rel: str,
                     ticker: str | None = None) -> dict:
        # The slug is the belief's address (graph_query `belief <slug>`), so it
        # comes from the claim text alone, not the trailing `— \`source\`` part.
        core = re.split(r"\s+—\s+`", text, 1)[0]
        slug = slugify(core, 60)
        node_id = f"belief:{slug}"
        if node_id in self.nodes and norm_text(
                self.nodes[node_id]["data"].get("text", ""))[:80] != norm_text(text)[:80]:
            node_id = f"belief:{slug}-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:6]}"
        self.node(node_id, "knowledge", "Belief", ticker=ticker,
                  label=text[:120], status=status, as_of=date, path=rel,
                  data={"lens": lens, "agent_approved": agent,
                        "text": text[:TEXT_LIMIT], "sources": sources})
        for ref in sources:
            self.edge(node_id, self.source_node(ref), "SUPPORTED_BY")
        if ticker:
            self.edge(node_id, self.ticker_node(ticker), "ABOUT")
        return {"id": node_id}

    def _belief_table_row(self, raw: str, rel: str) -> None:
        cells = [c.strip() for c in raw.strip().strip("|").split("|")]
        if len(cells) < 5 or cells[0] in ("Ticker", "") or set(cells[0]) <= {"-"}:
            return
        ticker, belief_text, source_cell, approved, status_cell = cells[:5]
        match = re.search(r"(active|superseded|disproven)\s+(\d{4}-\d{2}-\d{2})",
                          status_cell)
        status = match.group(1) if match else "active"
        date = match.group(2) if match else approved[:10]
        sources = self._source_paths(source_cell)
        self._belief_node(belief_text, "company", status, date,
                          "agent" in status_cell, sources, rel, ticker=ticker)

    @staticmethod
    def _source_paths(text: str) -> list[str]:
        paths = []
        for span in BACKTICK_SPAN.findall(text):
            if "/" in span and " " not in span and "{" not in span \
                    and "*" not in span and not span.startswith("["):
                paths.append(span.rstrip("/"))
        return sorted(set(paths))

    def project_proposals(self) -> None:
        ledger = load_json(self.root / "_system" / "memory" / "triage_ledger.json") or {}
        decisions = ledger.get("decisions", {})
        beliefs = [(nid, norm_text(node["data"].get("text", "")))
                   for nid, node in self.nodes.items() if node["type"] == "Belief"]
        for pid in sorted(decisions):
            row = decisions[pid] or {}
            decision = str(row.get("decision", "unknown"))
            node_id = self.node(
                f"proposal:{pid}", "knowledge", "Proposal",
                label=str(row.get("excerpt", ""))[:120], status=decision,
                as_of=str(row.get("date", "")),
                path="_system/memory/triage_ledger.json",
                data={"lens": row.get("lens"), "by": row.get("by"),
                      "first_seen": row.get("first_seen"),
                      "excerpt": str(row.get("excerpt", ""))[:TEXT_LIMIT]})
            decision_node = self.node(f"decision:{decision}", "knowledge",
                                      "Decision", label=decision)
            self.edge(node_id, decision_node, "DECIDED_AS",
                      {"date": row.get("date"), "by": row.get("by")})
            if decision == "promoted":
                self._distill_edge(node_id, row, beliefs)
        # Daily-log proposals the ledger has not decided.
        daily_dir = self.root / "_system" / "memory" / "daily"
        items = []
        for day_path in sorted(daily_dir.glob("*.md")):
            items.extend(build_memory_triage.parse_file(day_path))
        deduped, _ = build_memory_triage.dedupe(items)
        for item in sorted(deduped, key=lambda it: (it["day"], it["lens"],
                                                    " ".join(it["body"])[:80])):
            fid = build_memory_triage.fingerprint(item)
            if fid in decisions:
                continue
            excerpt = " ".join(item["body"])
            self.node(f"proposal:{fid}", "knowledge", "Proposal",
                      label=excerpt[:120], status="undecided",
                      as_of=item["day"],
                      path=f"_system/memory/daily/{item['file']}",
                      data={"lens": item["lens"], "excerpt": excerpt[:TEXT_LIMIT],
                            "mechanical": build_memory_triage.is_mechanical(item)})

    def _distill_edge(self, proposal_id: str, row: dict,
                      beliefs: list[tuple[str, str]]) -> None:
        """DISTILLED_FROM (Belief -> Proposal), cheapest match that holds:
        the anchor's double-quoted phrase, else the excerpt's normalized prefix."""
        anchor = str(row.get("memory_anchor", "") or "")
        quoted = QUOTED_PHRASE.search(anchor)
        needles = []
        if quoted:
            needles.append(norm_text(quoted.group(1))[:80])
        excerpt_prefix = norm_text(str(row.get("excerpt", "")))[:40]
        if len(excerpt_prefix) >= 20:
            needles.append(excerpt_prefix)
        for belief_id, belief_text in beliefs:
            if any(needle and needle in belief_text for needle in needles):
                self.edge(belief_id, proposal_id, "DISTILLED_FROM")
                return

    # ------------------------------------------------------------------ #
    # knowledge plane: corrections, guards, validators, CI, evaluations
    # ------------------------------------------------------------------ #
    def project_corrections(self) -> None:
        path = self.root / "_system" / "memory" / "corrections.md"
        if not path.is_file():
            return
        registry = self.config.get("guards", {})
        seen_slugs = set()
        for raw in path.read_text(encoding="utf-8").splitlines():
            if not raw.startswith("|"):
                continue
            cells = [c.strip() for c in raw.strip().strip("|").split("|")]
            if len(cells) < 4 or not CORRECTION_DATE.match(cells[0]):
                continue
            if len(cells) >= 5:
                date, ticker, error, correction, source = cells[:5]
            else:
                # Two log rows merge the Error and Correction cells; the row is
                # still a correction and must still get a stable id.
                date, ticker, error, source = cells
                correction = ""
            slug = correction_slug(date, error)
            seen_slugs.add(slug)
            # A cell like "AAOI/ADBE" names several real tickers, not one
            # ticker called "AAOI/ADBE": split and emit an ABOUT edge to each.
            raw_ticker = ticker if ticker not in ("", "-", "—") else None
            tickers = ([t for t in (p.strip() for p in raw_ticker.split("/")) if t]
                       if raw_ticker else [])
            node_id = self.node(
                f"correction:{slug}", "knowledge", "Correction",
                ticker=tickers[0] if len(tickers) == 1 else None,
                label=error[:120],
                status="guarded" if slug in registry else "unguarded",
                as_of=date, path="_system/memory/corrections.md",
                data={"error": error[:TEXT_LIMIT],
                      "correction": correction[:TEXT_LIMIT],
                      "source_column": source[:TEXT_LIMIT],
                      "tickers": tickers})
            for t in tickers:
                self.edge(node_id, self.ticker_node(t), "ABOUT")
            for guard in registry.get(slug, []):
                guard_id = self.node(
                    f"guard:{guard['id']}", "knowledge", "Guard",
                    label=guard.get("label", guard["id"]), status="registered",
                    path=guard.get("script", ""),
                    data={"function": guard.get("function"),
                          "script": guard.get("script")})
                self.edge(node_id, guard_id, "GUARDED_BY")
                for enforcer in guard.get("enforced_by", []):
                    basename = enforcer.rsplit("/", 1)[-1]
                    validator_id = self.node(
                        f"validator:{basename}", "knowledge", "Validator",
                        label=basename, path=enforcer,
                        data={"origin": "guard_registry"})
                    self.edge(guard_id, validator_id, "ENFORCED_BY")
        unmatched = sorted(set(registry) - seen_slugs)
        if unmatched:
            self.warnings.append(
                "guard registry keys matching no correction row: " + ", ".join(unmatched))

    def project_validators_ci(self) -> None:
        scripts_dir = self.root / "_system" / "scripts"
        for script in sorted(scripts_dir.glob("*.py")):
            if script.name.startswith(VALIDATOR_PREFIXES):
                self.node(f"validator:{script.name}", "knowledge", "Validator",
                          label=script.name,
                          path=f"_system/scripts/{script.name}",
                          data={"origin": "prefix_glob"})
        workflows_dir = self.root / ".github" / "workflows"
        workflow_texts = {}
        for wf in sorted(workflows_dir.glob("*.yml")):
            workflow_texts[wf.name] = wf.read_text(encoding="utf-8").splitlines()
        validator_ids = sorted(nid for nid, node in self.nodes.items()
                               if node["type"] == "Validator")
        for validator_id in validator_ids:
            basename = validator_id.split(":", 1)[1]
            for wf_name, lines in sorted(workflow_texts.items()):
                hits = [i + 1 for i, line in enumerate(lines) if basename in line]
                if not hits:
                    continue
                label = next((WORKFLOW_NAME.match(line).group(1)
                              for line in lines if WORKFLOW_NAME.match(line)), wf_name)
                ci_id = self.node(f"ci:{wf_name}", "knowledge", "CIJob",
                                  label=label,
                                  path=f".github/workflows/{wf_name}")
                self.edge(validator_id, ci_id, "INVOKED_BY", {"lines": hits})

    def project_evaluations(self) -> None:
        research = self.root / "_system" / "research"
        adjudications = sorted(research.glob("extreme_irr_adjudication_*.json"))
        previous_id = None
        for path in adjudications:
            payload = load_json(path) or {}
            node_id = self.node(
                f"eval:{path.stem}", "knowledge", "Evaluation", label=path.stem,
                status=str(payload.get("revision", "")),
                as_of=str(payload.get("as_of", "")),
                path=f"_system/research/{path.name}",
                data={"rubric": str(payload.get("adjudication_rule", ""))[:TEXT_LIMIT],
                      "authority": str(payload.get("authority", ""))[:TEXT_LIMIT],
                      "kind": "adjudication"})
            if previous_id:
                self.edge(node_id, previous_id, "SUPERSEDES")
            previous_id = node_id
        for name in ("committee_calibration.json", "falsifier_calibration.json"):
            path = research / name
            if not path.is_file():
                continue
            payload = load_json(path) or {}
            self.node(f"eval:{path.stem}", "knowledge", "Evaluation",
                      label=path.stem, status=str(payload.get("status", "")),
                      path=f"_system/research/{name}",
                      data={"kind": "calibration",
                            "completed_outcomes": (payload.get("completed_outcomes")
                                                   if payload.get("completed_outcomes") is not None
                                                   else payload.get("resolved_outcomes")),
                            "warning": str(payload.get("warning", ""))[:TEXT_LIMIT]})

    # ------------------------------------------------------------------ #
    # assembly
    # ------------------------------------------------------------------ #
    def build(self) -> None:
        # Tickers project FIRST: the registry is the richest source for
        # ticker:{T} nodes (company, archetype, sleeve, stance), and node()'s
        # merge keeps the first non-empty value, so the registry must win over
        # the bare ticker_node() stubs the run/wave/contract projectors emit.
        self.project_tickers()
        self.project_lanes_commits()
        self.project_runs()
        self.project_wave()
        self.project_contracts()
        self.project_outcomes()
        self.project_beliefs()
        self.project_proposals()
        self.project_corrections()
        self.project_validators_ci()
        self.project_evaluations()

    def content_hash(self) -> str:
        digest = hashlib.sha256()
        for node_id in sorted(self.nodes):
            node = self.nodes[node_id]
            digest.update(json.dumps(
                [node["id"], node["plane"], node["type"], node["ticker"],
                 node["label"], node["status"], node["as_of"], node["path"],
                 node["data"]],
                sort_keys=True, ensure_ascii=True).encode("ascii"))
        for key in sorted(self.edges):
            edge = self.edges[key]
            digest.update(json.dumps(
                [edge["src"], edge["dst"], edge["type"], edge["data"]],
                sort_keys=True, ensure_ascii=True).encode("ascii"))
        return digest.hexdigest()

    def git_head(self) -> str:
        try:
            return subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=self.root, capture_output=True,
                text=True, check=True).stdout.strip()
        except (subprocess.CalledProcessError, OSError):
            return ""

    def write(self, db_path: Path, started: float) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        if db_path.exists():
            db_path.unlink()
        conn = sqlite3.connect(db_path)
        try:
            conn.executescript(
                "CREATE TABLE nodes (id TEXT PRIMARY KEY, plane TEXT, type TEXT,"
                " ticker TEXT, label TEXT, status TEXT, as_of TEXT, path TEXT,"
                " data_json TEXT);"
                "CREATE TABLE edges (src TEXT, dst TEXT, type TEXT, data_json TEXT,"
                " PRIMARY KEY (src, dst, type));"
                "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);"
                "CREATE INDEX idx_nodes_type ON nodes (type);"
                "CREATE INDEX idx_nodes_ticker ON nodes (ticker);"
                "CREATE INDEX idx_edges_src ON edges (src);"
                "CREATE INDEX idx_edges_dst ON edges (dst);"
                "CREATE INDEX idx_edges_type ON edges (type);")
            conn.executemany(
                "INSERT INTO nodes VALUES (?,?,?,?,?,?,?,?,?)",
                [(n["id"], n["plane"], n["type"], n["ticker"], n["label"],
                  n["status"], n["as_of"], n["path"],
                  json.dumps(n["data"], sort_keys=True, ensure_ascii=True))
                 for n in (self.nodes[k] for k in sorted(self.nodes))])
            conn.executemany(
                "INSERT INTO edges VALUES (?,?,?,?)",
                [(e["src"], e["dst"], e["type"],
                  json.dumps(e["data"], sort_keys=True, ensure_ascii=True))
                 for e in (self.edges[k] for k in sorted(self.edges))])
            meta = {
                "schema_version": "1.0",
                "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "build_seconds": f"{time.time() - started:.1f}",
                "git_head": self.git_head(),
                "content_hash": self.content_hash(),
                "node_count": str(len(self.nodes)),
                "edge_count": str(len(self.edges)),
                "warnings": json.dumps(self.warnings, ensure_ascii=True),
            }
            conn.executemany("INSERT INTO meta VALUES (?,?)",
                             sorted(meta.items()))
            conn.commit()
        finally:
            conn.close()

    def summary(self) -> dict:
        node_types: dict[str, int] = {}
        for node in self.nodes.values():
            node_types[node["type"]] = node_types.get(node["type"], 0) + 1
        edge_types: dict[str, int] = {}
        for edge in self.edges.values():
            edge_types[edge["type"]] = edge_types.get(edge["type"], 0) + 1
        return {"nodes": node_types, "edges": edge_types}


def build(root: Path | None = None, db_path: Path | None = None) -> GraphBuilder:
    root = root or ROOT
    db_path = db_path or root / "_system" / "graph" / "graph.db"
    started = time.time()
    builder = GraphBuilder(root)
    builder.build()
    builder.write(db_path, started)
    return builder


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--db", type=Path, default=None)
    args = parser.parse_args()
    started = time.time()
    builder = build(args.root, args.db)
    summary = builder.summary()
    print("graph build complete in %.1fs" % (time.time() - started))
    print("nodes: %d  edges: %d" % (len(builder.nodes), len(builder.edges)))
    for ntype in sorted(summary["nodes"]):
        print("  node %-18s %6d" % (ntype, summary["nodes"][ntype]))
    for etype in sorted(summary["edges"]):
        print("  edge %-18s %6d" % (etype, summary["edges"][etype]))
    for warning in builder.warnings:
        print("  [warn] " + warning.encode("ascii", "replace").decode("ascii"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
