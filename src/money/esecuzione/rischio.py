"""Limiti di rischio del percorso di esecuzione — un solo vocabolario col mandato.

PERCHE' QUESTO MODULO E' CAMBIATO (audit senza pieta', 13/10 — Fix #4)
=====================================================================
Questo file duplicava i limiti con una semantica DIVERSA dal resto del sistema:
`rischio_per_trade` trattava il NOZIONALE come se fosse il rischio e bloccava ogni
ordine oltre il 2% dell'equity — su un conto da ~1.100 EUR, qualsiasi spot sopra
~22 EUR veniva rifiutato. E' il "blocco fittizio" trovato dall'audit, ed e' il
motivo per cui il canary da 110 EUR non avrebbe potuto crescere fino al tetto.

Il rischio di uno spot long-only NON e' il nozionale: e' `nozionale x distanza
dello stop`. La distanza la fornisce lo stop ATR (2,5x, via `money.rischio`); il
tetto qui applicato e' quello del mandato proprietario: **2% dell'equity per
operazione**. Il sizing operativo, piu' prudente, e' un'altra cosa e vive gia' nel
resto del sistema (0,25% di default in `money.rischio.ParametriRischio`, budget
applicato dal cancello condiviso `esecuzione.cancello`): due livelli, una sola
definizione di rischio — nozionale x distanza stop.

Freni di giornata (-3%) e drawdown massimo (-10%) restano i numeri del mandato:
questo modulo li applica, non li discute.

REGOLA: funzioni pure, nessuna eccezione sul percorso del capitale: un limite che
non si riesce a calcolare blocca l'ordine, non passa. Il ritorno e' sempre un
Verdetto; l'unico modo di sbagliare e' ignorarlo.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

#: Tetto del mandato sul rischio per operazione (frazione dell'equity): 2%.
#: Il rischio si misura sullo STOP (`nozionale x distanza_stop`), mai sul nozionale.
RISCHIO_PER_TRADE = 0.02
#: Stop giornaliero del mandato: perdita di giornata oltre il 3% ferma tutto.
STOP_GIORNALIERO = 0.03
#: Drawdown massimo del mandato dal picco: oltre il 10% si chiude soltanto.
DD_MASSIMO = 0.10


@dataclass(frozen=True)
class Verdetto:
    """Esito di un controllo di rischio. `ok=False` blocca l'ordine."""

    ok: bool
    motivo: str = ""


def rischio_per_trade(nozionale: float, equity: float,
                      distanza_stop: Optional[float] = None,
                      rischio_max: float = RISCHIO_PER_TRADE) -> Verdetto:
    """Rischio per operazione = `nozionale x distanza_stop`, contro il mandato (2%).

    `distanza_stop` e' |ingresso - stop| / ingresso (frazione: 0.05 = stop al 5%).
    Senza una distanza dichiarata o plausibile il controllo NON si puo' fare:
    blocca (fail-closed) — uno spot senza stop non ha un rischio definito.
    equity <= 0 o nozionale < 0 sono input rotti: il controllo FALLISCE,
    perche' un controllo che non si puo' fare e' un controllo fallito.
    """
    if equity <= 0:
        return Verdetto(False, f"equity non positiva ({equity}): controllo impossibile, ordine bloccato")
    if nozionale < 0:
        return Verdetto(False, f"nozionale negativo ({nozionale}): input rotto, ordine bloccato")
    if distanza_stop is None or not (0.0 < float(distanza_stop) < 1.0):
        return Verdetto(False, "distanza dello stop assente o implausibile: "
                               "rischio non calcolabile, ordine bloccato")
    rischio_eur = float(nozionale) * float(distanza_stop)
    limite = float(rischio_max) * float(equity)
    if rischio_eur > limite:
        return Verdetto(False, f"rischio {rischio_eur:.4f} ({rischio_eur / equity:.2%} "
                               f"dell'equity) > {rischio_max:.0%} di equity {equity:.4f} ({limite:.4f})")
    return Verdetto(True)


def distanza_stop_relativa(prezzo_ingresso: float, prezzo_stop: float) -> float:
    """|ingresso - stop| / ingresso — la distanza che trasforma un nozionale in rischio.

    Solleva su prezzi non positivi: e' un errore di programmazione, non un caso
    operativo; il chiamante sul percorso del capitale valida prima di chiamare.
    """
    if prezzo_ingresso <= 0 or prezzo_stop <= 0:
        raise ValueError(
            f"i prezzi devono essere positivi (ingresso {prezzo_ingresso!r}, stop {prezzo_stop!r})")
    return abs(float(prezzo_ingresso) - float(prezzo_stop)) / float(prezzo_ingresso)


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
