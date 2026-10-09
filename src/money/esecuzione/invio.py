"""invio — la primitiva di invio ordini. UNICO punto che chiama `create_order`.

PERCHE' UN MODULO A SE'
=======================
La regola del progetto (Sprint P0, docs/26 §5) e': **un solo componente autorizzato a
usare `create_order`**. Se la primitiva vivesse dentro `coordinatore.py`, e `esecutore.py`
la importasse, si creerebbe un ciclo (`coordinatore` importa `esecutore.cl_ord_id`).
Questo modulo non importa nulla dal resto del package: e' il livello piu' basso.

Chi lo usa: `coordinatore.Coordinatore`, `esecutore.Esecutore` (percorso generico), il
canary (`scripts/canary_carry.py`) e gli script operativi. Nessun altro file deve
contenere la stringa `create_order(`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class Gamba:
    """Una gamba di un ordine: spot, perp o conversione."""
    symbol: str
    side: str                 # buy / sell
    qty: float
    prezzo_limite: float
    cl_ord_id: str
    td_mode: str = ""         # solo perp (cross/isolated)
    reduce_only: bool = False
    tipo: str = "limit"       # limit / market
    filled: float = 0.0
    medio: float = 0.0
    esito: str = ""           # closed / partial / reprice / invio_fallito
    exchange_id: str = ""
    nota: str = ""


def invia_gamba(ex: Any, gamba: Gamba) -> Dict[str, Any]:
    """L'UNICA chiamata a `create_order` di tutto il repository.

    Idempotente: il `cl_ord_id` e' deterministico per intento (`esecutore.cl_ord_id`),
    quindi un retry dopo un timeout riusa lo stesso id e l'exchange deduplica.
    """
    params: Dict[str, Any] = {"clOrdId": gamba.cl_ord_id}
    if gamba.td_mode:
        params["tdMode"] = gamba.td_mode
    if gamba.reduce_only:
        params["reduceOnly"] = True
    return ex.create_order(gamba.symbol, gamba.tipo, gamba.side, gamba.qty,
                           gamba.prezzo_limite, params)
