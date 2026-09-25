#!/usr/bin/env python3
"""Verifica indipendente della curva equity e del drawdown. Strumento diagnostico.

Ricalcola il drawdown dalle operazioni con un ciclo scritto a mano (non con `_equity` del
modulo) e stampa i punti di picco e di valle: un numero di rischio che nessuno ha mai visto
scomposto e' un numero di cui nessuno puo' dire se e' giusto.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_RADICE / "src"))
os.environ.setdefault("MONEY_CACHE", str(_RADICE / "dati_cache"))

from money.dati import Scarica, da_ms                      # noqa: E402
from money.ricerca import trend_lungo as tl                # noqa: E402


def main() -> None:
    s = Scarica()
    serie = {sim: s.serie(sim, tl.TIMEFRAME, tl.INIZIO_STORIA, tl.FINE_STORIA)
             for sim in tl.SIMBOLI}
    esito, per_simbolo = tl.simula_paniere(serie)
    tutte = []
    for sim, r in per_simbolo.items():
        tutte.extend(r.operazioni)
    tutte.sort(key=lambda o: (o.ts_uscita, o.simbolo))

    # Ciclo a mano: nessuna funzione del modulo coinvolta.
    equity = 1.0
    picco = 1.0
    dd_max = 0.0
    i_picco = i_valle = 0
    for k, op in enumerate(tutte):
        equity *= (1.0 + op.netto)
        if equity > picco:
            picco = equity
            i_picco = k
        calo = (picco - equity) / picco
        if calo > dd_max:
            dd_max = calo
            i_valle = k
    print(f"operazioni totali: {len(tutte)}")
    print(f"equity finale    : {equity:.6f}  (rendimento di periodo "
          f"{(equity - 1) * 100:+.2f}%)")
    print(f"drawdown massimo : {dd_max * 100:.2f}%  (picco dopo l'operazione {i_picco + 1}, "
          f"valle dopo la {i_valle + 1})")
    print(f"  picco : {da_ms(tutte[i_picco].ts_uscita).date()} dopo {tutte[i_picco].simbolo} "
          f"{tutte[i_picco].netto * 100:+.2f}%")
    print(f"  valle : {da_ms(tutte[i_valle].ts_uscita).date()} dopo {tutte[i_valle].simbolo} "
          f"{tutte[i_valle].netto * 100:+.2f}%")
    print(f"  _equity del modulo: {tl.simula_paniere(serie)[0].max_drawdown * 100:.2f}%")
    print()
    print("lettura a capitale parzialmente investito (capitale per operazione / capitale):")
    frazione = esito.esposizione_media
    print(f"  capitale per operazione assunto: {frazione:.4%} del conto")
    print(f"  drawdown come frazione del conto: {esito.max_drawdown * frazione * 100:.2f}%")
    print(f"  perdita peggiore per operazione : {min(esito.ritorni_netti) * 100:+.2f}% "
          f"= {min(esito.ritorni_netti) * frazione * 100:+.2f}% del conto")


if __name__ == "__main__":
    main()
