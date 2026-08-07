#!/usr/bin/env python3
"""Calibration report for the SSI pipeline against the blueprint bars.

Reads the `_eval/` gold sets (see `_eval/README.md`) and states the current
numbers for:

  severity-5 recall        (bar: 100%)   from ssi_sev5_events.jsonl
  locator accuracy         (bar: 100%)   from ssi_skeptic_gold.jsonl
  top-alert precision      (bar: >=85%)  from ssi_alert_adjudications.jsonl

Metrics with no adjudicated cases report `insufficient_data` — never a
fabricated number. `--enforce` exits non-zero when a *measurable* bar is
unmet (CI-friendly). `--splits` prints the issuer-level train/dev/test
assignment used for tuning discipline.

Usage:
  python _system/scripts/calibrate_ssi.py
  python _system/scripts/calibrate_ssi.py --enforce
  python _system/scripts/calibrate_ssi.py --splits
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = ROOT / "_eval"

BARS = {
    "severity5_recall": 1.00,
    "locator_accuracy": 1.00,
    "top_alert_precision": 0.85,
}


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def latest_adjudications(rows: list[dict]) -> list[dict]:
    """Collapse an append-only gold log to the current verdict per case.

    The file is append-only by rule -- "never delete a gold case; supersede with
    a new line if re-adjudicated" -- so a re-adjudicated case appears twice and
    the later line is the live one. Without this, a superseded case is counted
    under both its old and its new verdict.

    Keyed on (issuer, claim_id, as_of). Cases with no claim_id cannot be
    collapsed safely and are all kept.
    """
    latest: dict[tuple, dict] = {}
    unkeyed: list[dict] = []
    for row in rows:
        claim_id = row.get("claim_id")
        if not claim_id:
            unkeyed.append(row)
            continue
        latest[(row.get("issuer"), claim_id, row.get("as_of"))] = row
    return [*latest.values(), *unkeyed]


def issuer_split(issuer: str) -> str:
    bucket = int(hashlib.sha1(issuer.encode("utf-8")).hexdigest(), 16) % 10
    if bucket <= 6:
        return "train"
    if bucket <= 8:
        return "dev"
    return "test"


# A recall claim needs more than a couple of events behind it. One event caught
# is 100% recall arithmetically and tells you nothing about the detector.
MIN_SEV5_EVENTS_FOR_RECALL = 5


def severity5_recall(rows: list[dict]) -> tuple[float | None, str]:
    if not rows:
        return None, "no known critical events recorded (_eval/ssi_sev5_events.jsonl empty)"
    caught = sum(1 for r in rows if r.get("caught") is True)
    if len(rows) < MIN_SEV5_EVENTS_FOR_RECALL:
        return None, (
            f"{caught}/{len(rows)} caught, but {len(rows)} event(s) is below the "
            f"{MIN_SEV5_EVENTS_FOR_RECALL}-event floor for a recall claim; "
            "add known critical events to _eval/ssi_sev5_events.jsonl"
        )
    return caught / len(rows), f"{caught}/{len(rows)} known critical events caught"


def locator_accuracy(rows: list[dict], emitted_claims: int) -> tuple[float | None, str]:
    """Share of emitted claims that were not generator errors.

    Infrastructure failures are excluded outright: the sources moved under the
    pack, so the claim was never re-checked and it is neither a generator nor a
    skeptic error. Counting them either way would corrupt this number -- the 258
    NVDA source_drift cases alone would read as 99.5% against a 100% bar.

    With no adjudicated cases the formula returns exactly 1.0, which is a
    measurement of nothing: it says "no confirmed errors", not "no errors". That
    now reports INSUFFICIENT DATA instead, per the repo rule against inventing a
    number. --enforce only fails on a measurable bar, so this stays CI-safe.
    """
    infrastructure = [r for r in rows if r.get("adjudication") == "infrastructure"]
    real = [r for r in rows if r.get("adjudication") != "infrastructure"]
    adjudicated = [r for r in real if r.get("adjudication") not in (None, "pending")]
    pending = len(real) - len(adjudicated)
    generator_errors = sum(1 for r in adjudicated if r.get("adjudication") == "generator_error")
    infra_note = f"; {len(infrastructure)} infrastructure case(s) excluded" if infrastructure else ""
    if emitted_claims == 0 and not rows:
        return None, "no verification runs recorded yet"
    if emitted_claims == 0:
        return None, f"{len(real)} gold cases ({pending} pending adjudication) but no emitted-claim census"
    if not adjudicated:
        return None, (
            f"no adjudicated gold cases yet, so accuracy is unmeasured; "
            f"{pending} pending over {emitted_claims} emitted claims{infra_note}"
        )
    accuracy = 1.0 - generator_errors / max(emitted_claims, 1)
    return accuracy, (
        f"{generator_errors} adjudicated generator errors over {emitted_claims} emitted claims; "
        f"{pending} gold cases still pending adjudication{infra_note}"
    )


def top_alert_precision(rows: list[dict]) -> tuple[float | None, str]:
    verdicts = [r for r in rows if r.get("adjudication") in ("real", "noise")]
    if not verdicts:
        return None, "no adjudicated severity>=4 alerts (_eval/ssi_alert_adjudications.jsonl empty)"
    real = sum(1 for r in verdicts if r["adjudication"] == "real")
    return real / len(verdicts), f"{real}/{len(verdicts)} adjudicated alerts were real"


def emitted_claim_census() -> int:
    total = 0
    for path in ROOT.glob("*/research/evidence/ssi_verified_claims_*.json"):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        total += doc.get("verified_count", 0) + doc.get("failed_count", 0)
    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--enforce", action="store_true", help="exit 1 if a measurable bar is unmet")
    parser.add_argument("--splits", action="store_true", help="print issuer train/dev/test assignment")
    args = parser.parse_args(argv)

    gold = latest_adjudications(_read_jsonl(EVAL_DIR / "ssi_skeptic_gold.jsonl"))
    alerts = _read_jsonl(EVAL_DIR / "ssi_alert_adjudications.jsonl")
    events = _read_jsonl(EVAL_DIR / "ssi_sev5_events.jsonl")

    if args.splits:
        issuers = sorted(
            {r.get("issuer") for r in gold + alerts + events if r.get("issuer")}
            | {p.parents[2].name for p in ROOT.glob("*/research/evidence/ssi_verified_claims_*.json")}
        )
        for issuer in issuers:
            print(f"{issuer_split(issuer):5s}  {issuer}")
        return 0

    census = emitted_claim_census()
    metrics = {
        "severity5_recall": severity5_recall(events),
        "locator_accuracy": locator_accuracy(gold, census),
        "top_alert_precision": top_alert_precision(alerts),
    }

    print("SSI calibration vs blueprint bars")
    print(f"(emitted-claim census across repo: {census} claims)\n")
    failures = 0
    for name, (value, detail) in metrics.items():
        bar = BARS[name]
        if value is None:
            verdict = "INSUFFICIENT DATA"
        elif value >= bar:
            verdict = "MEETS BAR"
        else:
            verdict = "BELOW BAR"
            failures += 1
        shown = f"{value:.3f}" if value is not None else "n/a"
        print(f"  {name:22s} {shown:>7s}  (bar {bar:.2f})  {verdict}")
        print(f"      {detail}")
    pending = sum(1 for r in gold if r.get("adjudication") in (None, "pending"))
    infrastructure = sum(1 for r in gold if r.get("adjudication") == "infrastructure")
    if pending:
        print(f"\n  NOTE: {pending} skeptic gold case(s) pending adjudication — adjudicate to firm up locator accuracy.")
    if infrastructure:
        print(f"  NOTE: {infrastructure} gold case(s) labelled infrastructure (source drift / pack mismatch); "
              "excluded from locator accuracy — re-run on a stable pack to get a real verdict.")
    if args.enforce and failures:
        print(f"\nENFORCE: {failures} measurable bar(s) unmet.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
