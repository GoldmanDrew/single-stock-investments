#!/usr/bin/env python3
"""Resolve the quoted currency and minor-unit scale for a listing.

Every per-share number the dashboard renders -- price, component value, entry
hurdles, NAV, distributions -- is quoted in the currency of the listing venue.
The payload used to record that nowhere the renderer could reach, so index.html
prefixed all of them with a dollar sign. This module is the single place that
answers "what units is this number in".

Two separate facts, and both matter:

  currency           ISO 4217 code of the quote (JPY, CAD, GBP...)
  minor_unit_factor  how many quoted units make one major unit

The second one is the dangerous half. LSE equities quote in *pence* (GBp) and
TASE quotes in *agorot* (ILA), so a raw feed number is 100x the major-unit
value. Rendering that with the right symbol but the wrong scale is worse than
rendering it with no symbol at all, because it looks correct.

Resolution order is exchange, then market, then ticker suffix, because that is
their order of reliability in this repo:

  * exchange is specific and correct where present, but 661 US rows leave it
    unset, so it cannot be the only source.
  * market is a coarse bucket. "EU" in particular is a catch-all that currently
    holds HKEX, B3, BMV, BYMA, SGX, TASE, WSE, KLSE, PSE and ATHEX listings, so
    it must never be allowed to imply EUR.
  * the suffix is a last resort and is absent from most tickers (CSU is
    TSX-listed with no suffix at all).

Anything still unresolved returns currency=None with source="unresolved". That
is deliberately not a silent USD default: a caller that cannot name the units
must render the bare number, never a currency symbol it guessed.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OVERRIDES_PATH = ROOT / "_system" / "reference" / "listing_units_overrides.json"

MAJOR = 1
MINOR_100 = 100

# Exchange is checked first. Keys are matched case-insensitively after trimming.
EXCHANGE_UNITS: dict[str, tuple[str, int]] = {
    # North America
    "NYSE": ("USD", MAJOR), "NYSE AMERICAN": ("USD", MAJOR), "NASDAQ": ("USD", MAJOR),
    "NASDAQ CAPITAL MARKET": ("USD", MAJOR), "CBOE": ("USD", MAJOR), "CME": ("USD", MAJOR),
    "OTC": ("USD", MAJOR), "OTC PINK": ("USD", MAJOR), "OTCQX": ("USD", MAJOR),
    "OTCQB": ("USD", MAJOR), "PRIVATE": ("USD", MAJOR),
    "TSX": ("CAD", MAJOR), "TSXV": ("CAD", MAJOR), "CSE": ("CAD", MAJOR),
    # Europe
    "LSE": ("GBP", MINOR_100),          # quoted in pence
    "AIM": ("GBP", MINOR_100),
    "XETRA": ("EUR", MAJOR), "FRANKFURT": ("EUR", MAJOR),
    "EURONEXT PARIS": ("EUR", MAJOR), "EURONEXT AMSTERDAM": ("EUR", MAJOR),
    "EURONEXT BRUSSELS": ("EUR", MAJOR), "EURONEXT LISBON": ("EUR", MAJOR),
    "BORSA ITALIANA": ("EUR", MAJOR), "BME": ("EUR", MAJOR), "ATHEX": ("EUR", MAJOR),
    "NASDAQ STOCKHOLM": ("SEK", MAJOR), "NASDAQ FIRST NORTH": ("SEK", MAJOR),
    "NASDAQ COPENHAGEN": ("DKK", MAJOR), "NASDAQ HELSINKI": ("EUR", MAJOR),
    "OSLO BORS": ("NOK", MAJOR), "SIX": ("CHF", MAJOR), "WSE": ("PLN", MAJOR),
    # Asia-Pacific
    "TSE": ("JPY", MAJOR),              # Tokyo; Toronto is TSX above
    "JPX": ("JPY", MAJOR), "HKEX": ("HKD", MAJOR), "SGX": ("SGD", MAJOR),
    "KLSE": ("MYR", MAJOR), "PSE": ("PHP", MAJOR),  # Philippine Stock Exchange
    "NSE": ("INR", MAJOR), "BSE": ("INR", MAJOR), "KRX": ("KRW", MAJOR),
    "TWSE": ("TWD", MAJOR), "ASX": ("AUD", MAJOR), "NZX": ("NZD", MAJOR),
    # Middle East / Africa / LatAm
    "TASE": ("ILS", MINOR_100),         # quoted in agorot
    "JSE": ("ZAR", MINOR_100),          # quoted in cents
    "B3": ("BRL", MAJOR), "BMV": ("MXN", MAJOR), "BYMA": ("ARS", MAJOR),
}

# Coarse fallback. "EU" is intentionally absent: it is a catch-all bucket in this
# repo's registry, not a currency zone, and guessing EUR from it would mislabel
# Hong Kong, Brazilian, Israeli, Polish and Singaporean listings.
MARKET_UNITS: dict[str, tuple[str, int]] = {
    "US": ("USD", MAJOR), "OTC": ("USD", MAJOR), "CA": ("CAD", MAJOR),
    "JP": ("JPY", MAJOR), "AU": ("AUD", MAJOR), "NZ": ("NZD", MAJOR),
    "UK": ("GBP", MINOR_100), "SE": ("SEK", MAJOR), "NO": ("NOK", MAJOR),
    "DK": ("DKK", MAJOR), "CH": ("CHF", MAJOR), "IN": ("INR", MAJOR),
    "HK": ("HKD", MAJOR), "SG": ("SGD", MAJOR), "KR": ("KRW", MAJOR),
    "TW": ("TWD", MAJOR), "BR": ("BRL", MAJOR), "MX": ("MXN", MAJOR),
    "IL": ("ILS", MINOR_100), "ZA": ("ZAR", MINOR_100), "PL": ("PLN", MAJOR),
}

SUFFIX_UNITS: dict[str, tuple[str, int]] = {
    "T": ("JPY", MAJOR), "TO": ("CAD", MAJOR), "V": ("CAD", MAJOR),
    "HK": ("HKD", MAJOR), "AX": ("AUD", MAJOR), "NZ": ("NZD", MAJOR),
    "L": ("GBP", MINOR_100), "PA": ("EUR", MAJOR), "DE": ("EUR", MAJOR),
    "AS": ("EUR", MAJOR), "BR": ("EUR", MAJOR), "MI": ("EUR", MAJOR),
    "MC": ("EUR", MAJOR), "AT": ("EUR", MAJOR), "HE": ("EUR", MAJOR),
    "ST": ("SEK", MAJOR), "CO": ("DKK", MAJOR), "OL": ("NOK", MAJOR),
    "SW": ("CHF", MAJOR), "SI": ("SGD", MAJOR), "KL": ("MYR", MAJOR),
    "NS": ("INR", MAJOR), "BO": ("INR", MAJOR), "KS": ("KRW", MAJOR),
    "TW": ("TWD", MAJOR), "SA": ("BRL", MAJOR), "MX": ("MXN", MAJOR),
    "TA": ("ILS", MINOR_100), "JO": ("ZAR", MINOR_100), "WA": ("PLN", MAJOR),
}

_PLACEHOLDERS = {"", "-", "—", "–", "?", "N/A", "NA", "NONE", "NULL"}


def _clean(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.upper() in _PLACEHOLDERS else text


def load_overrides(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Reviewed per-ticker exceptions, same convention as security_identity_overrides."""
    target = path or OVERRIDES_PATH
    if not target.exists():
        return {}
    payload = json.loads(target.read_text(encoding="utf-8"))
    return payload.get("tickers") or {}


def resolve_units(
    ticker: str,
    market: Any = None,
    exchange: Any = None,
    *,
    overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return the units block for one listing.

    Never guesses. An unresolved listing reports currency=None so the renderer
    can show a bare number instead of inventing a symbol.
    """
    table = load_overrides() if overrides is None else overrides
    override = table.get(ticker)
    if override and override.get("currency"):
        return {
            "currency": str(override["currency"]).upper(),
            "minor_unit_factor": int(override.get("minor_unit_factor", MAJOR)),
            "source": "override",
            "reason": override.get("reason"),
        }

    exchange_key = _clean(exchange).upper()
    if exchange_key in EXCHANGE_UNITS:
        currency, factor = EXCHANGE_UNITS[exchange_key]
        return {"currency": currency, "minor_unit_factor": factor, "source": "exchange", "reason": None}

    market_key = _clean(market).upper()
    if market_key in MARKET_UNITS:
        currency, factor = MARKET_UNITS[market_key]
        return {"currency": currency, "minor_unit_factor": factor, "source": "market", "reason": None}

    if "." in ticker:
        suffix = ticker.rsplit(".", 1)[-1].upper()
        if suffix in SUFFIX_UNITS:
            currency, factor = SUFFIX_UNITS[suffix]
            return {"currency": currency, "minor_unit_factor": factor, "source": "ticker_suffix", "reason": None}

    return {
        "currency": None,
        "minor_unit_factor": MAJOR,
        "source": "unresolved",
        "reason": f"no units rule for market={market_key or '?'} exchange={exchange_key or '?'}",
    }


def is_minor_unit(units: dict[str, Any] | None) -> bool:
    """True when the quote is in a minor unit (pence, agorot, cents)."""
    return bool(units) and int(units.get("minor_unit_factor") or MAJOR) != MAJOR


def display_currency(units: dict[str, Any] | None) -> str | None:
    """The code a formatter should use, distinguishing GBp from GBP."""
    if not units or not units.get("currency"):
        return None
    currency = str(units["currency"])
    if not is_minor_unit(units):
        return currency
    return {"GBP": "GBp", "ILS": "ILA", "ZAR": "ZAc"}.get(currency, currency)
