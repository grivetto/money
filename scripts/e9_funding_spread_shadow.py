#!/usr/bin/env python3
"""Run the E9 funding-spread backtest (fail-closed) without exchange access.

Provenienza: branco Manus_29_10_26 (29/10/26) — CLI del backtest fail-closed
`money.ricerca.funding_spread`. Il motore di misura ufficiale E9 resta
`scripts/e9_funding_spread.py`; questo CLI serve a riesecuzioni shadow su file
JSONL (read-only, mai ordini).

Usage:
  python scripts/e9_funding_spread_shadow.py funding.jsonl --venue-a bybit --venue-b binance --capital-eur 1000
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Optional, Sequence

for ancestor in Path(__file__).resolve().parents:
    src = ancestor / "src"
    if (src / "money" / "__init__.py").exists():
        sys.path.insert(0, str(src))
        break

from money.ricerca import funding_spread as e9  # noqa: E402


def main(argv: Optional[Sequence[str]] = None) -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="E9 funding spread: backtest/shadow only")
    parser.add_argument("input", nargs="+", help="JSONL file(s): venue, symbol/simbolo, ts ms, funding")
    parser.add_argument("--venue-a", required=True)
    parser.add_argument("--venue-b", required=True)
    parser.add_argument("--capital-eur", type=float, required=True)
    parser.add_argument("--outdir", default=str(root / "prove"))
    args = parser.parse_args(argv)
    if args.capital_eur <= 0:
        parser.error("--capital-eur deve essere positivo")
    if args.venue_a.lower() == args.venue_b.lower():
        parser.error("venue-a e venue-b devono essere diverse")
    try:
        points, malformed, read = e9.load_points(args.input)
    except FileNotFoundError as exc:
        print(f"input non trovato: {exc.filename}", file=sys.stderr)
        return 2
    if not points:
        print("nessun punto valido: misura bloccata", file=sys.stderr)
        return 2
    result = e9.report(points, venue_a=args.venue_a.lower(), venue_b=args.venue_b.lower(),
                       capital_eur=args.capital_eur)
    result["input"] = {"files": args.input, "rows_read": read, "rows_malformed": malformed}
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = date.today().strftime("%Y%m%d")
    out_json = outdir / f"e9_funding_spread_{stamp}.json"
    out_txt = outdir / f"e9_funding_spread_{stamp}.txt"
    out_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    out_txt.write_text(e9.report_text(result), encoding="utf-8")
    print(e9.report_text(result), end="")
    print(f"artefatti: {out_txt} | {out_json}")
    return 0 if result["aggregate"]["t1_t2_t3"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
