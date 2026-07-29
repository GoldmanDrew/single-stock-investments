#!/usr/bin/env python3
"""Fetch float % and ADV into index_float_adv.json (Yahoo primary, SEC fallback).

Yahoo: quoteSummary (floatShares, sharesOutstanding) + chart (3mo ADV).
SEC fallback: companyfacts shares outstanding; float ≈ 1 − heldPercentInsiders when
Yahoo float missing but insider % available; else omit float_pct (never invent).

Double-check: when both Yahoo float and shares exist, require 0 < float_pct ≤ 1;
when SEC shares diverge >25% from Yahoo, keep Yahoo float_pct but flag notes.
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import time
import urllib.error
import urllib.request
from datetime import date
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "_system" / "reference" / "market-data" / "fundamentals" / "index_float_adv.json"
HISTORY_OUT = (
    ROOT
    / "_system"
    / "reference"
    / "market-data"
    / "fundamentals"
    / "market_structure_history.json"
)
REGISTRY = ROOT / "_system" / "portfolio" / "registry.json"
MEMBERSHIP = ROOT / "dashboard" / "data" / "index_membership.json"
SEC_TICKERS = ROOT / "_system" / "reference" / "securities" / "sec_company_tickers.json"
# Browser-like UA required for Yahoo crumb + quoteSummary (v10 returns 401 otherwise)
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

sys_path = str(ROOT / "_system" / "scripts")
import sys

sys.path.insert(0, sys_path)

_YAHOO_OPENER: urllib.request.OpenerDirector | None = None
_YAHOO_CRUMB: str | None = None


def _yahoo_session() -> tuple[urllib.request.OpenerDirector, str | None]:
    """Cookie jar + crumb for Yahoo quoteSummary (chart still works unauthenticated)."""
    global _YAHOO_OPENER, _YAHOO_CRUMB
    if _YAHOO_OPENER is not None:
        return _YAHOO_OPENER, _YAHOO_CRUMB
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    try:
        opener.open(
            urllib.request.Request("https://fc.yahoo.com", headers={"User-Agent": UA}),
            timeout=15,
        )
    except Exception:
        pass
    crumb = None
    try:
        crumb = (
            opener.open(
                urllib.request.Request(
                    "https://query1.finance.yahoo.com/v1/test/getcrumb",
                    headers={"User-Agent": UA},
                ),
                timeout=15,
            )
            .read()
            .decode("utf-8")
            .strip()
        )
    except Exception:
        crumb = None
    _YAHOO_OPENER, _YAHOO_CRUMB = opener, crumb
    return opener, crumb


def _get_json(url: str, timeout: float = 25.0, *, auth_yahoo: bool = False) -> dict | None:
    headers = {"User-Agent": UA, "Accept": "application/json"}
    try:
        if auth_yahoo:
            opener, crumb = _yahoo_session()
            if crumb and "crumb=" not in url:
                sep = "&" if "?" in url else "?"
                url = f"{url}{sep}crumb={crumb}"
            req = urllib.request.Request(url, headers=headers)
            with opener.open(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def yahoo_symbol(ticker: str) -> str:
    t = ticker.upper()
    if "." in t and t.count(".") == 1 and not t.endswith(
        (".TO", ".L", ".T", ".ST", ".HK", ".AX", ".PA")
    ):
        return t.replace(".", "-")
    return t


def _epoch_date(value: Any) -> str | None:
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def fetch_yahoo_float_adv(ticker: str) -> dict[str, Any]:
    sym = yahoo_symbol(ticker)
    out: dict[str, Any] = {"ticker": ticker, "yahoo_symbol": sym, "error": None}
    # ADV + price from chart
    chart = _get_json(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=3mo&interval=1d"
    )
    price = None
    adv_shares = None
    mcap = None
    if chart:
        try:
            result = chart["chart"]["result"][0]
            quote = result["indicators"]["quote"][0]
            volumes = quote.get("volume") or []
            closes = quote.get("close") or []
            pairs = [
                (v, c)
                for v, c in zip(volumes, closes)
                if v is not None and c is not None and v > 0 and c > 0
            ]
            pairs = pairs[-60:] if len(pairs) > 60 else pairs
            if pairs:
                adv_shares = sum(v for v, _ in pairs) / len(pairs)
                price = float(pairs[-1][1])
            meta = result.get("meta") or {}
            mpx = meta.get("regularMarketPrice")
            if isinstance(mpx, (int, float)) and mpx > 0:
                price = float(mpx)
            if isinstance(meta.get("marketCap"), (int, float)):
                mcap = float(meta["marketCap"])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            out["error"] = f"chart:{exc}"

    # Float / shares from quoteSummary (requires crumb session)
    qs = _get_json(
        f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{sym}"
        f"?modules=defaultKeyStatistics,summaryDetail,price",
        auth_yahoo=True,
    )
    float_shares = None
    shares_out = None
    insider_pct = None
    shares_short = None
    shares_short_prior = None
    short_percent_float = None
    short_ratio = None
    short_interest_date = None
    short_interest_prior_date = None
    if qs:
        try:
            res = qs["quoteSummary"]["result"][0]
            dks = res.get("defaultKeyStatistics") or {}
            sd = res.get("summaryDetail") or {}
            pr = res.get("price") or {}

            def _raw(node, key):
                v = (node.get(key) or {})
                if isinstance(v, dict):
                    return v.get("raw")
                return v

            float_shares = _raw(dks, "floatShares")
            shares_out = _raw(dks, "sharesOutstanding") or _raw(sd, "sharesOutstanding")
            insider_pct = _raw(dks, "heldPercentInsiders")
            shares_short = _raw(dks, "sharesShort")
            shares_short_prior = _raw(dks, "sharesShortPriorMonth")
            short_percent_float = _raw(dks, "shortPercentOfFloat")
            short_ratio = _raw(dks, "shortRatio")
            short_interest_date = _epoch_date(_raw(dks, "dateShortInterest"))
            short_interest_prior_date = _epoch_date(_raw(dks, "sharesShortPreviousMonthDate"))
            if mcap is None:
                mc = _raw(pr, "marketCap")
                if mc:
                    mcap = float(mc)
            if price is None:
                p = _raw(pr, "regularMarketPrice")
                if p:
                    price = float(p)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            out["error"] = (out.get("error") or "") + f"|qs:{exc}"

    float_pct = None
    notes = []
    if float_shares and shares_out and float(shares_out) > 0:
        float_pct = float(float_shares) / float(shares_out)
        if float_pct > 1.0 or float_pct <= 0:
            notes.append(f"yahoo_float_pct_out_of_range={float_pct:.4f}")
            float_pct = None
    elif shares_out and insider_pct is not None:
        try:
            ins = float(insider_pct)
            if ins > 1.5:
                ins = ins / 100.0
            if 0 <= ins < 1:
                float_pct = max(0.0, min(1.0, 1.0 - ins))
                notes.append("float_approx_1_minus_insider_pct")
        except (TypeError, ValueError):
            pass

    adv_dollar = None
    if adv_shares is not None and price is not None:
        adv_dollar = float(adv_shares) * float(price)

    out.update(
        {
            "float_pct": round(float_pct, 4) if float_pct is not None else None,
            "shares_outstanding": int(shares_out) if shares_out else None,
            "float_shares": int(float_shares) if float_shares else None,
            "short_interest_shares": int(shares_short) if shares_short else None,
            "short_interest_prior_shares": int(shares_short_prior) if shares_short_prior else None,
            "short_percent_float": (
                round(float(short_percent_float), 6)
                if short_percent_float is not None
                else None
            ),
            "days_to_cover": round(float(short_ratio), 2) if short_ratio is not None else None,
            "short_interest_date": short_interest_date,
            "short_interest_prior_date": short_interest_prior_date,
            "adv_shares": round(float(adv_shares), 2) if adv_shares else None,
            "price": round(float(price), 4) if price else None,
            "adv_dollar": round(float(adv_dollar), 2) if adv_dollar else None,
            "market_cap_usd": round(float(mcap), 2) if mcap else None,
            "held_percent_insiders": insider_pct,
            "source": "yahoo_quoteSummary+chart",
            "as_of": date.today().isoformat(),
            "notes": "; ".join(notes) if notes else None,
        }
    )
    return out


def load_sec_cik_map() -> dict[str, str]:
    if not SEC_TICKERS.exists():
        return {}
    try:
        doc = json.loads(SEC_TICKERS.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    # SEC format: {"0": {"cik_str": ..., "ticker": "AAPL", ...}, ...}
    out = {}
    if isinstance(doc, dict):
        for v in doc.values():
            if isinstance(v, dict) and v.get("ticker"):
                cik = str(v.get("cik_str") or v.get("cik") or "").lstrip("0") or "0"
                out[str(v["ticker"]).upper()] = cik.zfill(10)
    return out


def fetch_sec_shares(cik: str) -> int | None:
    """Latest CommonStockSharesOutstanding from companyfacts (fallback)."""
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    doc = _get_json(url, timeout=30.0)
    if not doc:
        return None
    try:
        units = doc["facts"]["dei"]["EntityCommonStockSharesOutstanding"]["units"]["shares"]
    except (KeyError, TypeError):
        try:
            units = doc["facts"]["us-gaap"]["CommonStockSharesOutstanding"]["units"]["shares"]
        except (KeyError, TypeError):
            return None
    if not units:
        return None
    # Prefer most recent filed
    units_sorted = sorted(units, key=lambda x: x.get("end") or x.get("filed") or "", reverse=True)
    for row in units_sorted:
        val = row.get("val")
        if isinstance(val, (int, float)) and val > 0:
            return int(val)
    return None


def priority_tickers(
    only_events: bool,
    max_n: int | None,
    explicit: list[str] | None,
    *,
    only_candidates: bool = False,
) -> list[str]:
    if explicit:
        return [t.upper() for t in explicit]
    reg = json.loads(REGISTRY.read_text(encoding="utf-8")) if REGISTRY.exists() else {}
    holdings = list((reg.get("holdings") or {}).keys())
    event_first: list[str] = []
    cand_first: list[str] = []
    _pred = {
        "inclusion_candidate",
        "deletion_risk",
        "banding_hold",
        "committee_watch",
    }
    if MEMBERSHIP.exists():
        mem = json.loads(MEMBERSHIP.read_text(encoding="utf-8"))
        by = mem.get("by_ticker") or {}
        for t, row in by.items():
            if row.get("confirmed_events") or row.get("news_notes"):
                event_first.append(t)
            for sc in row.get("scorecards") or []:
                if sc.get("status") in _pred:
                    cand_first.append(t)
                    break
        for r in (mem.get("portfolio_summary") or {}).get("predictor_watch") or []:
            if r.get("ticker"):
                cand_first.append(str(r["ticker"]))
    # Dedupe preserve order
    seen = set()
    ordered = []
    lead = cand_first + event_first if only_candidates else event_first + cand_first + holdings
    for t in lead:
        tu = str(t).upper()
        if tu in seen:
            continue
        # US-ish only for Yahoo float
        if "." in tu and tu.split(".")[-1] in {"T", "L", "TO", "ST", "HK", "AX", "PA"}:
            continue
        seen.add(tu)
        ordered.append(tu)
    if only_events:
        ordered = [t for t in ordered if t in {x.upper() for x in event_first}]
    if only_candidates:
        ordered = [t for t in ordered if t in {x.upper() for x in cand_first}]
    if max_n is not None:
        ordered = ordered[:max_n]
    return ordered


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", nargs="*", help="Explicit tickers")
    ap.add_argument("--only-events", action="store_true")
    ap.add_argument(
        "--only-candidates",
        action="store_true",
        help="Prefer inclusion_candidate / banding_hold / committee_watch / deletion_risk",
    )
    ap.add_argument("--max", type=int, default=None)
    ap.add_argument("--sleep", type=float, default=0.15)
    ap.add_argument("--sec-fallback", action="store_true", default=True)
    ap.add_argument("--no-sec-fallback", action="store_true")
    args = ap.parse_args()

    existing = {}
    if OUT.exists():
        try:
            existing = json.loads(OUT.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    by = dict(existing.get("by_ticker") or {})
    history_doc: dict[str, Any] = {}
    if HISTORY_OUT.exists():
        try:
            history_doc = json.loads(HISTORY_OUT.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            history_doc = {}
    history_by = dict(history_doc.get("by_ticker") or {})

    tickers = priority_tickers(
        args.only_events,
        args.max,
        args.tickers,
        only_candidates=args.only_candidates,
    )
    cik_map = load_sec_cik_map() if not args.no_sec_fallback else {}
    print(f"Fetching float/ADV for {len(tickers)} tickers…")

    for i, t in enumerate(tickers):
        row = fetch_yahoo_float_adv(t)
        # SEC shares cross-check / fill
        if not args.no_sec_fallback and cik_map.get(t):
            sec_sh = fetch_sec_shares(cik_map[t])
            if sec_sh:
                y_sh = row.get("shares_outstanding")
                if y_sh and abs(sec_sh - y_sh) / max(y_sh, 1) > 0.25:
                    notes = row.get("notes") or ""
                    note = f"sec_shares={sec_sh} diverges>25% from yahoo={y_sh}"
                    row["notes"] = f"{notes}; {note}".strip("; ")
                    row["sec_shares_outstanding"] = sec_sh
                elif not y_sh:
                    row["shares_outstanding"] = sec_sh
                    row["source"] = (row.get("source") or "") + "+sec_shares"
                    # Recompute float if we have insider approx only
                    if row.get("float_pct") is None and row.get("held_percent_insiders") is not None:
                        try:
                            ins = float(row["held_percent_insiders"])
                            if ins > 1.5:
                                ins /= 100.0
                            row["float_pct"] = round(max(0.0, min(1.0, 1.0 - ins)), 4)
                            row["notes"] = ((row.get("notes") or "") + "; float_from_sec_shares_minus_insider").strip("; ")
                        except (TypeError, ValueError):
                            pass
                time.sleep(args.sleep)  # SEC rate limit courtesy

        # Persist only useful rows (have float, ADV, or reported short interest).
        if (
            row.get("float_pct") is not None
            or row.get("adv_dollar") is not None
            or row.get("short_interest_shares") is not None
        ):
            clean = {
                k: v
                for k, v in row.items()
                if k
                not in {"error", "ticker", "yahoo_symbol", "held_percent_insiders", "market_cap_usd"}
                and v is not None
            }
            if row.get("error"):
                clean["fetch_error"] = row["error"]
            by[t] = clean
            ticker_history = list(history_by.get(t) or [])
            history_dates = {str(item.get("date")) for item in ticker_history}
            float_shares = row.get("float_shares")
            prior_shares = row.get("short_interest_prior_shares")
            prior_date = row.get("short_interest_prior_date")
            if prior_date and prior_shares and prior_date not in history_dates:
                ticker_history.append(
                    {
                        "date": prior_date,
                        "shares_short": int(prior_shares),
                        "short_percent_float": (
                            round(float(prior_shares) / float(float_shares), 6)
                            if float_shares
                            else None
                        ),
                        "source": "yahoo_defaultKeyStatistics",
                    }
                )
            current_shares = row.get("short_interest_shares")
            current_date = row.get("short_interest_date")
            if current_date and current_shares:
                ticker_history = [
                    item for item in ticker_history if str(item.get("date")) != current_date
                ]
                ticker_history.append(
                    {
                        "date": current_date,
                        "shares_short": int(current_shares),
                        "short_percent_float": row.get("short_percent_float"),
                        "days_to_cover": row.get("days_to_cover"),
                        "float_shares": row.get("float_shares"),
                        "source": "yahoo_defaultKeyStatistics",
                    }
                )
            history_by[t] = sorted(
                ticker_history,
                key=lambda item: str(item.get("date") or ""),
            )[-36:]
            print(
                f"  {t}: float_pct={clean.get('float_pct')} "
                f"short_float={clean.get('short_percent_float')} "
                f"adv_dollar={clean.get('adv_dollar')}"
            )
        else:
            print(f"  {t}: skip (no float/ADV) err={row.get('error')}")
        if args.sleep > 0:
            time.sleep(args.sleep)
        if (i + 1) % 20 == 0:
            print(f"  … {i + 1}/{len(tickers)}")

    doc = {
        "as_of": date.today().isoformat(),
        "notes": (
            "Float % and ADV for index float-impact math. Never invent — omit when unknown. "
            "Yahoo primary; SEC sharesOutstanding cross-check/fallback. "
            "Used by index_market_inputs.py as secondary cache."
        ),
        "stale_after_days": 90,
        "by_ticker": dict(sorted(by.items())),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    history_payload = {
        "as_of": date.today().isoformat(),
        "notes": (
            "Reported short-interest snapshots. Short interest is a position snapshot, "
            "not daily short-sale volume. Historical short-percent-of-float uses the "
            "float available at collection time."
        ),
        "by_ticker": dict(sorted(history_by.items())),
    }
    HISTORY_OUT.write_text(
        json.dumps(history_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUT} ({len(by)} tickers)")
    print(f"Wrote {HISTORY_OUT} ({len(history_by)} ticker histories)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
