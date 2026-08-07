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


def issuer_split(issuer: str) -> str:
    bucket = int(hashlib.sha1(issuer.encode("utf-8")).hexdigest(), 16) % 10
    if bucket <= 6:
        return "train"
    if bucket <= 8:
        return "dev"
    return "test"


def severity5_recall(rows: list[dict]) -> tuple[float | None, str]:
    if not rows:
        return None, "no known critical events recorded (_eval/ssi_sev5_events.jsonl empty)"
    caught = sum(1 for r in rows if r.get("caught") is True)
    return caught / len(rows), f"{caught}/{len(rows)} known critical events caught"


def locator_accuracy(rows: list[dict], emitted_claims: int) -> tuple[float | None, str]:
    adjudicated = [r for r in rows if r.get("adjudication") not in (None, "pending")]
    pending = len(rows) - len(adjudicated)
    generator_errors = sum(1 for r in adjudicated if r.get("adjudication") == "generator_error")
    if emitted_claims == 0 and not rows:
        return None, "no verification runs recorded yet"
    if emitted_claims == 0:
        return None, f"{len(rows)} gold cases ({pending} pending adjudication) but no emitted-claim census"
    accuracy = 1.0 - generator_errors / max(emitted_claims, 1)
    return accuracy, (
        f"{generator_errors} adjudicated generator errors over {emitted_claims} emitted claims; "
        f"{pending} gold cases still pending adjudication"
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

    gold = _read_jsonl(EVAL_DIR / "ssi_skeptic_gold.jsonl")
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
    if pending:
        print(f"\n  NOTE: {pending} skeptic gold case(s) pending adjudication — adjudicate to firm up locator accuracy.")
    if args.enforce and failures:
        print(f"\nENFORCE: {failures} measurable bar(s) unmet.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
