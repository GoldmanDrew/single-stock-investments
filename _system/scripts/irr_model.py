#!/usr/bin/env python3
"""Legacy wrapper — use marvin_valuation.py instead.

Usage:
  python _system/scripts/irr_model.py --json ICE/research/valuation.json
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MARVIN = ROOT / "_system" / "scripts" / "marvin_valuation.py"


def main() -> None:
    parser = argparse.ArgumentParser(description="Lawrence IRR (delegates to marvin_valuation.py)")
    parser.add_argument("--json", type=Path, help="Path to valuation.json")
    args, rest = parser.parse_known_args()

    cmd = [sys.executable, str(MARVIN), "--json"]
    if args.json:
        cmd.extend(["--file", str(args.json)])
    else:
        parser.error("--json path required")
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
