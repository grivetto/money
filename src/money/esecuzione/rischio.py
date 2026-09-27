"""Limiti di rischio del mandato proprietario (19/09/2026).

Funzioni pure, nessuna eccezione sul percorso del capitale: un limite che non
si riesce a calcolare deve bloccare l'ordine, non passare. Il ritorno e'
sempre un Verdetto; l'unico modo di sbagliare e' ignorarlo.

Mandato: rischio per trade <= 2% dell'equity, stop giornaliero -3%,
drawdown massimo -10% dal picco. Sono numeri DEL PROPRIETARIO: questo modulo
li applica, non li discute.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

RISCHIO_PER_TRADE = 0.02
STOP_GIORNALIERO = 0.03
DD_MASSIMO = 0.10


@dataclass(frozen=True)
class Verdetto:
    """Esito di un controllo di rischio. `ok=False` blocca l'ordine."""

    ok: bool
    motivo: str = ""


def rischio_per_trade(nozionale: float, equity: float,
                      rischio_max: float = RISCHIO_PER_TRADE) -> Verdetto:
    """Per uno spot long-only il rischio massimo e' il nozionale stesso.

    equity <= 0 o nozionale < 0 sono input rotti: il controllo FALLISCE,
    perche' un controllo che non si puo' fare e' un controllo fallito.
    """
    if equity <= 0:
        return Verdetto(False, f"equity non positiva ({equity}): controllo impossibile, ordine bloccato")
    if nozionale < 0:
        return Verdetto(False, f"nozionale negativo ({nozionale}): input rotto, ordine bloccato")
    limite = rischio_max * equity
    if nozionale > limite:
        return Verdetto(False, f"nozionale {nozionale:.4f} > {rischio_max:.0%} di equity {equity:.4f} ({limite:.4f})")
    return Verdetto(True)


def stop_giornaliero(pnl_giorno: float, equity_inizio_giorno: float,
                     limite: float = STOP_GIORNALIERO) -> Verdetto:
    """Vero freno di giornata: pnl_giorno <= -limite * equity_inizio blocca tutto."""
    if equity_inizio_giorno <= 0:
        return Verdetto(False, "equity di inizio giorno non positiva: stop attivo per prudenza")
    if pnl_giorno <= -limite * equity_inizio_giorno:
        return Verdetto(False, f"stop giornaliero: pnl {pnl_giorno:.4f} <= -{limite:.0%} di {equity_inizio_giorno:.4f}")
    return Verdetto(True)


def drawdown_massimo(equity_attuale: float, equity_picco: float,
                     limite: float = DD_MASSIMO) -> Verdetto:
    """Sotto (1 - limite) * picco storico si blocca tutto: e' la regola che salva il capitale."""
    if equity_picco <= 0:
        return Verdetto(False, "picco non positivo: drawdown non calcolabile, ordine bloccato")
    pavimento = (1.0 - limite) * equity_picco
    if equity_attuale < pavimento:
        dd = 1.0 - equity_attuale / equity_picco
        return Verdetto(False, f"drawdown {dd:.2%} oltre il limite {limite:.0%} (equity {equity_attuale:.4f} < pavimento {pavimento:.4f})")
    return Verdetto(True)


# --- kill switch: un file che, se esiste, ferma tutto ---------------------------------

def kill_switch_attivo(percorso: str) -> bool:
    """Il kill switch e' un FILE: esiste = fermo tutto. Anche a codice morto, basta crearlo."""
    return Path(percorso).exists()


def attiva_kill_switch(percorso: str, motivo: str = "") -> None:
    Path(percorso).write_text(motivo or "attivato manualmente\n", encoding="utf-8")


def disattiva_kill_switch(percorso: str) -> None:
    Path(percorso).unlink(missing_ok=True)
