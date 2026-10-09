"""Economia di MOSAICO-4 (§3.4, §5): break-even, scenari, fattibilita'.

Funzioni PURE. La decisione di aprire un hedge group passa SOLO da qui: nessun altro
modulo puo' dire "apri" senza che `valuta` abbia prodotto un esito ammissibile.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict, Optional

from .model import EconomicsSnapshot

#: Moltiplicatore del margine rispetto ai costi (§3.4: margine >= 3 * costi).
MARGINE_MINIMO_SU_COSTI = 3.0


@dataclass(frozen=True)
class EsitoEconomico:
    ammissibile: bool
    motivo: str
    margine_netto: float
    costi: float
    beneficio_lordo: float
    scenario: str = "base"

    def __bool__(self) -> bool:
        return self.ammissibile


def scenari(base: EconomicsSnapshot, *, taglio_funding: float = 0.5,
            amplia_slippage: float = 2.0) -> Dict[str, EconomicsSnapshot]:
    """Le tre fotografie richieste (§3.3, §4): favorevole, base, avverso.

    - favorevole: funding pieno, slippage dimezzato (fill maker), nessun buffer;
    - base: i numeri osservati;
    - avverso: funding dimezzato, slippage/spread raddoppiati, PIU' un buffer eventi
      avversi pari ai costi base (unwind parziale, ritardi, regime che cambia). Il buffer
      e' la differenza fra uno scenario avverso vero e un semplice ricalcolo: senza di
      esso, con funding dimezzato e costi raddoppiati il margine avverso resterebbe
      sistematicamente >= 0 quando il base passa, e il controllo non morderebbe mai.
    """
    favorevole = replace(base,
                         funding_atteso=base.funding_atteso,
                         slippage_entry=base.slippage_entry * 0.5,
                         slippage_exit=base.slippage_exit * 0.5,
                         buffer_eventi_avversi=0.0)
    avverso = replace(base,
                      funding_atteso=base.funding_atteso * taglio_funding,
                      slippage_entry=base.slippage_entry * amplia_slippage,
                      slippage_exit=base.slippage_exit * amplia_slippage,
                      spread_entry=base.spread_entry * amplia_slippage,
                      spread_exit=base.spread_exit * amplia_slippage,
                      buffer_eventi_avversi=base.buffer_eventi_avversi + base.costi)
    return {"favorevole": favorevole, "base": base, "avverso": avverso}


def valuta(snap: EconomicsSnapshot, *, soglia_minima_eur: float = 0.0,
           budget_perdita_avversa_eur: Optional[float] = None,
           margine_su_costi: float = MARGINE_MINIMO_SU_COSTI) -> EsitoEconomico:
    """La regola completa di §3.4. Ammissibile solo se TUTTE le condizioni valgono.

    Ordine dei controlli deliberato: prima i motivi "di merito" (funding, margine), poi
    lo scenario avverso (che e' un budget, non una speranza).
    """
    sc = scenari(snap)
    base, avverso = sc["base"], sc["avverso"]

    if base.beneficio_lordo <= 0:
        return EsitoEconomico(False, "beneficio lordo non positivo: niente da incassare",
                              base.margine_netto, base.costi, base.beneficio_lordo)
    if base.funding_atteso <= 0:
        return EsitoEconomico(False, "funding atteso non positivo: carry assente (non e' uno sconto)",
                              base.margine_netto, base.costi, base.beneficio_lordo)
    if base.costi <= 0:
        return EsitoEconomico(False, "costi nulli: fotografia non credibile, non si apre",
                              base.margine_netto, base.costi, base.beneficio_lordo)

    soglia = max(margine_su_costi * base.costi, soglia_minima_eur)
    if base.margine_netto < soglia:
        return EsitoEconomico(
            False,
            f"margine netto {base.margine_netto:.4f} < soglia {soglia:.4f} "
            f"(max({margine_su_costi:.0f}x costi, {soglia_minima_eur:.2f}))",
            base.margine_netto, base.costi, base.beneficio_lordo)

    if budget_perdita_avversa_eur is not None and avverso.margine_netto < -abs(budget_perdita_avversa_eur):
        return EsitoEconomico(
            False,
            f"scenario avverso {avverso.margine_netto:.4f} oltre il budget "
            f"{-abs(budget_perdita_avversa_eur):.4f}",
            base.margine_netto, base.costi, base.beneficio_lordo, scenario="avverso")

    return EsitoEconomico(True, "ammissibile", base.margine_netto, base.costi,
                          base.beneficio_lordo, scenario="base")


def not_economicamente_fattibile(nozionale: float, min_notional: float) -> bool:
    """§5: sotto il minimo d'ordine il sistema risponde NO, non aumenta size o leva."""
    return nozionale <= 0 or nozionale < min_notional


def riepilogo(snap: EconomicsSnapshot) -> Dict[str, Any]:
    """Le componenti SEPARATE (§4 doc «Suggerimenti»): mai sommare cose diverse."""
    sc = scenari(snap)
    return {
        "funding_atteso": snap.funding_atteso,
        "basis_edge": snap.basis_edge,
        "fee_entry": snap.fee_entry,
        "fee_exit": snap.fee_exit,
        "slippage_entry": snap.slippage_entry,
        "slippage_exit": snap.slippage_exit,
        "spread_entry": snap.spread_entry,
        "spread_exit": snap.spread_exit,
        "costo_conversione": snap.costo_conversione,
        "buffer_hedge": snap.buffer_hedge,
        "buffer_eventi_avversi": snap.buffer_eventi_avversi,
        "base": {"margine_netto": sc["base"].margine_netto, "costi": sc["base"].costi},
        "avverso": {"margine_netto": sc["avverso"].margine_netto, "costi": sc["avverso"].costi},
        "favorevole": {"margine_netto": sc["favorevole"].margine_netto},
    }
