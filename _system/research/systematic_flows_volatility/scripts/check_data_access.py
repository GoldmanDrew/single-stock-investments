"""Check research data access without displaying credentials."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "data_access.json"


def main() -> None:
    status: dict[str, object] = {
        "credentials": {
            "DATABENTO_API_KEY": bool(os.getenv("DATABENTO_API_KEY")),
            "THETADATA_API_KEY": bool(os.getenv("THETADATA_API_KEY")),
        },
        "packages": {
            name: importlib.util.find_spec(name) is not None
            for name in ("databento", "thetadata", "yfinance", "pandas", "pyarrow")
        },
    }

    theta = {"client": False, "historical_stock_entitlement": "not_tested"}
    if status["credentials"]["THETADATA_API_KEY"] and status["packages"]["thetadata"]:
        try:
            from datetime import date

            from thetadata import ThetaClient

            client = ThetaClient(dataframe_type="pandas")
            theta["client"] = True
            client.stock_history_ohlc(
                symbol="SPY",
                interval="1m",
                date=date(2024, 8, 5),
                start_time="09:30:00",
                end_time="09:31:00",
            )
            theta["historical_stock_entitlement"] = "available"
        except Exception as exc:
            message = str(exc)
            theta["historical_stock_entitlement"] = (
                "permission_denied" if "PERMISSION_DENIED" in message else "error"
            )
            theta["error_type"] = type(exc).__name__
    status["thetadata"] = theta

    databento = {"client": False}
    if status["credentials"]["DATABENTO_API_KEY"] and status["packages"]["databento"]:
        try:
            import databento as db

            db.Historical()
            databento["client"] = True
        except Exception as exc:
            databento["error_type"] = type(exc).__name__
    else:
        databento["reason"] = "missing_key_or_package"
    status["databento"] = databento

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(json.dumps(status, indent=2))


if __name__ == "__main__":
    main()

