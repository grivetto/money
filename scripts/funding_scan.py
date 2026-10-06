#!/usr/bin/env python3
"""Entrypoint S2 — funding scan sugli X-Perp OKX EEA (spec docs/24).

PROTOCOLLO (dichiarato PRIMA dei numeri, docs/24_S2_ricerca_funding_scan.md)
============================================================================
- Dati: archivio ``data/funding_xperp.jsonl`` (raccoglitore del funding
  X-Perp OKX EEA; una riga per (simbolo, ts ms), campo `funding` =
  frazione per periodo).
- Misura: per simbolo, n osservazioni, funding medio/mediano giornaliero
  (giorni dagli ts reali, UTC), rendimento NETTO annualizzato dopo fee
  entrata+uscita (giro misto `money.costi`) e slippage dichiarato, con
  1 ciclo di apertura/chiusura al mese; frazione di giorni positivi per
  lato short, persistenza (autocorrelazione lag-1), giorni di storia.
- Criteri di lettura (NON promozione): persistenza > 0, n >= 60 giorni,
  netto > 0 dopo costi; |funding giornaliero| > 0,5% = "da verificare"
  (possibile errore dati, non edge).

Artefatti: ``prove/funding_scan_<YYYYMMDD>.{txt,json}``.
Uso: python scripts/funding_scan.py [percorso_jsonl] [--outdir DIR]
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Optional, Sequence

for _antenato in Path(__file__).resolve().parents:
    _src = _antenato / "src"
    if (_src / "money" / "__init__.py").exists():
        if str(_src) not in sys.path:
            sys.path.insert(0, str(_src))
        break

from money.ricerca import funding_scan as fs  # noqa: E402


def main(argv: Optional[Sequence[str]] = None) -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="S2 — funding scan X-Perp OKX EEA (descrittivo, NON promozione)")
    parser.add_argument("percorso", nargs="?",
                        default=str(root / "data" / "funding_xperp.jsonl"),
                        help="archivio JSONL (default: data/funding_xperp.jsonl)")
    parser.add_argument("--outdir", default=str(root / "prove"),
                        help="cartella di output (default: prove/)")
    args = parser.parse_args(argv)

    try:
        risultato = fs.scansione(args.percorso)
    except FileNotFoundError:
        print(f"archivio non trovato: {args.percorso}", file=sys.stderr)
        return 2
    if risultato["meta"]["n_simboli"] == 0:
        print("archivio vuoto: niente da scansionare", file=sys.stderr)
        return 2

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    oggi = date.today().strftime("%Y%m%d")
    out_txt = outdir / f"funding_scan_{oggi}.txt"
    out_json = outdir / f"funding_scan_{oggi}.json"
    testo = fs.report_testo(risultato)
    out_txt.write_text(testo, encoding="utf-8")
    out_json.write_text(fs.report_json(risultato) + "\n", encoding="utf-8")
    print(testo)
    print("artefatti: %s | %s" % (out_txt, out_json))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
