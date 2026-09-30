#!/usr/bin/env python3
"""Raccoglitore funding X-Perp EEA (P8) — append-only, idempotente, READ-ONLY.

Collezione dei tassi funding degli X-Perp major di OKX EEA nel JSONL di P8
(`data/funding_xperp.jsonl`). Il modulo di raccolta è `money.raccoglitore_funding`
(guardia anti-ordini nel sorgente, 9 test). Nessun percorso di codice invia ordini.

Uso:
  python scripts/raccogli_funding.py                 # incrementale (ultimi 7 giorni)
  python scripts/raccogli_funding.py --giorni 120    # backfill (storia disponibile)
  python scripts/raccogli_funding.py --report 30     # copertura ultimi 30 giorni
"""
import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import ccxt  # noqa: E402

from money.raccoglitore_funding import raccogli_funding_basis, report_copertura  # noqa: E402

SIMBOLI = [
    "BTC/USD:USD-310404",
    "ETH/USD:USD-310404",
    "SOL/USD:USD-310404",
    "DOGE/USD:USD-310404",
    "XRP/USD:USD-310404",
    "ADA/USD:USD-310404",
    "AVAX/USD:USD-310530",
    "DOT/USD:USD-310808",
    "LINK/USD:USD-310523",
    "LTC/USD:USD-310404",
]
OUT = ROOT / "data" / "funding_xperp.jsonl"


def main() -> int:
    ap = argparse.ArgumentParser(description="Raccoglitore funding X-Perp EEA (read-only)")
    ap.add_argument("--giorni", type=int, default=7, help="finestra di raccolta in giorni")
    ap.add_argument("--report", type=int, metavar="GIORNI", help="solo report copertura su N giorni")
    args = ap.parse_args()

    fine = datetime.now(timezone.utc)
    if args.report:
        inizio = fine - timedelta(days=args.report)
        rep = report_copertura(str(OUT), inizio, fine)
        print(f"copertura {args.report}g: righe={rep['righe_totali']} copertura={rep['copertura_pct']}%")
        for sym, v in sorted(rep["simboli"].items()):
            print(f"  {sym:24} n={v['count']:5}  da={datetime.fromtimestamp(v['min_ts']/1000, timezone.utc):%m-%d %H:%M}")
        return 0

    ex = ccxt.okx({"hostname": "eea.okx.com", "enableRateLimit": True})
    inizio = fine - timedelta(days=args.giorni)
    stats = raccogli_funding_basis(ex, SIMBOLI, inizio, fine, str(OUT))
    print(
        f"raccolta {args.giorni}g: scritti={stats['scritti']} "
        f"duplicati={stats['duplicati']} errori={len(stats['errori'])}"
    )
    for err in stats["errori"][:5]:
        print("  ERR:", err)
    return 1 if stats["errori"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
