#!/usr/bin/env python
"""CLI del lint strutturale spec: python scripts/spec_lint.py <file.md> [--strict] [--json]

Advisory: exit 0 anche con blocchi mancanti; con --strict exit 1 se manca qualcosa.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from money.spec_lint import lint_text, missing  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("file")
    ap.add_argument("--strict", action="store_true", help="exit 1 se manca qualche blocco")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    p = Path(args.file)
    if not p.is_file():
        print("file non trovato: %s" % p, file=sys.stderr)
        return 2
    checks = lint_text(p.read_text(encoding="utf-8"))

    if args.json:
        print(json.dumps({"file": str(p), "checks": checks, "missing": missing(checks)},
                         ensure_ascii=False, indent=1))
    else:
        for c in checks:
            print("%s  %-16s %s" % ("OK  " if c["ok"] else "MANCA", c["check"], c["hint"]))
        miss = missing(checks)
        print("esito: %d/%d blocchi presenti%s" % (
            len(checks) - len(miss), len(checks),
            (" — MANCANO: " + ", ".join(miss)) if miss else ""))
    if args.strict and missing(checks):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
