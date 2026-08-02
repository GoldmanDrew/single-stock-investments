"""Collect and analyze the August 2024 market/sector event study."""

from __future__ import annotations

import json
import math
import os
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config" / "research_config.json").read_text())
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
OUT = ROOT / "outputs"


def _mkdirs() -> None:
    for path in (RAW, PROCESSED, OUT):
        path.mkdir(parents=True, exist_ok=True)


def collect_yahoo_daily() -> pd.DataFrame:
    import yfinance as yf

    symbols = list(CONFIG["market_symbols"]) + list(CONFIG["sector_symbols"])
    frame = yf.download(
        symbols,
        start=CONFIG["event"]["start"],
        end=CONFIG["event"]["end"],
        auto_adjust=False,
        actions=False,
        group_by="ticker",
        progress=False,
        threads=True,
    )
    rows = []
    for symbol in symbols:
        if isinstance(frame.columns, pd.MultiIndex) and symbol in frame.columns.levels[0]:
            part = frame[symbol].copy()
        elif len(symbols) == 1:
            part = frame.copy()
        else:
            continue
        part.columns = [str(c).lower().replace(" ", "_") for c in part.columns]
        part = part.dropna(subset=["open", "close"], how="all")
        part = part.reset_index().rename(columns={"Date": "date", "Datetime": "date"})
        part["symbol"] = symbol
        rows.append(part)
    if not rows:
        raise RuntimeError("Yahoo Finance returned no daily data")
    out = pd.concat(rows, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"]).dt.tz_localize(None).dt.normalize()
    out.to_csv(RAW / "yahoo_daily_ohlcv.csv", index=False)
    return out


def collect_cboe_vix() -> pd.DataFrame | None:
    url = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
    try:
        frame = pd.read_csv(url)
        frame.columns = [str(c).strip().lower() for c in frame.columns]
        frame["date"] = pd.to_datetime(frame["date"])
        frame.to_csv(RAW / "cboe_vix_history.csv", index=False)
        return frame
    except Exception as exc:
        (OUT / "cboe_vix_error.txt").write_text(
            f"{type(exc).__name__}: {exc}", encoding="utf-8"
        )
        return None


def collect_thetadata_intraday() -> dict[str, object]:
    status: dict[str, object] = {"attempted": False, "files": [], "errors": {}}
    if not os.getenv("THETADATA_API_KEY"):
        status["reason"] = "THETADATA_API_KEY missing"
        return status
    try:
        from thetadata import ThetaClient
    except ImportError:
        status["reason"] = "thetadata package missing"
        return status

    status["attempted"] = True
    client = ThetaClient(dataframe_type="pandas")
    theta_cfg = CONFIG["thetadata"]
    for symbol in ["SPY", "QQQ", "IWM", *CONFIG["sector_symbols"].keys()]:
        try:
            df = client.stock_history_ohlc(
                symbol=symbol,
                interval=theta_cfg["interval"],
                start_date=date(2024, 8, 2),
                end_date=date(2024, 8, 23),
                start_time=theta_cfg["start_time"],
                end_time=theta_cfg["end_time"],
            )
            path = RAW / f"thetadata_{symbol}_1m.parquet"
            df.to_parquet(path)
            status["files"].append(path.name)
        except Exception as exc:
            message = str(exc)
            status["errors"][symbol] = {
                "type": type(exc).__name__,
                "permission_denied": "PERMISSION_DENIED" in message,
            }
            if "PERMISSION_DENIED" in message:
                break
    return status


def collect_databento_intraday() -> dict[str, object]:
    status: dict[str, object] = {"attempted": False, "files": [], "errors": {}}
    if not os.getenv("DATABENTO_API_KEY"):
        status["reason"] = "DATABENTO_API_KEY missing"
        return status
    try:
        import databento as db
    except ImportError:
        status["reason"] = "databento package missing"
        return status

    cfg = CONFIG["databento"]
    status["attempted"] = True
    try:
        client = db.Historical()
        symbols = ["SPY", "QQQ", "IWM", *CONFIG["sector_symbols"].keys()]
        store = client.timeseries.get_range(
            dataset=cfg["dataset"],
            schema=cfg["schema"],
            symbols=symbols,
            stype_in=cfg["stype_in"],
            stype_out="symbol",
            start=cfg["start"],
            end=cfg["end"],
        )
        frame = store.to_df()
        path = RAW / "databento_us_equity_1m.parquet"
        frame.to_parquet(path)
        status["files"].append(path.name)
    except Exception as exc:
        status["errors"]["request"] = {
            "type": type(exc).__name__,
            "message": str(exc)[:300],
        }
    return status


def add_features(daily: pd.DataFrame) -> pd.DataFrame:
    df = daily.copy().sort_values(["symbol", "date"])
    numeric = ["open", "high", "low", "close", "adj_close", "volume"]
    for col in numeric:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    grouped = df.groupby("symbol", group_keys=False)
    df["prior_close"] = grouped["close"].shift(1)
    df["overnight_return"] = df["open"] / df["prior_close"] - 1.0
    df["intraday_return"] = df["close"] / df["open"] - 1.0
    df["close_return"] = grouped["close"].pct_change(fill_method=None)
    df["log_return"] = grouped["close"].transform(lambda s: np.log(s).diff())
    for window in CONFIG["vol_target"]["realized_vol_windows"]:
        df[f"rv_{window}d"] = grouped["log_return"].transform(
            lambda s, w=window: s.rolling(w).std() * math.sqrt(252)
        )
    df["dollar_volume"] = df["close"] * df["volume"]
    df["volume_z20"] = grouped["volume"].transform(
        lambda s: (s - s.rolling(20).mean()) / s.rolling(20).std()
    )
    df["range_pct"] = (df["high"] - df["low"]) / df["prior_close"]
    target = float(CONFIG["vol_target"]["annual_target"])
    max_weight = float(CONFIG["vol_target"]["max_equity_weight"])
    df["vol_target_weight_20d"] = (target / df["rv_20d"]).clip(upper=max_weight)
    df["vol_target_weight_change"] = grouped["vol_target_weight_20d"].diff()
    df["vol_target_sell_proxy"] = (
        -df["vol_target_weight_change"].clip(upper=0) * df["dollar_volume"]
    )
    return df


def event_summary(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    event_date = pd.Timestamp(CONFIG["event"]["event_date"])
    neutral_days = int(CONFIG["event"]["neutral_window_trading_days"])
    event = panel.loc[panel["date"] == event_date].copy()

    rows = []
    for symbol, group in panel.groupby("symbol"):
        group = group.sort_values("date").reset_index(drop=True)
        loc = group.index[group["date"] == event_date]
        if len(loc) == 0:
            continue
        i = int(loc[0])
        before = group.iloc[max(0, i - 20) : i]
        after = group.iloc[i : i + neutral_days + 1]
        row = event.loc[event["symbol"] == symbol].iloc[0].to_dict()
        row.update(
            {
                "pre_event_20d_return": (
                    group.loc[i - 1, "close"] / group.loc[max(0, i - 21), "close"] - 1
                    if i > 0
                    else np.nan
                ),
                "forward_5d_return": (
                    group.loc[min(i + 5, len(group) - 1), "close"] / group.loc[i, "close"] - 1
                ),
                "forward_15d_return": (
                    group.loc[min(i + neutral_days, len(group) - 1), "close"]
                    / group.loc[i, "close"]
                    - 1
                ),
                "event_volume_z_vs_pre20": (
                    (group.loc[i, "volume"] - before["volume"].mean())
                    / before["volume"].std()
                    if len(before) >= 10 and before["volume"].std() > 0
                    else np.nan
                ),
                "post_event_low_return": after["low"].min() / group.loc[i, "close"] - 1,
            }
        )
        rows.append(row)
    summary = pd.DataFrame(rows)

    sectors = summary[summary["symbol"].isin(CONFIG["sector_symbols"])].copy()
    sectors["sector"] = sectors["symbol"].map(CONFIG["sector_symbols"])
    sectors["event_return_rank"] = sectors["close_return"].rank()
    sectors["forward_15d_rank"] = sectors["forward_15d_return"].rank()

    market = summary[summary["symbol"].isin(CONFIG["market_symbols"])].copy()
    market["market"] = market["symbol"].map(CONFIG["market_symbols"])

    sector_daily = panel[panel["symbol"].isin(CONFIG["sector_symbols"])].pivot(
        index="date", columns="symbol", values="close_return"
    )
    breadth = pd.DataFrame(
        {
            "date": sector_daily.index,
            "sector_breadth_positive": (sector_daily > 0).mean(axis=1),
            "sector_dispersion": sector_daily.std(axis=1),
            "sector_mean_return": sector_daily.mean(axis=1),
        }
    ).reset_index(drop=True)
    return market, sectors, breadth


def write_methodology(status: dict[str, object]) -> None:
    text = f"""# August 5, 2024 first-pass dataset

## Data availability

- Databento: `{json.dumps(status["databento"])}`.
- ThetaData: `{json.dumps(status["thetadata"])}`.
- Free fallback: Yahoo daily OHLCV plus official Cboe VIX daily history.

## Current resolution

This first pass is daily and supports event-window and sector comparisons. It
does not yet establish intraday forced-flow exhaustion. That requires entitled
intraday trades/quotes, futures, options, closing-auction, and preferably fund
flow or position data.

## Mechanical proxy

The prototype vol-target weight is `min(1, 10% / 20-day realized volatility)`.
The daily sell proxy is the decrease in this weight multiplied by dollar volume.
It is a sensitivity tool, not an estimate of actual industry AUM or orders.

## Next empirical tests

1. Estimate multiple volatility horizons and rebalance rules, including delayed
   and thresholded rebalancing.
2. Map the inferred equity sale to plausible AUM ranges instead of dollar volume.
3. Test whether proxy deceleration predicts forward returns outside August 2024.
4. Add futures, options, order-book liquidity, auction imbalance, ETF flows, and
   sector constituent breadth.
5. Freeze all parameters before evaluating a holdout event set.
"""
    (OUT / "METHODOLOGY.md").write_text(text, encoding="utf-8")


def write_first_findings(market: pd.DataFrame, sectors: pd.DataFrame) -> None:
    def pct(value: float) -> str:
        return f"{100 * value:.1f}%"

    spy = market.loc[market["symbol"] == "SPY"].iloc[0]
    vix = market.loc[market["symbol"] == "^VIX"].iloc[0]
    worst = sectors.sort_values("close_return").iloc[0]
    best_forward = sectors.sort_values("forward_15d_return", ascending=False).iloc[0]
    correlations = {
        column: sectors[[column, "forward_15d_return"]]
        .corr(method="spearman")
        .iloc[0, 1]
        for column in (
            "close_return",
            "overnight_return",
            "intraday_return",
            "event_volume_z_vs_pre20",
            "vol_target_sell_proxy",
        )
    }
    text = f"""# Initial August 5, 2024 findings

These are descriptive results from one event, not a validated trading rule.

- SPY fell {pct(spy["overnight_return"])} from the prior close to the open, then
  recovered {pct(spy["intraday_return"])} intraday. It gained
  {pct(spy["forward_15d_return"])} over the next 15 trading days.
- The daily VIX series reached an intraday high of {vix["high"]:.2f}; its close was
  {pct(vix["close_return"])} above the prior close. The intraday high must be
  interpreted alongside BIS's evidence of illiquid pre-open option quotes.
- {worst["sector"]} was the weakest sector on the day at
  {pct(worst["close_return"])}. {best_forward["sector"]} had the strongest
  subsequent 15-day return at {pct(best_forward["forward_15d_return"])}.
- Across 11 sector ETFs, the Spearman correlation between the August 5 return and
  the next 15-day return was {correlations["close_return"]:+.3f}; the correlation
  using the overnight return was {correlations["overnight_return"]:+.3f}.
- Event-day volume relative to the prior 20 sessions correlated
  {correlations["event_volume_z_vs_pre20"]:+.3f} with the subsequent 15-day
  sector return. This is directionally consistent with capitulation, but the
  cross-section is tiny and selected after observing an extreme event.
- The prototype vol-target sell proxy correlated
  {correlations["vol_target_sell_proxy"]:+.3f} with the subsequent 15-day sector
  return. This does not validate the proxy and shows why direct flow and intraday
  confirmation are required.

## What the first pass supports

The episode has the qualitative signature worth studying: a severe overnight gap,
very high volume, partial intraday reversal in major growth/risk assets, rapid
volatility normalization, and strong 15-day recovery.

## What it does not support

Daily OHLCV cannot identify the exact time forced selling ended, distinguish
vol-target funds from other sellers, or prove the pre-open beta decision was
executable at the assumed prices. Those questions remain for the entitled
intraday, options, futures, auction, and fund-flow dataset.
"""
    (OUT / "INITIAL_FINDINGS.md").write_text(text, encoding="utf-8")


def make_plots(panel: pd.DataFrame, sectors: pd.DataFrame) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return

    fig, ax = plt.subplots(figsize=(9, 6))
    ax.scatter(
        100 * sectors["close_return"],
        100 * sectors["forward_15d_return"],
        s=55,
        color="#2563eb",
    )
    for row in sectors.itertuples():
        ax.annotate(
            row.symbol,
            (100 * row.close_return, 100 * row.forward_15d_return),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=8,
        )
    ax.axvline(0, color="#94a3b8", linewidth=0.8)
    ax.axhline(0, color="#94a3b8", linewidth=0.8)
    ax.set(
        title="August 5 sector shock versus next 15 trading days",
        xlabel="August 5 close-to-close return (%)",
        ylabel="Forward 15-day return (%)",
    )
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(OUT / "sector_shock_vs_forward_15d.png", dpi=180)
    plt.close(fig)

    window = panel.loc[
        panel["date"].between("2024-07-15", "2024-09-10")
        & panel["symbol"].isin(["SPY", "^VIX"])
    ].copy()
    spy = window.loc[window["symbol"] == "SPY"].set_index("date")
    vix = window.loc[window["symbol"] == "^VIX"].set_index("date")
    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    axes[0].plot(spy.index, 100 * spy["close"] / spy["close"].iloc[0], label="SPY indexed")
    right = axes[0].twinx()
    right.plot(vix.index, vix["close"], color="#dc2626", alpha=0.8, label="VIX close")
    axes[0].axvline(pd.Timestamp("2024-08-05"), color="#111827", linestyle="--")
    axes[0].set_ylabel("SPY (July 15 = 100)")
    right.set_ylabel("VIX")
    axes[0].set_title("Market path and prototype vol-target exposure")
    axes[1].plot(
        spy.index,
        spy["vol_target_weight_20d"],
        color="#7c3aed",
        label="10% target / 20d realized vol",
    )
    axes[1].axvline(pd.Timestamp("2024-08-05"), color="#111827", linestyle="--")
    axes[1].set_ylabel("Prototype equity weight")
    axes[1].grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(OUT / "spy_vix_vol_target_path.png", dpi=180)
    plt.close(fig)


def main() -> None:
    _mkdirs()
    daily = collect_yahoo_daily()
    collect_cboe_vix()
    status = {
        "thetadata": collect_thetadata_intraday(),
        "databento": collect_databento_intraday(),
    }
    (OUT / "collection_status.json").write_text(
        json.dumps(status, indent=2), encoding="utf-8"
    )
    panel = add_features(daily)
    panel.to_csv(PROCESSED / "daily_market_sector_panel.csv", index=False)
    panel.to_parquet(PROCESSED / "daily_market_sector_panel.parquet", index=False)
    market, sectors, breadth = event_summary(panel)
    market.to_csv(OUT / "august_5_market_summary.csv", index=False)
    sectors.to_csv(OUT / "august_5_sector_summary.csv", index=False)
    breadth.to_csv(OUT / "sector_breadth_daily.csv", index=False)
    write_methodology(status)
    write_first_findings(market, sectors)
    make_plots(panel, sectors)
    print(
        json.dumps(
            {
                "daily_rows": len(panel),
                "market_rows": len(market),
                "sector_rows": len(sectors),
                "outputs": str(OUT),
                "data_status": status,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
