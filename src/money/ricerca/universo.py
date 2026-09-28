"""Selezione dell'universo per la misura di robustezza (nodo P5).

Il criterio e' dichiarato PRIMA dei numeri: una coppia entra se la sua storia copre la
finestra ``[inizio, fine]`` con copertura >= ``copertura_minima`` (barre presenti / barre
attese) E se la prima barra non e' piu' tarda della tolleranza (7 giorni).

La seconda condizione non e' un capriccio: i motori indicizzano le serie per POSIZIONE,
quindi una serie che parte mesi dopo le altre disallineerebbe il confine
addestramento/verifica invece di essere esclusa — meglio escluderla con un motivo scritto
che includerla con un errore silenzioso.

Provenienza: scritto per P5 (Donchian su universo esteso), riusabile da chiunque debba
selezionare le coppie "con storia lunga" senza deciderlo a mano.
"""
from __future__ import annotations

from typing import Optional

from ..dati import SerieBarre

#: La prima barra deve stare entro questa tolleranza dall'inizio della finestra.
TOLLERANZA_MS: int = 7 * 86_400_000

#: Sotto questa lunghezza una serie non e' misurabile, a prescindere dalla copertura.
MIN_BARRE: int = 60


def barre_attese(inizio_ms: int, fine_ms: int, durata_ms: int) -> int:
    """Numero di barre attese in ``[inizio_ms, fine_ms]`` estremi inclusi."""
    if durata_ms <= 0 or fine_ms < inizio_ms:
        return 0
    return (fine_ms - inizio_ms) // durata_ms + 1


def copertura_finestra(serie: SerieBarre, inizio_ms: int, fine_ms: int) -> float:
    """Barre presenti nella finestra / barre attese (0.0 se non ci sono attese)."""
    attese = barre_attese(inizio_ms, fine_ms, serie.durata_barra_ms)
    if attese <= 0:
        return 0.0
    presenti = sum(1 for barra in serie if inizio_ms <= barra.ts <= fine_ms)
    return presenti / attese


def motivo_esclusione(serie: SerieBarre, *, inizio_ms: int, fine_ms: int,
                      copertura_minima: float = 0.95,
                      tolleranza_ms: int = TOLLERANZA_MS,
                      min_barre: int = MIN_BARRE) -> Optional[str]:
    """``None`` se la serie e' eleggibile, altrimenti il motivo (scritto) dell'esclusione.

    I motivi sono frasi intere perche' finiscono nel log della misura: un'esclusione senza
    motivo e' indistinguibile da un errore.
    """
    if len(serie) < min_barre:
        return f"serie corta: {len(serie)} barre (< {min_barre})"
    prima = serie.prima
    ultima = serie.ultima
    if prima is None or ultima is None:
        return "serie senza barre"
    if prima.ts > inizio_ms + tolleranza_ms:
        giorni = (prima.ts - inizio_ms) // 86_400_000
        return f"storia corta: prima barra {giorni} giorni dopo l'inizio (tolleranza inclusa)"
    if ultima.ts < fine_ms - tolleranza_ms:
        giorni = (fine_ms - ultima.ts) // 86_400_000
        return f"storia tronca: ultima barra {giorni} giorni prima della fine"
    cop = copertura_finestra(serie, inizio_ms, fine_ms)
    if cop < copertura_minima:
        return f"copertura {cop:.1%} < {copertura_minima:.0%}"
    return None
