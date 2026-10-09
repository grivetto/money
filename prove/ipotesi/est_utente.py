"""Estensione famiglie per lo screener: implementa ipotesi NON presenti nel motore base.

`stato_fn(barre, cfg)` deve rispettare la convenzione del rig: vettore causale di
desiderio di posizione alla CHIUSURA della barra i (True = long da aprire all'apertura
di i+1). None = warmup (nessuna decisione).

Famiglie qui:
  terzo_giorno — "regola del terzo giorno": dopo `disc` ribassi consecutivi si entra,
                 si resta `tieni` barre, poi si esce. (ipotesi classica del proprietario)
"""
from __future__ import annotations

from typing import Optional, Sequence

from money.ricerca import scansione as S

#: famiglie fornite da questa estensione (per il fail-closed dello screener)
FAMIGLIE = ("terzo_giorno",)


def _terzo_giorno(barre: Sequence, cfg: dict) -> list[Optional[bool]]:
    c = [b.chiusura for b in barre]
    disc = int(cfg.get("disc", 3))
    tieni = int(cfg.get("tieni", 5))
    n = len(c)
    stato: list[Optional[bool]] = [None] * n
    i = 1
    while i < n:
        # quante chiusure consecutive in ribasso terminano nella barra i?
        k, j = 0, i
        while j >= 1 and c[j] < c[j - 1]:
            k += 1
            j -= 1
        if k >= disc:
            for t in range(i, min(i + tieni, n)):
                stato[t] = True
            i += tieni
        else:
            stato[i] = False
            i += 1
    return stato


def stato_fn(barre: Sequence, cfg: dict) -> list[Optional[bool]]:
    """Dispatcher: `terzo_giorno` qui, tutto il resto al motore base."""
    fam = cfg.get("famiglia")
    if fam == "terzo_giorno":
        return _terzo_giorno(barre, cfg)
    return S.stato_per_config(barre, cfg)
