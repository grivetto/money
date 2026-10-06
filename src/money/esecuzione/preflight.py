"""Preflight: i controlli che un ordine supera PRIMA di esistere.

Ogni controllo e' una tupla (nome, ok, dettaglio) e resta nella risposta: un
preflight negato non dice solo "no", dice PERCHE'. Tocca la rete (exchange):
le eccezioni diventano controlli falliti, non traceback — fermo e' meglio che
rotto, ma muto no.

FAIL-CLOSED sui permessi (revisione Manus 06/10): un permesso non leggibile,
vuoto o non interpretabile NON autorizza - blocca. "Non verificabile" non e'
mai "probabilmente va bene" sul percorso del denaro.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Tuple

from ..costi import get_tariffa


@dataclass(frozen=True)
class EsitoPreflight:
    ok: bool
    controlli: Tuple[Tuple[str, bool, str], ...]

    def motivi_rifiuto(self) -> List[str]:
        return [f"{nome}: {det}" for nome, ok, det in self.controlli if not ok]


def preflight(exchange: Any, symbol: str, nozionale_eur: float,
              min_notional_cfg: float = 1.0) -> EsitoPreflight:
    """Controlli: chiave (permessi), simbolo (attivo), min_notional, saldo EUR.

    Il saldo richiesto include il pedaggio taker di ENTRATA: comprare 10 EUR
    con 10,00 EUR sul conto fallisce all'exchange per 3,5 centesimi di fee —
    misurato, non teorico.
    """
    controlli: List[Tuple[str, bool, str]] = []

    # 1. permessi chiave — FAIL-CLOSED: se non sono leggibili con certezza,
    #    l'ordine non parte (prima era fail-open: "proseguito non verificato").
    try:
        risposta = exchange.privateGetAccountConfig()
        dati = (risposta or {}).get("data") or []
        perm = str(dati[0].get("perm")) if dati else ""
        if perm:
            puo_tradare = "trade" in perm
            controlli.append(("permessi_chiave", puo_tradare, perm))
        else:
            controlli.append(("permessi_chiave", False,
                              "permesso non leggibile (risposta vuota): fail-closed, ordine bloccato"))
    except Exception as exc:
        controlli.append(("permessi_chiave", False,
                          f"non verificabili ({exc.__class__.__name__}): fail-closed, ordine bloccato"))

    # 2. simbolo presente e attivo
    try:
        exchange.load_markets()
        mercato = (exchange.markets or {}).get(symbol)
        if mercato is None:
            controlli.append(("simbolo", False, f"{symbol} assente dall'exchange"))
        else:
            attivo = bool(mercato.get("active", True))
            controlli.append(("simbolo", attivo, "attivo" if attivo else "disabilitato"))
    except Exception as exc:
        controlli.append(("simbolo", False, f"load_markets fallito: {exc.__class__.__name__}"))
        mercato = None

    # 3. min_notional: dal mercato se dichiarato, altrimenti la config
    min_notional = min_notional_cfg
    if mercato:
        try:
            dichiarato = ((mercato.get("limits") or {}).get("cost") or {}).get("min")
            if dichiarato:
                min_notional = float(dichiarato)
        except (TypeError, ValueError):
            pass
    controlli.append(("min_notional", nozionale_eur >= min_notional,
                      f"nozionale {nozionale_eur:.4f} vs minimo {min_notional:.4f}"))

    # 4. saldo EUR libero (trading) copre nozionale + fee taker di entrata
    tariffa = get_tariffa()
    richiesto = nozionale_eur * (1.0 + tariffa.taker)
    try:
        saldi = exchange.fetch_balance({"type": "trading"}) or {}
        libero = float(((saldi.get("EUR") or {}).get("free")) or 0.0)
    except Exception as exc:
        libero = 0.0
        controlli.append(("saldo", False, f"fetch_balance fallito: {exc.__class__.__name__}"))
    else:
        controlli.append(("saldo", libero >= richiesto,
                          f"EUR liberi {libero:.4f} vs richiesti {richiesto:.4f} (nozionale + fee)"))

    return EsitoPreflight(ok=all(ok for _, ok, _ in controlli), controlli=tuple(controlli))
