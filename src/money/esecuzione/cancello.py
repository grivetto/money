"""cancello — il gate pre-trade UNICO, condiviso da `Esecutore` e dal canary.

PERCHE' ESISTE
==============
`verifica_pre_trade` (in `money.rischio`) e' l'unico punto che ammette o rifiuta
un'operazione. Ma il sistema aveva DUE percorsi di invio con due cablaggi diversi:

- `Esecutore.esegui` — passava dal gate;
- `scripts/canary_carry.py` — chiamava `invia_gamba` diretto, **senza gate**.

Due percorsi = il cancello e' aggirabile, e un cancello aggirabile non e' un
cancello. Questo modulo e' il cablaggio UNICO: Esecutore e canary passano di qui,
cosi' non esiste un secondo modo di inviare un ordine senza validazione.

FAIL-CLOSED
===========
`prezzo_stop is None` -> `Decisione(False)`, non un default. E ritorna SEMPRE una
`Decisione`, mai un'eccezione: un cancello che crasha e' un cancello disattivato —
il modo esatto in cui il progetto precedente ha perso il suo layer di rischio.
"""
from __future__ import annotations

from typing import Optional

from ..rischio import Decisione, verifica_pre_trade

MOTIVO_SENZA_STOP = "operazione senza stop ATR: non ammissibile (verifica_pre_trade)"


def gate_pre_trade(*, equity: float, simbolo: str, lato: str, prezzo: float,
                   quantita: float, prezzo_stop: Optional[float], leva: float = 1.0,
                   rischio_aperto_eur: float = 0.0) -> Decisione:
    """Il cancello: `verifica_pre_trade` con stop OBBLIGATORIO. Fail-closed.

    `ok=False` significa: l'ordine non esiste. Non solleva su dati mancanti, li
    rifiuta — cosi' il cancello resta vivo anche quando un input e' sbagliato.
    """
    if prezzo_stop is None:
        return Decisione(False, (MOTIVO_SENZA_STOP,), 0.0, 0.0, 0.0, 0.0)
    return verifica_pre_trade(
        equity=equity, simbolo=simbolo, lato=lato, prezzo=prezzo,
        quantita=quantita, prezzo_stop=prezzo_stop, leva=leva,
        rischio_aperto_eur=rischio_aperto_eur,
    )


__all__ = ["gate_pre_trade", "MOTIVO_SENZA_STOP"]
