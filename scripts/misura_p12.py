#!/usr/bin/env python3
"""Misura P12 — funding: regime e timing (protocollo della catena).

PROTOCOLLO (pre-registrato PRIMA di ogni numero; voce P12 di prove/REGISTRO_ESPERIMENTI.md
e spec coda_catena/P12_funding_regime.md)
===========================================================================
- Dati: archivio P8 ``data/funding_xperp.jsonl`` (10 X-Perp OKX EEA, dal 2026-06-29).
- H1 persistenza: p1b = P(next>0 | media3>0) vs base rate; autocorr lag-1 (IC90 bootstrap).
- H2 netto: netto@30g con C = 0,40% (X-Perp) e 0,62% (stress); payback <= 45g.
- H3 stabilita: rho di Spearman tra le due meta' del calendario (>= 0,5, inversioni <= 2).
- RULE: ingresso media3>0 / uscita primo negativo vs always-on (funding-only, NESSUN P&L
  di prezzo); successo: quota >= 85% del flusso E riduzione DD >= 50%.
- Griglia: UNICA variante (soglia 0, uscita 1 negativo); orizzonti {7,14,30,60,90} tutti
  riportati; timing intraday dichiarato morto per aritmetica (non misurato).
- Esiti ammessi: {descrittiva solida, insufficiente, archiviata-al-netto} — MAI "promossa".
Artefatti: ``prove/P12_funding_regime.{txt,json}``.

Uso: python scripts/misura_p12.py [path_jsonl]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

for _antenato in Path(__file__).resolve().parents:
    _src = _antenato / "src"
    if (_src / "money" / "__init__.py").exists():
        if str(_src) not in sys.path:
            sys.path.insert(0, str(_src))
        break

from money.ricerca import funding_regime as fr  # noqa: E402


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    path = sys.argv[1] if len(sys.argv) > 1 else str(root / "data" / "funding_xperp.jsonl")
    serie, malformate = fr.carica_serie(path)
    if not serie:
        print("archivio vuoto: niente da misurare", file=sys.stderr)
        return 2
    risultato = fr.valuta(serie)
    testo = fr.report_testo(risultato, malformate)
    out_txt = root / "prove" / "P12_funding_regime.txt"
    out_json = root / "prove" / "P12_funding_regime.json"
    out_txt.write_text(testo, encoding="utf-8")
    out_json.write_text(fr.report_json(risultato, malformate) + "\n", encoding="utf-8")
    print(testo)
    print("artefatti: %s | %s" % (out_txt, out_json))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
