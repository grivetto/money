#!/usr/bin/env python3
"""Sonda diagnostica: quante operazioni produce l'ipotesi e con che numeri.

NON e' il runner della misura: e' lo strumento con cui si verifica che i parametri fissati
a priori producano abbastanza operazioni perche' il cancello possa giudicare (>= 30). Se
non le producono, il verdetto corretto e' "insufficiente" e va riportato come tale — la
sonda esiste per saperlo prima, non per cambiare i parametri dopo aver visto il risultato.

Convenzione d'uso: si guardano SOLO i conteggi, la durata e i costi. Il giudizio di merito
e' di `cancello`.

Uso:  python scripts/sonda_trend_lungo.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_RADICE = Path(__file__).resolve().parents[1]
_SRC = _RADICE / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
os.environ.setdefault("MONEY_CACHE", str(_RADICE / "dati_cache"))

from money.dati import Scarica, da_ms                                    # noqa: E402
from money.ricerca import trend_lungo as tl                              # noqa: E402


def main() -> None:
    print(f"cache: {os.environ['MONEY_CACHE']}")
    s = Scarica()
    print(f"tariffa assunta: {tl.NOME_TARIFFA} tipo {tl.TIPO_PEDAGGIO} "
          f"-> pedaggio {tl._pedaggio():.5f} per operazione")
    print(f"slippage assunto: {tl._slippage_giro():.5f} per giro "
          f"({tl.SLIPPAGE_PER_LATO:.5f} per lato)")
    print(f"parametri: Donchian{tl.DONCHIAN_INGRESSO} in, canale{tl.USCITA_CANALE} out, "
          f"ATR{tl.ATR_PERIODO}x{tl.ATR_STOP}, stop tempo {tl.STOP_TEMPO}")
    print()
    tot = 0
    for simbolo in tl.SIMBOLI:
        serie = s.serie(simbolo, tl.TIMEFRAME, tl.INIZIO_STORIA, tl.FINE_STORIA)
        esito_sim = tl._simula_simbolo(serie)
        op = esito_sim.operazioni
        tot += len(op)
        netti = [o.netto for o in op]
        lordi = [o.lordo for o in op]
        vinte = [r for r in netti if r > 0]
        print(f"{simbolo:9s} barre {len(serie):5d} "
              f"da {da_ms(serie[0].ts).date()} a {da_ms(serie[-1].ts).date()} "
              f"({esito_sim.giorni_osservati:.0f} gg)")
        print(f"          operazioni {len(op):4d}  "
              f"op/anno {len(op) / (esito_sim.giorni_osservati / 365):6.2f}  "
              f"hit {len(vinte) / len(op) * 100 if op else 0:5.1f}%  "
              f"DD {esito_sim.max_drawdown * 100:6.2f}%")
        if op:
            print(f"          lordo medio {sum(lordi) / len(lordi) * 100:+.3f}%  "
                  f"netto medio {sum(netti) / len(netti) * 100:+.3f}%  "
                  f"migliore {max(netti) * 100:+.2f}%  peggiore {min(netti) * 100:+.2f}%")
            motivi: dict = {}
            for o in op:
                motivi[o.motivo_uscita] = motivi.get(o.motivo_uscita, 0) + 1
            print(f"          uscite: {motivi}")
            print(f"          barre detenute: media "
                  f"{sum(o.barre_detenute for o in op) / len(op):.1f} "
                  f"max {max(o.barre_detenute for o in op)}  "
                  f"esposizione {tl._esposizione_media(serie, op):.3f}")
    print()
    print(f"TOTALE operazioni nel paniere: {tot}")


if __name__ == "__main__":
    main()
