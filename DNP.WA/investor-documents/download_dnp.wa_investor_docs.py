#!/usr/bin/env python3
"""Download DNP.WA IR PDFs via shared Marvin IR harvest script."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
subprocess.check_call([
    sys.executable,
    str(ROOT / "_system" / "scripts" / "download_ir_harvest.py"),
    "--ticker",
    "DNP.WA",
])
