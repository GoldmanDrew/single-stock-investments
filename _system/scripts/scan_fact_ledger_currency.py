#!/usr/bin/env python3
"""Scan locked fact ledgers for currency labels that contradict SEC companyfacts.

For every ``{TICKER}/research/valuation_fact_ledger.json``, each locked fact
sourced from ``sec_companyfacts.json`` must satisfy one of:

  * the ledger unit's currency appears among the source concept's unit keys, or
  * the fact carries an ``fx_conversion`` row whose ``from_currency`` matches a
    source unit key and whose ``to_currency`` matches the ledger unit.

Anything else is the NVO corruption (DKK values locked as "USD millions",
found 2026-08-09): the number is in one currency and the label in another.
Exit code 1 when any mismatch is found. Output is ASCII-only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
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


def scan() -> int:
    mismatches, unverifiable, checked = [], [], 0
    for ledger_path in sorted(ROOT.glob("*/research/valuation_fact_ledger.json")):
        ticker = ledger_path.parents[1].name
        ledger = read_json(ledger_path)
        companyfacts_cache: dict[str, dict] = {}
        for row in ledger.get("facts") or []:
            if row.get("locked") is not True:
                continue
            ref = str((row.get("source") or {}).get("ref") or "")
            if not ref.endswith("sec_companyfacts.json"):
                continue
            ledger_ccy = unit_currency(str(row.get("unit") or ""))
            if ledger_ccy is None:
                continue  # non-monetary fact (shares etc.)
            if ref not in companyfacts_cache:
                companyfacts_cache[ref] = read_json(ROOT / ref)
            currencies = concept_currencies(companyfacts_cache[ref], (row.get("source") or {}).get("locator") or "")
            field_id = str(row.get("field_id"))
            if currencies is None:
                unverifiable.append((ticker, field_id, "locator does not resolve in companyfacts"))
                continue
            if not currencies:
                unverifiable.append((ticker, field_id, "source concept has no monetary unit key"))
                continue
            checked += 1
            fx = row.get("fx_conversion") or {}
            if fx:
                if fx.get("from_currency") in currencies and fx.get("to_currency") == ledger_ccy:
                    continue
                mismatches.append((ticker, field_id, f"{ledger_ccy} via fx {fx.get('from_currency')}->{fx.get('to_currency')}",
                                   "/".join(sorted(currencies))))
                continue
            if ledger_ccy not in currencies:
                mismatches.append((ticker, field_id, str(row.get("unit")), "/".join(sorted(currencies))))
    for ticker, field_id, ledger_unit, source_unit in mismatches:
        print(f"MISMATCH {ticker} {field_id}: ledger says '{ledger_unit}' but companyfacts reports {source_unit}")
    if unverifiable:
        print(f"NOTE: {len(unverifiable)} locked companyfacts fact(s) could not be verified (stale or renamed concepts):")
        for ticker, field_id, reason in unverifiable:
            print(f"  UNVERIFIABLE {ticker} {field_id}: {reason}")
    print(f"Checked {checked} locked companyfacts fact(s); {len(mismatches)} mismatch(es).")
    return 1 if mismatches else 0


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    return scan()


if __name__ == "__main__":
    raise SystemExit(main())
