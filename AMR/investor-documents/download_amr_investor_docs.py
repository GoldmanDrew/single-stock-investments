#!/usr/bin/env python3
"""Download AMR investor documents via shared Marvin script."""
import subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
subprocess.check_call([
    sys.executable,
    str(ROOT / "_system" / "scripts" / "download_us_investor_docs.py"),
    "--ticker", "AMR",
])
