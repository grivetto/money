#!/usr/bin/env python
"""Runner CLI della misura di carry funding (spec: coda_catena/P4_funding_carry.md).

Uso:
    python scripts/carry_netto.py [--path data/funding_xperp.jsonl] [--json] [--out prove/carry]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from money.carry_netto import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
