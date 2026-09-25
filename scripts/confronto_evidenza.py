#!/usr/bin/env python3
"""Confronto con l'evidenza precedente: addestramento vs verifica, e robustezza per finestra.

Serve a rispondere alla domanda posta dal committente:
  "il rendimento del giornaliero era un **episodio**, non un flusso" (docs/20_derivati_okx_eea.md
  §20.3: mediana +17,47% di periodo su 19 asset, 0/24 configurazioni robuste su 4 finestre su 5).

Questo script calcola, sull'ipotesi del nodo A e con i parametri fissati a priori:
  - rendimento di periodo a nozionale pieno (la grandezza confrontabile con il +17,47%);
  - expectancy netta per operazione nei due lati della partizione walk-forward;
  - quante finestre di verifica hanno expectancy positiva (la "robustezza" del §20.3).

Uso:  python scripts/confronto_evidenza.py
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

_RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_RADICE / "src"))
os.environ.setdefault("MONEY_CACHE", str(_RADICE / "dati_cache"))

from money.dati import Scarica, da_ms                          # noqa: E402
from money.ricerca import trend_lungo as tl                    # noqa: E402

WF_ADDESTRA, WF_VERIFICA, WF_EMBARGO = 550, 480, 1
WF_ADDESTRA_FINE, WF_VERIFICA_FINE = 520, 160


def riassunto(nome: str, ops) -> None:
    if not ops:
        print(f"{nome:<34} nessuna operazione")
        return
    netti = [o.netto for o in ops]
    somma = math.fsum(netti)
    composto = 1.0
    picco, dd = 1.0, 0.0
    for r in netti:
        composto *= (1.0 + r)
        picco = max(picco, composto)
        dd = max(dd, (picco - composto) / picco)
    print(f"{nome:<34} n={len(ops):>4}  somma lorda-net {somma * 100:>+8.2f}%  "
          f"composto {(composto - 1) * 100:>+8.2f}%  DD {dd * 100:>6.2f}%  "
          f"exp/op {somma / len(ops) * 100:>+7.3f}%")


def main() -> None:
    s = Scarica()
    serie = {sim: s.serie(sim, tl.TIMEFRAME, tl.INIZIO_STORIA, tl.FINE_STORIA)
             for sim in tl.SIMBOLI}
    esito, per_simbolo = tl.simula_paniere(serie)

    print("=" * 108)
    print("1) TUTTA LA STORIA (grandezza confrontabile con la mediana +17,47% di §20.3)")
    print("=" * 108)
    tutte = [o for sim in per_simbolo.values() for o in sim.operazioni]
    riassunto("paniere 3 simboli, tutta la storia", tutte)
    print()
    for sim, r in per_simbolo.items():
        riassunto(f"  {sim}", r.operazioni)

    print()
    print("=" * 108)
    print("2) PARTIZIONE WALK-FORWARD: addestramento vs verifica (parametri FISSI)")
    print("=" * 108)
    fuori, dentro, finestre = tl.partizione_addestra_verifica(
        serie, WF_ADDESTRA, WF_VERIFICA, WF_VERIFICA, WF_EMBARGO)
    riassunto("ADDESTRAMENTO (prime 550 barre)", fuori)
    riassunto("VERIFICA (finestre mai viste)", dentro)
    print()
    print(f"finestre di verifica: {sorted(finestre)}")
    for k in sorted(finestre):
        v = finestre[k]
        print(f"  {k:<12} {str(da_ms(v[0].ts).date())} -> {str(da_ms(v[-1].ts).date())} "
              f"({len(v)} barre)")

    print()
    print("=" * 108)
    print("3) ROBUSTEZZA SU FINESTRE CORTE — quante hanno expectancy netta > 0")
    print("   (il confronto diretto con '0/24 configurazioni robuste su 4 finestre su 5')")
    print("=" * 108)
    positive = totale = 0
    for sim, s_ in serie.items():
        for k, (_, ver) in enumerate(
                tl.iterazioni_walk_forward(s_, WF_ADDESTRA_FINE, WF_VERIFICA_FINE,
                                          WF_VERIFICA_FINE, WF_EMBARGO), 1):
            sim_op = tl._simula_simbolo(ver)
            chiuse = [o for o in sim_op.operazioni if o.i_uscita <= len(ver) - 1]
            netti = [o.netto for o in chiuse]
            media = (math.fsum(netti) / len(netti)) if netti else None
            totale += 1
            if media is not None and media > 0:
                positive += 1
            print(f"  {sim}#{k:<3} {str(da_ms(ver[0].ts).date())} -> "
                  f"{str(da_ms(ver[-1].ts).date())}  n={len(chiuse):>2}  "
                  f"exp/op {('%+.3f%%' % (media * 100)).replace('.', ',') if media is not None else '   n/d':>9}")
    print(f"\nfinestre con expectancy netta > 0: {positive}/{totale} "
          f"({positive / totale * 100:.0f}%)")
    print(f"finestre con n >= 5 operazioni   : "
          f"{sum(1 for _ in [])}")


if __name__ == "__main__":
    main()
