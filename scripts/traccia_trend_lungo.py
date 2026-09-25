#!/usr/bin/env python3
"""Traccia delle operazioni: entra/esco dove, e per quale motivo. Strumento diagnostico."""
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
    for sim in tl.SIMBOLI:
        serie = s.serie(sim, tl.TIMEFRAME, tl.INIZIO_STORIA, tl.FINE_STORIA)
        b = list(serie)
        r = tl._simula_simbolo(serie)
        print("=" * 110)
        print(f"{sim}  {len(r.operazioni)} operazioni, DD {r.max_drawdown:.2%}")
        print(f"{'#':>2} {'ingresso':>11} {'uscita':>11} {'apert_ing':>10} {'max_da_ing':>10} "
              f"{'prezzo_usc':>10} {'lordo':>8} {'netto':>8} {'barre':>5}  motivo")
        for k, o in enumerate(r.operazioni, 1):
            hi = max(x.massimo for x in b[o.i_ingresso:o.i_uscita + 1])
            print(f"{k:>2} {str(da_ms(o.ts_ingresso).date()):>11} "
                  f"{str(da_ms(o.ts_uscita).date()):>11} {o.prezzo_ingresso:>10.0f} "
                  f"{hi:>10.0f} {o.prezzo_uscita:>10.0f} {o.lordo * 100:>7.2f}% "
                  f"{o.netto * 100:>7.2f}% {o.barre_detenute:>5}  {o.motivo_uscita}")
        if b and r.operazioni:
            ultima = r.operazioni[-1]
            print(f"  ultima uscita {da_ms(ultima.ts_uscita).date()}, "
                  f"fine serie {da_ms(b[-1].ts).date()}")


if __name__ == "__main__":
    main()
