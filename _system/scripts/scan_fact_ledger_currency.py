#!/usr/bin/env python3
"""Scan locked currency labels against the SEC companyfacts unit key they came from.

Two surfaces are scanned, because the label is asserted in both and only one of
them is what the valuation actually consumes:

  * ``{TICKER}/research/valuation_fact_ledger.json`` - every locked fact, and
  * ``{TICKER}/research/valuation.json`` - every ``calculation_proof`` input of
    kind ``fact``, at any depth.

A row sourced from ``sec_companyfacts.json`` must satisfy one of:

  * the row unit's currency appears among the source concept's unit keys, or
  * the row carries an ``fx_conversion`` block whose ``from_currency`` matches a
    source unit key and whose ``to_currency`` matches the row unit.

Anything else is the NVO corruption (DKK values locked as "USD millions", found
2026-08-09): the number is in one currency and the label in another. Scanning
the ledger alone missed the ASML case, where the ledger was corrected but the
proof inputs the model reads kept the raw EUR figures - a validator green on
data it never looked at. Exit code 1 when any mismatch is found in either
surface. Output is ASCII-only.

COVERAGE. A monetary row whose source is NOT sec_companyfacts.json (a PDF or HTM
locator, a filing_facts extract) has no unit key to compare against, so it is
skipped - about 10% of proof inputs. Skipping is unavoidable; skipping silently
is not, because "0 mismatches" then reads as "everything checked" when a tenth of
the monetary surface was never looked at. Every skip is counted in the summary and
broken down by source file, and `--show-skipped` lists the rows. `--fail-on-skipped`
turns the coverage gap itself into a non-zero exit for a caller that wants it.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ISO_CURRENCY = re.compile(r"^[A-Z]{3}$")


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def unit_currency(unit: str) -> str | None:
    """ISO currency of a ledger unit ("USD millions") or unit key ("DKK", "EUR/shares")."""
    base = str(unit).split("/", 1)[0].split()[0].strip() if str(unit).strip() else ""
    return base if ISO_CURRENCY.match(base) else None


def concept_currencies(companyfacts: dict, locator: str) -> set[str] | None:
    """Currencies among the unit keys of the concept a ledger locator points at.

    Returns None when the locator does not resolve to a companyfacts concept
    (renamed tag, stale evidence file), which is reported as unverifiable
    rather than as a mismatch.
    """
    head = str(locator).split(";", 1)[0].strip()
    if ":" not in head:
        return None
    namespace, tag = head.split(":", 1)
    record = ((companyfacts.get("facts") or {}).get(namespace.strip()) or {}).get(tag.strip())
    if not record:
        return None
    found = {unit_currency(key) for key in (record.get("units") or {})}
    return {currency for currency in found if currency}


def iter_calculation_proofs(node):
    """Yield every ``calculation_proof`` dict anywhere in a valuation model.

    Walking the whole tree rather than one known path is deliberate: component
    schedules are nested differently across schema versions and overlays, and a
    scan that only knows one path is blind to the file it is meant to check.
    """
    if isinstance(node, dict):
        proof = node.get("calculation_proof")
        if isinstance(proof, dict):
            yield proof
        for value in node.values():
            yield from iter_calculation_proofs(value)
    elif isinstance(node, list):
        for value in node:
            yield from iter_calculation_proofs(value)


def check_row(unit: str, fx: dict | None, currencies: set[str] | None) -> tuple[str, str] | None:
    """Return ``(claimed, actual)`` when the row's currency label contradicts its source.

    Returns None when the row is consistent; callers handle ``currencies`` of
    None/empty (unverifiable) before getting here.
    """
    row_currency = unit_currency(str(unit or ""))
    if row_currency is None or not currencies:
        return None
    fx = fx or {}
    if fx:
        if fx.get("from_currency") in currencies and fx.get("to_currency") == row_currency:
            return None
        return (f"{row_currency} via fx {fx.get('from_currency')}->{fx.get('to_currency')}",
                "/".join(sorted(currencies)))
    if row_currency not in currencies:
        return (str(unit), "/".join(sorted(currencies)))
    return None


def _resolve(ref: str, locator: str, cache: dict) -> set[str] | None:
    if ref not in cache:
        cache[ref] = read_json(ROOT / ref)
    return concept_currencies(cache[ref], locator)


def _source_kind(ref: str) -> str:
    """Coarse label for a non-companyfacts source, for the skipped-row breakdown."""
    name = ref.rsplit("/", 1)[-1] or ref
    if not name:
        return "(no source ref)"
    if name.startswith("filing_facts_"):
        return "filing_facts_*.json"
    return name


def scan_ledgers() -> tuple[list, list, list, int]:
    mismatches, unverifiable, skipped, checked = [], [], [], 0
    for ledger_path in sorted(ROOT.glob("*/research/valuation_fact_ledger.json")):
        ticker = ledger_path.parents[1].name
        ledger = read_json(ledger_path)
        cache: dict[str, dict] = {}
        for row in ledger.get("facts") or []:
            if row.get("locked") is not True:
                continue
            source = row.get("source") or {}
            ref = str(source.get("ref") or "")
            if unit_currency(str(row.get("unit") or "")) is None:
                continue  # non-monetary fact (shares etc.)
            if not ref.endswith("sec_companyfacts.json"):
                # Monetary, but the source exposes no unit key to check against.
                skipped.append((ticker, f"ledger {row.get('field_id')}", _source_kind(ref)))
                continue
            field_id = f"ledger {row.get('field_id')}"
            currencies = _resolve(ref, str(source.get("locator") or ""), cache)
            if currencies is None:
                unverifiable.append((ticker, field_id, "locator does not resolve in companyfacts"))
                continue
            if not currencies:
                unverifiable.append((ticker, field_id, "source concept has no monetary unit key"))
                continue
            checked += 1
            problem = check_row(row.get("unit"), row.get("fx_conversion"), currencies)
            if problem:
                mismatches.append((ticker, field_id, *problem))
    return mismatches, unverifiable, skipped, checked


def scan_proofs() -> tuple[list, list, list, int]:
    mismatches, unverifiable, skipped, checked = [], [], [], 0
    for model_path in sorted(ROOT.glob("*/research/valuation.json")):
        ticker = model_path.parents[1].name
        cache: dict[str, dict] = {}
        for proof in iter_calculation_proofs(read_json(model_path)):
            method_id = str(proof.get("method_id") or "proof")
            for row in proof.get("inputs") or []:
                if not isinstance(row, dict) or row.get("kind") != "fact":
                    continue
                source = row.get("source") or {}
                ref = str(source.get("ref") or "")
                if unit_currency(str(row.get("unit") or "")) is None:
                    continue  # non-monetary input (shares etc.)
                if not ref.endswith("sec_companyfacts.json"):
                    # Monetary, but the source exposes no unit key to check against.
                    skipped.append((ticker, f"proof {method_id}.{row.get('id')}", _source_kind(ref)))
                    continue
                node_id = f"proof {method_id}.{row.get('id')}"
                currencies = _resolve(ref, str(source.get("locator") or ""), cache)
                if currencies is None:
                    unverifiable.append((ticker, node_id, "locator does not resolve in companyfacts"))
                    continue
                if not currencies:
                    unverifiable.append((ticker, node_id, "source concept has no monetary unit key"))
                    continue
                checked += 1
                problem = check_row(row.get("unit"), row.get("fx_conversion"), currencies)
                if problem:
                    mismatches.append((ticker, node_id, *problem))
    return mismatches, unverifiable, skipped, checked


def scan(show_skipped: bool = False, fail_on_skipped: bool = False) -> int:
    ledger_mismatches, ledger_unverifiable, ledger_skipped, ledger_checked = scan_ledgers()
    proof_mismatches, proof_unverifiable, proof_skipped, proof_checked = scan_proofs()
    mismatches = ledger_mismatches + proof_mismatches
    unverifiable = ledger_unverifiable + proof_unverifiable
    skipped = ledger_skipped + proof_skipped
    for ticker, field_id, row_unit, source_unit in mismatches:
        print(f"MISMATCH {ticker} {field_id}: says '{row_unit}' but companyfacts reports {source_unit}")
    if unverifiable:
        print(f"NOTE: {len(unverifiable)} companyfacts-sourced row(s) could not be verified (stale or renamed concepts):")
        for ticker, field_id, reason in unverifiable:
            print(f"  UNVERIFIABLE {ticker} {field_id}: {reason}")

    checked = ledger_checked + proof_checked
    if skipped:
        # Never silent: "0 mismatches" over a partial surface is not a clean bill of
        # health, and the reader cannot tell the difference without this line.
        by_kind: dict[str, int] = {}
        for _, _, kind in skipped:
            by_kind[kind] = by_kind.get(kind, 0) + 1
        denom = checked + len(skipped)
        share = (100.0 * len(skipped) / denom) if denom else 0.0
        print(f"SKIPPED {len(skipped)} monetary row(s) ({share:.1f}% of "
              f"{denom} monetary rows: {len(ledger_skipped)} ledger, {len(proof_skipped)} proof) - "
              f"source is not sec_companyfacts.json, so there is no unit key to check against:")
        for kind, count in sorted(by_kind.items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"  SKIPPED-SOURCE {kind}: {count}")
        if show_skipped:
            for ticker, field_id, kind in skipped:
                print(f"  SKIPPED {ticker} {field_id}: source {kind}")
        else:
            print("  (re-run with --show-skipped to list them)")

    print(f"Checked {ledger_checked} locked fact-ledger row(s) and {proof_checked} calculation_proof input(s); "
          f"{len(mismatches)} mismatch(es), {len(skipped)} skipped for lack of a source unit key.")
    if mismatches:
        return 1
    return 1 if (fail_on_skipped and skipped) else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--show-skipped", action="store_true",
                        help="list every monetary row skipped for lack of a source unit key")
    parser.add_argument("--fail-on-skipped", action="store_true",
                        help="exit 1 on the coverage gap too, not only on a mismatch")
    args = parser.parse_args()
    return scan(show_skipped=args.show_skipped, fail_on_skipped=args.fail_on_skipped)


if __name__ == "__main__":
    raise SystemExit(main())
