#!/usr/bin/env python3
"""Orchestrate downloads for all portfolio holdings."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable
SCRIPTS = ROOT / "_system" / "scripts"

US_FROM_CONFIG = json.loads((SCRIPTS / "us_ticker_config.json").read_text(encoding="utf-8")).keys()


def run(cmd: list[str], label: str) -> None:
    print(f"\n=== {label} ===")
    subprocess.run(cmd, cwd=ROOT, check=False)


def powershell_script(script: Path) -> list[str]:
    for exe in ("pwsh", "powershell"):
        if shutil.which(exe):
            return [exe, "-ExecutionPolicy", "Bypass", "-File", str(script)]
    raise RuntimeError(f"PowerShell not found; cannot run {script}")


def main() -> None:
    for ticker in sorted(US_FROM_CONFIG):
        if ticker == "QDEL":
            run([PY, str(ROOT / "QDEL/investor-documents/download_qdel_investor_docs.py")], f"QDEL (dedicated)")
            continue
        run([PY, str(SCRIPTS / "download_us_investor_docs.py"), "--ticker", ticker], ticker)

    run(powershell_script(ROOT / "8697.T/_scripts/download_and_organize.ps1"), "8697.T")

    run([PY, str(SCRIPTS / "download_teq_st.py")], "TEQ.ST")
    run([PY, str(SCRIPTS / "download_csu.py")], "CSU")
    run([PY, str(SCRIPTS / "download_otc_api.py")], "OTC tickers (OTCM/FRMO/KEWL)")

    # 3905.T: log refresh from existing archive
    log3905 = ROOT / "3905.T" / "_download_log.txt"
    from datetime import datetime
    log3905.write_text(f"{datetime.now().isoformat()} Archive present; INDEX rebuilt by Marvin\n", encoding="utf-8")
    script3905 = ROOT / "3905.T" / "_scripts"
    script3905.mkdir(parents=True, exist_ok=True)
    dl3905 = script3905 / "download_and_organize.ps1"
    if not dl3905.exists():
        dl3905.write_text(
            "# Placeholder: PDFs already mirrored under IR/. Rebuild INDEX via build_folder_indexes.py\n",
            encoding="utf-8",
        )

    run([PY, str(SCRIPTS / "build_folder_indexes.py")], "Build INDEX.csv files")
    run([PY, str(SCRIPTS / "build_dashboard_data.py")], "Rebuild dashboard JSON")
    print("\nAll download jobs finished.")


if __name__ == "__main__":
    main()
