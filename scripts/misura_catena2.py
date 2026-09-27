#!/usr/bin/env python3
"""Catena 2 Hermes — nodi J-O, sei famiglie ORTOGONALI, stesso protocollo della catena 1.

Nodi: J rotazione forza relativa | K effetto weekend | L momentum assoluto |
      M capitolazione+volume | N breakout con conferma paniere | O reversal 2 giorni.

Protocollo: griglia dichiarata provata TUTTA in addestramento [2023-12-01, 2025-09-01),
scelta per expectancy netta (vincolo n>=30 in training, lezione DSH), verifica su
[2025-09-01, 2026-09-25), `cancello.giudica` (1000 EUR, soglia 10 EUR/anno),
confronta_tariffe verso con_perp e swap_lv1. Verdetti e numeri in prove/ (txt + json).
Non si ritocca niente dopo la verifica: se archivia, archivia.
Uso: `python scripts/misura_catena2.py` (usa la cache della catena 1).
"""
from __future__ import annotations

import sys
from pathlib import Path

for _antenato in Path(__file__).resolve().parents:
    _src = _antenato / "src"
    if (_src / "money" / "__init__.py").exists():
        if str(_src) not in sys.path:
            sys.path.insert(0, str(_src))
        if str(_antenato) not in sys.path:          # radice repo: serve per `import scripts.*`
            sys.path.insert(0, str(_antenato))
        break

from money.ricerca import breakout_paniere as N  # noqa: E402
from money.ricerca import capitolazione_volume as M  # noqa: E402
from money.ricerca import effetto_weekend as K  # noqa: E402
from money.ricerca import momentum_assoluto as L  # noqa: E402
from money.ricerca import reversal_2giorni as O  # noqa: E402
from money.ricerca import rotazione_forza as J  # noqa: E402

# Il runner e' lo stesso della catena 1: si importano le sue parti e gli si cambia la lista.
from scripts.misura_catena_hermes import (  # noqa: E402
    CARTELLA_PROVE, TARIFFE_SCENARIO, carica, giudica_nodo, prima_dopo, _iso, _p, _n)

import json  # noqa: E402
import time  # noqa: E402

from money.dati import Scarica  # noqa: E402

NODI = (
    ("J_rotazione_forza", J),
    ("K_effetto_weekend", K),
    ("L_momentum_assoluto", L),
    ("M_capitolazione_volume", M),
    ("N_breakout_paniere", N),
    ("O_reversal_2giorni", O),
)


def main() -> int:
    t0 = time.time()
    CARTELLA_PROVE.mkdir(parents=True, exist_ok=True)
    scaricatore = Scarica()
    print(f"cache dati: {scaricatore.cartella_cache}")
    print(f"universo: {len(J.SIMBOLI)} coppie EUR, 1d, "
          f"{J.INIZIO_STORIA} -> {J.FINE_STORIA}, confine {J.CONFINE_ADDESTRAMENTO}")

    dati = carica(scaricatore, J.SIMBOLI, "1d", J.INIZIO_STORIA, J.FINE_STORIA,
                  J.COPERTURA_MINIMA)
    if not dati:
        print("DATI INSUFFICIENTI: non si misura niente.")
        return 1
    i_confine = prima_dopo(dati, J.CONFINE_ADDESTRAMENTO)
    confine_reale = _iso(max(dati.values(), key=len)[i_confine].ts)
    print(f"confine effettivo: indice {i_confine} @ {confine_reale}")

    risultati: dict = {}
    for nome, modulo in NODI:
        righe_log: list = []
        esito_nodo = giudica_nodo(nome, modulo, dati, i_confine, righe_log)
        esito_nodo["meta"] = {
            "periodo": [modulo.INIZIO_STORIA, modulo.FINE_STORIA],
            "confine": modulo.CONFINE_ADDESTRAMENTO,
            "confine_reale_iso": confine_reale,
            "universo": sorted(dati.keys()),
            "tariffa": modulo.TARIFFA_ASSUNTA, "tipo": modulo.TIPO_ORDINE,
            "slippage_per_lato": modulo.SLIPPAGE_PER_LATO,
            "esposizione": modulo.ESPOSIZIONE,
        }
        risultati[nome] = esito_nodo
        testo = "\n".join(righe_log)
        print(testo)
        (CARTELLA_PROVE / f"{nome}.txt").write_text(testo + "\n", encoding="utf-8")
        (CARTELLA_PROVE / f"{nome}.json").write_text(
            json.dumps(esito_nodo, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8")

    print("\n=== QUADRO CATENA 2 ===")
    for nome, r in risultati.items():
        v = r["verifica"]
        print(f"  {nome:<24} {v['verdetto']:<16} n={v['operazioni']:>4}  "
              f"exp {_p(v['expectancy_netta'], 4)}  copertura {_n(v['copertura_3x'])}x  "
              f"maxDD {_p(v['max_drawdown'], 1)}")
    print(f"\nprove scritte in {CARTELLA_PROVE} ({time.time() - t0:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
