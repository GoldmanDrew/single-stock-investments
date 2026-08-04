#!/usr/bin/env python3
"""Fetch crypto network / stablecoin context panels into market-data/crypto/."""
from __future__ import annotations

import argparse
import csv
import json
import math
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
CONFIG = SCRIPTS / "crypto_panel_config.json"
CRYPTO_DIR = ROOT / "_system" / "reference" / "market-data" / "crypto"
BTC_SEED_PRE_YAHOO = CRYPTO_DIR / "btc_spot_usd_seed_pre_yahoo.csv"
UA = "MarvinResearch/1.0 (crypto-panel)"
TODAY = date.today().isoformat()
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
MEMPOOL = "https://mempool.space/api"
COINGECKO = "https://api.coingecko.com/api/v3"
BLOCKCHAIN_CHARTS = "https://api.blockchain.info/charts"


def load_config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def _get_json(url: str, timeout: int = 30) -> dict | list | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    except Exception:
        return None


def read_csv_series(path: Path) -> list[tuple[str, float]]:
    if not path.exists():
        return []
    rows: list[tuple[str, float]] = []
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        parts = line.split(",")
        if len(parts) >= 2:
            try:
                rows.append((parts[0].strip(), float(parts[1])))
            except ValueError:
                continue
    rows.sort()
    return rows


def write_csv(path: Path, rows: list[tuple[str, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "value"])
        for d, v in sorted(rows):
            w.writerow([d, v])


def fetch_yahoo_chart(
    symbol: str,
    *,
    history_start: str | None = None,
    lookback_days: int = 400,
    interval: str = "1d",
) -> tuple[list[tuple[str, float]], str | None]:
    from datetime import timedelta

    end = datetime.now(timezone.utc)
    if history_start:
        try:
            start = datetime.fromisoformat(history_start).replace(tzinfo=timezone.utc)
        except ValueError:
            start = end - timedelta(days=lookback_days)
    else:
        start = end - timedelta(days=lookback_days)
    url = (
        f"{YAHOO_CHART_URL}/{symbol}?period1={int(start.timestamp())}"
        f"&period2={int(end.timestamp())}&interval={interval}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        payload = json.loads(urllib.request.urlopen(req, timeout=45).read())
        result = payload["chart"]["result"][0]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
    except Exception:
        return [], "network"
    rows: list[tuple[str, float]] = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        d = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        rows.append((d, float(close)))
    rows.sort()
    return rows, (None if rows else "empty")


def fetch_yahoo_daily(symbol: str) -> tuple[list[tuple[str, float]], str | None]:
    """Backward-compatible wrapper (last ~400 daily closes)."""
    return fetch_yahoo_chart(symbol, lookback_days=400, interval="1d")


def fetch_coingecko_btc_history() -> tuple[list[tuple[str, float]], str | None]:
    """Daily BTC USD history from CoinGecko (covers pre-Yahoo era)."""
    data = _get_json(f"{COINGECKO}/coins/bitcoin/market_chart?vs_currency=usd&days=max")
    if not data or not isinstance(data, dict):
        return [], "network"
    rows: list[tuple[str, float]] = []
    for pair in data.get("prices") or []:
        if not isinstance(pair, (list, tuple)) or len(pair) < 2:
            continue
        try:
            ts_ms = float(pair[0])
            px = float(pair[1])
        except (TypeError, ValueError):
            continue
        if px <= 0:
            continue
        d = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")
        rows.append((d, px))
    # Keep last close per calendar day
    by_day: dict[str, float] = {}
    for d, v in rows:
        by_day[d] = v
    out = sorted(by_day.items())
    return out, (None if out else "empty")


def fetch_blockchain_btc_history(*, before: str = "2014-09-17") -> tuple[list[tuple[str, float]], str | None]:
    """Long BTC USD history from blockchain.info charts (sampled)."""
    data = _get_json(f"{BLOCKCHAIN_CHARTS}/market-price?timespan=all&format=json")
    if not data or not isinstance(data, dict):
        return [], "network"
    by_day: dict[str, float] = {}
    for rec in data.get("values") or []:
        if not isinstance(rec, dict):
            continue
        try:
            ts = int(rec["x"])
            px = float(rec["y"])
        except (KeyError, TypeError, ValueError):
            continue
        if px <= 0:
            continue
        d = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        if d >= before:
            continue
        by_day[d] = px
    out = sorted(by_day.items())
    return out, (None if out else "empty")


def load_btc_seed_pre_yahoo() -> list[tuple[str, float]]:
    return read_csv_series(BTC_SEED_PRE_YAHOO)


def merge_btc_backfill(
    live_rows: list[tuple[str, float]],
    *,
    mode: str | None,
) -> tuple[list[tuple[str, float]], str]:
    """Merge Yahoo/live rows with seed and optional remote backfill."""
    merged: dict[str, float] = {}
    tags: list[str] = []
    seed = load_btc_seed_pre_yahoo()
    if seed:
        merged.update(seed)
        tags.append("seed_pre_yahoo")
    if mode in ("coingecko_btc", "seed_pre_yahoo", "blockchain_btc"):
        # Prefer live remote backfill when reachable; seed already applied
        if mode == "coingecko_btc":
            remote, _err = fetch_coingecko_btc_history()
            if remote:
                merged.update({d: v for d, v in remote if d < "2014-09-17"})
                tags.append("coingecko")
        remote_bc, _err_bc = fetch_blockchain_btc_history()
        if remote_bc:
            # Fill gaps only; do not overwrite denser seed/remote
            for d, v in remote_bc:
                merged.setdefault(d, v)
            tags.append("blockchain.info")
    merged.update({d: v for d, v in live_rows})
    label = "+".join(tags) if tags else "none"
    return sorted(merged.items()), label


def fetch_amzn_weekly() -> tuple[list[tuple[str, float]], str | None]:
    """Weekly AMZN closes from IPO week (HK snowball comparison series)."""
    return fetch_yahoo_chart(
        "AMZN",
        history_start="1997-05-15",
        interval="1wk",
    )


def write_amzn_weekly(offline: bool = False) -> Path:
    equity_dir = ROOT / "_system" / "reference" / "market-data" / "equity"
    path = equity_dir / "amzn_weekly_usd.csv"
    cached = read_csv_series(path)
    if offline:
        return path
    rows, _err = fetch_amzn_weekly()
    if not rows and cached:
        rows = cached
    if rows:
        merged = {d: v for d, v in cached}
        merged.update({d: v for d, v in rows})
        write_csv(path, sorted(merged.items()))
    return path


def fetch_mempool_hashrate(period: str = "1w") -> tuple[list[tuple[str, float]], str | None]:
    data = _get_json(f"{MEMPOOL}/v1/mining/hashrate/{period}")
    if not data or not isinstance(data, dict):
        return [], "network"
    rows: list[tuple[str, float]] = []
    for rec in data.get("hashrates") or []:
        if not isinstance(rec, dict):
            continue
        ts = rec.get("timestamp")
        hr = rec.get("avgHashrate")
        if ts is None or hr is None:
            continue
        d = datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
        rows.append((d, float(hr) / 1e18))
    if not rows and data.get("currentHashrate"):
        rows = [(TODAY, float(data["currentHashrate"]) / 1e18)]
    rows.sort()
    return rows, (None if rows else "empty")


def fetch_mempool_difficulty() -> tuple[list[tuple[str, float]], str | None]:
    data = _get_json(f"{MEMPOOL}/v1/mining/hashrate/1w")
    if not data or not isinstance(data, dict):
        return [], "network"
    try:
        diff = float(data.get("currentDifficulty") or 0)
        if diff <= 0:
            return [], "empty"
        return [(TODAY, diff)], None
    except (TypeError, ValueError):
        return [], "parse_error"


def fetch_mempool_fees_usd(btc_price: float) -> tuple[list[tuple[str, float]], str | None]:
    blocks = _get_json(f"{MEMPOOL}/blocks/tip/height")
    if not blocks:
        return [], "network"
    # use recommended fees * avg tx as rough proxy; fallback fixed estimate from mempool
    fees = _get_json(f"{MEMPOOL}/v1/fees/mempool-blocks")
    if not fees or not isinstance(fees, list):
        return [(TODAY, 0.05 * btc_price)], "estimate"
    total_fee_sat = 0
    n = 0
    for blk in fees[:6]:
        try:
            total_fee_sat += float(blk.get("totalFees") or 0)
            n += 1
        except (TypeError, ValueError):
            continue
    if n == 0:
        return [(TODAY, 0.05 * btc_price)], "estimate"
    avg_fee_btc = (total_fee_sat / n) / 1e8
    return [(TODAY, round(avg_fee_btc * btc_price, 4))], None


def fetch_coingecko(coin_id: str, metric: str) -> tuple[list[tuple[str, float]], str | None]:
    data = _get_json(f"{COINGECKO}/coins/{coin_id}?localization=false&tickers=false&community_data=false&developer_data=false")
    if not data:
        return [], "network"
    md = data.get("market_data") or {}
    if metric == "market_cap":
        val = (md.get("market_cap") or {}).get("usd")
    elif metric == "circulating_supply":
        val = md.get("circulating_supply")
        if val and (md.get("current_price") or {}).get("usd"):
            val = float(val) * float(md["current_price"]["usd"]) / 1e9
            return [(TODAY, round(val, 3))], None
    else:
        return [], "unknown_metric"
    if val is None:
        return [], "empty"
    return [(TODAY, round(float(val) / 1e9, 3))], None


def latest_from_rows(rows: list[tuple[str, float]]) -> tuple[float | None, str | None]:
    if not rows:
        return None, None
    d, v = rows[-1]
    return v, d


def yoy(rows: list[tuple[str, float]]) -> tuple[float | None, float | None]:
    if len(rows) < 2:
        return None, None
    latest_d, latest_v = rows[-1]
    try:
        target = date.fromisoformat(latest_d).replace(year=date.fromisoformat(latest_d).year - 1)
    except ValueError:
        return None, None
    prior = None
    for d, v in rows:
        if d <= target.isoformat():
            prior = v
    if prior is None or prior == 0:
        return None, None
    return prior, round(100.0 * (latest_v - prior) / abs(prior), 1)


def compute_hashprice(
    btc_price: float,
    hash_eh: float,
    fee_usd_per_block: float,
    subsidy_btc: float = 3.125,
) -> float:
    if hash_eh <= 0:
        return 0.0
    ph = hash_eh * 1e6
    blocks_per_day = 144.0
    daily_revenue = blocks_per_day * (subsidy_btc * btc_price + fee_usd_per_block)
    return round(daily_revenue / ph, 6)


def compute_breakeven_kwh(hashprice_ph_day: float, efficiency_j_th: float) -> float:
    hashprice_th_day = hashprice_ph_day / 1000.0
    kwh_per_th_day = (efficiency_j_th / 1000.0) * 24.0 / 1000.0
    if kwh_per_th_day <= 0:
        return 0.0
    return round(hashprice_th_day / kwh_per_th_day, 4)


def process_series(spec: dict, ctx: dict, offline: bool) -> dict:
    sid = spec["id"]
    src = spec.get("source")
    csv_path = CRYPTO_DIR / f"{sid}.csv"
    cached = read_csv_series(csv_path)
    rows: list[tuple[str, float]] = []
    err: str | None = None
    source_label = str(src)

    if offline:
        rows, err = cached, (None if cached else "offline_no_cache")
    elif src == "yahoo_daily":
        rows, err = fetch_yahoo_chart(
            spec.get("yahoo_symbol", ""),
            history_start=spec.get("history_start"),
            lookback_days=int(spec.get("lookback_days") or 400),
            interval=str(spec.get("interval") or "1d"),
        )
        source_label = f"yahoo:{spec.get('yahoo_symbol')}"
        backfill_mode = spec.get("backfill")
        if sid == "btc_spot_usd" and backfill_mode and not offline:
            rows, bf_tag = merge_btc_backfill(rows, mode=str(backfill_mode))
            source_label = f"yahoo:{spec.get('yahoo_symbol')}+{bf_tag}"
        elif backfill_mode == "coingecko_btc" and not offline:
            cg_rows, cg_err = fetch_coingecko_btc_history()
            if cg_rows:
                merged_bf = {d: v for d, v in cg_rows}
                merged_bf.update({d: v for d, v in rows})
                rows = sorted(merged_bf.items())
                source_label = f"yahoo:{spec.get('yahoo_symbol')}+coingecko:bitcoin"
            elif cg_err and not rows:
                err = err or cg_err
    elif src == "mempool_hashrate":
        rows, err = fetch_mempool_hashrate(spec.get("period", "1w"))
        source_label = "mempool.space:hashrate"
    elif src == "mempool_difficulty":
        rows, err = fetch_mempool_difficulty()
        source_label = "mempool.space:difficulty"
    elif src == "mempool_fees":
        btc = ctx.get("btc_spot_usd") or 0.0
        rows, err = fetch_mempool_fees_usd(btc)
        source_label = "mempool.space:fees"
    elif src == "coingecko":
        rows, err = fetch_coingecko(spec.get("coin_id", ""), spec.get("metric", ""))
        source_label = f"coingecko:{spec.get('coin_id')}:{spec.get('metric')}"
    elif src == "computed_hashprice":
        hp = compute_hashprice(
            ctx.get("btc_spot_usd") or 0.0,
            ctx.get("btc_hash_rate_eh") or 0.0,
            ctx.get("btc_avg_fee_per_block_usd") or 0.0,
            float(ctx.get("block_subsidy_btc") or 3.125),
        )
        rows = [(TODAY, hp)]
        source_label = "computed:hashprice"
    elif src == "computed_breakeven":
        hp = ctx.get("btc_hashprice_usd_ph_day") or 0.0
        eff = float(spec.get("efficiency_j_th") or 30)
        rows = [(TODAY, compute_breakeven_kwh(hp, eff))]
        source_label = f"computed:breakeven_{eff}jth"
    else:
        err = f"unknown_source:{src}"

    if not rows and cached:
        rows = cached
        err = err or "reused_cache"
    if rows:
        merged = {d: v for d, v in cached}
        merged.update({d: v for d, v in rows})
        rows = sorted(merged.items())
        write_csv(csv_path, rows)

    latest, as_of = latest_from_rows(rows)
    prior, yoy_pct = yoy(rows)
    stale_days = int(spec.get("staleness_max_days") or 7)
    stale = False
    if as_of:
        try:
            stale = (date.today() - date.fromisoformat(as_of)).days > stale_days
        except ValueError:
            stale = True
    elif latest is None:
        stale = True

    if sid == "btc_spot_usd" and latest is not None:
        ctx["btc_spot_usd"] = latest
    if sid == "btc_hash_rate_eh" and latest is not None:
        ctx["btc_hash_rate_eh"] = latest
    if sid == "btc_avg_fee_per_block_usd" and latest is not None:
        ctx["btc_avg_fee_per_block_usd"] = latest
    if sid == "btc_hashprice_usd_ph_day" and latest is not None:
        ctx["btc_hashprice_usd_ph_day"] = latest

    direction = "flat"
    if isinstance(yoy_pct, (int, float)):
        if yoy_pct > 1.0:
            direction = "up"
        elif yoy_pct < -1.0:
            direction = "down"

    return {
        "label": spec.get("label"),
        "latest": latest,
        "as_of": as_of,
        "prior_year": prior,
        "yoy_pct": yoy_pct,
        "direction": direction,
        "good_for": spec.get("good_for"),
        "source": source_label,
        "optional": bool(spec.get("optional")),
        "stale": stale,
        "error": err,
        "note": spec.get("note"),
    }


def build(theme_filter: str | None = None, offline: bool = False) -> dict:
    cfg = load_config()
    ctx: dict = {"block_subsidy_btc": cfg.get("block_subsidy_btc", 3.125)}
    manifest: dict = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": TODAY,
        "staleness_max_days": cfg.get("staleness_max_days", 7),
        "disclaimer": "Context only. Crypto metrics inform stance and overlays; never auto-inflate Lawrence base IRR.",
        "themes": {},
    }
    themes = cfg.get("themes") or {}
    for theme_id, theme in themes.items():
        if theme_filter and theme_id != theme_filter:
            continue
        series_out: dict = {}
        # pass 1: base series
        for spec in theme.get("series") or []:
            if spec.get("source", "").startswith("computed_"):
                continue
            series_out[spec["id"]] = process_series(spec, ctx, offline)
        # pass 2: computed
        for spec in theme.get("series") or []:
            if not spec.get("source", "").startswith("computed_"):
                continue
            series_out[spec["id"]] = process_series(spec, ctx, offline)
        manifest["themes"][theme_id] = {
            "label": theme.get("label"),
            "description": theme.get("description"),
            "series": series_out,
        }
    CRYPTO_DIR.mkdir(parents=True, exist_ok=True)
    (CRYPTO_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    # AMZN weekly companion series for HK snowball milestones
    try:
        amzn_path = write_amzn_weekly(offline=offline)
        manifest["amzn_weekly_path"] = str(amzn_path.relative_to(ROOT)).replace("\\", "/")
    except Exception as exc:  # noqa: BLE001 — companion series must not fail crypto panel
        manifest["amzn_weekly_error"] = str(exc)
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--theme", help="Single theme id")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--skip-snowball", action="store_true", help="Do not rebuild HK snowball model JSON")
    args = ap.parse_args()
    build(args.theme, args.offline)
    print(f"Wrote {CRYPTO_DIR / 'manifest.json'}")
    if not args.skip_snowball:
        try:
            from build_hk_snowball_model import build as build_snowball  # noqa: WPS433

            out = build_snowball()
            print(f"Wrote {out}")
        except Exception as exc:  # noqa: BLE001
            print(f"hk_snowball_model skipped: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
