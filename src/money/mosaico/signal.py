"""Segnali di MOSAICO-4 (§3): funding forecast, basis, qualità dell'esecuzione.

Funzioni PURE e deterministiche: nessun modello ML nel percorso live (§3.1). Ogni
soglia e' un parametro con default dichiarato, cosi' lo spec puo' congelarli.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Iterable, Optional, Sequence


# --- §3.1 carry funding previsto -----------------------------------------------------

def media_robusta(valori: Sequence[float], n: int = 3) -> Optional[float]:
    """Media degli ultimi `n` valori. None se non ci sono abbastanza osservazioni."""
    v = [x for x in valori[-n:] if x is not None]
    return sum(v) / len(v) if len(v) == n else None


def quantile_25(valori: Sequence[float]) -> Optional[float]:
    """25mo percentile (interpolazione lineare). Conservativo sul funding."""
    v = sorted(x for x in valori if x is not None)
    if len(v) < 4:
        return None
    pos = 0.25 * (len(v) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(v) - 1)
    frac = pos - lo
    return v[lo] + (v[hi] - v[lo]) * frac


def funding_forecast(serie: Sequence[float], *, finestra_breve: int = 3,
                     finestra_storica: int = 30) -> Optional[float]:
    """Minimo tra media robusta breve e quantile 25 storico (§3.1).

    Non usare l'ultimo funding osservato: e' il punto piu' rumoroso. Il minimo tra le due
    stime e' deliberatamente conservativo. None se una delle due non e' calcolabile.
    """
    breve = media_robusta(serie, finestra_breve)
    storico = quantile_25(serie[-finestra_storica:])
    if breve is None or storico is None:
        return None
    return min(breve, storico)


# --- §3.2 basis --------------------------------------------------------------------

def basis(perp_mid: float, spot_mid: float) -> float:
    """basis = (perp_mid / spot_mid) - 1. Zero se lo spot e' nullo (dato non valido)."""
    if spot_mid <= 0:
        return 0.0
    return perp_mid / spot_mid - 1.0


def basis_mediana(serie_basis: Sequence[float], finestra: int = 7) -> Optional[float]:
    v = [x for x in serie_basis[-finestra:] if x is not None]
    return median(v) if v else None


def deviazione_da_mediana(basis_corrente: float, mediana: float) -> float:
    return basis_corrente - mediana


# --- §3.3 qualità dell'esecuzione --------------------------------------------------

@dataclass(frozen=True)
class QualitaEsecuzione:
    spread_spot: float
    spread_perp: float
    profondita_spot: float     # multiplo del nozionale target
    profondita_perp: float
    slippage_p95: float
    eta_book_ms: int
    latenza_incrociata_ms: int
    ordini_non_riconciliati: int


def esecuzione_ammissibile(q: QualitaEsecuzione, *, spread_max: float = 0.0010,
                           profondita_min: float = 5.0, slippage_p95_max: float = 0.0015,
                           ttl_book_ms: int = 2000, latenza_max_ms: int = 250) -> tuple[bool, str]:
    """Tutte le condizioni di §3.3. Ritorna (ok, motivo) — il motivo e' sempre esplicito."""
    if q.spread_spot > spread_max or q.spread_perp > spread_max:
        return False, f"spread oltre il limite (spot {q.spread_spot:.5f} / perp {q.spread_perp:.5f} > {spread_max:.5f})"
    if q.profondita_spot < profondita_min or q.profondita_perp < profondita_min:
        return False, (f"profondita' insufficiente (spot {q.profondita_spot:.2f}x / "
                       f"perp {q.profondita_perp:.2f}x < {profondita_min:.1f}x)")
    if q.slippage_p95 > slippage_p95_max:
        return False, f"slippage p95 {q.slippage_p95:.5f} > {slippage_p95_max:.5f}"
    if q.eta_book_ms > ttl_book_ms:
        return False, f"book vecchio {q.eta_book_ms}ms > TTL {ttl_book_ms}ms"
    if q.latenza_incrociata_ms > latenza_max_ms:
        return False, f"latenza tra le macchine {q.latenza_incrociata_ms}ms > {latenza_max_ms}ms"
    if q.ordini_non_riconciliati > 0:
        return False, f"{q.ordini_non_riconciliati} ordini/posizioni non riconciliati"
    return True, "esecuzione ammissibile"
