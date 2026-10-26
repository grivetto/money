#!/usr/bin/env python3
"""money.funding_carry — stima del funding per il gate del carry (P34-F1) e
verifica della tariffa X-Perp (P34-F4).

PERCHE' ESISTE
==============
La stima del funding per l'apertura di un carry era il minimo degli ultimi
3 periodi (24h): una finestra cosi' corta non e' una base di decisione
(lezione P19b: serve >= 100 periodi) e un regime transitorio alto apre il
carry che poi allunga il payback (P22: uscita frequente mascherata fino a
-6,37%/anno su DOT).

La realta' misurata (33/33 epoche, 16/10 -> 26/10): su OKX EEA gli X-Perp
hanno fundingRate = +0,010000%/8h ESATTE. E' una tariffa DI LISTINO: il
rischio non e' il campione, e' che OKX la cambi. Percio' il gate degli X-Perp
verifica "tariffa corrente == tariffa dichiarata alla pre-registrazione" e
rifiuta al primo scostamento; il watchdog (P34-F4) allarma la stessa
condizione fuori dal gate.

Gli USDT-SWAP invece hanno funding variabile: li' la stima e' il percentile
10 della serie rolling (finestra >= 30 periodi; meno = rifiuto "campione
insufficiente", mai un default permissivo). Il segno si conserva (lezione
fix audit 19/10): un p10 negativo arriva negativo al gate, che lo rifiuta.

Solo funzioni pure o con l'exchange INIETTATO: niente rete nei test, niente
chiavi, niente I/O.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from money.statistica import _quantile

#: Tariffa fissa dichiarata per gli X-Perp OKX EEA alla pre-registrazione P34:
#: +0,010000%/8h, misurata identica su 33/33 epoche dal 16/10 al 26/10.
#: Qualsiasi altro valore corrente = tariffa cambiata = ALLARME, non campione.
TARIFFA_XPERP_DICHIARATA = 0.0001

#: Finestra minima di periodi per una stima p10 (soglia OPERATIVA dichiarata
#: dalla spec P34; il riferimento di metodo P19b resta >= 100 periodi).
MIN_PERIODI_SWAP = 30

#: Finestra richiesta alla funding-rate-history (max API = 100).
FINESTRA_HISTORY = 100

#: Percentile della serie rolling usato come stima (0,10 = p10: il 90% dei
#: periodi paga di piu').
PERCENTILE_SWAP = 0.10

#: Tolleranza di confronto tariffa corrente vs dichiarata: si accetta solo
#: l'uguaglianza (misurata esatta sulle epoche reali).
EPS_TARIFFA = 1e-12


@dataclass(frozen=True)
class StimaFunding:
    """Esito della stima funding per il gate di apertura (P34-F1).

    `ok=False` e' SEMPRE bloccante: chi apre usa `valore` solo se ok.
    """

    valore: float       # frazione per periodo (8h), CON SEGNO
    fonte: str          # da dove viene la stima (per il verbale del dry-run)
    ok: bool
    motivo: str         # vuoto se ok
    periodi: int        # periodi usati (0 se tariffa fissa)


def _tipo_strumento(inst_perp: str) -> str:
    """'xperp' se X-Perp EEA (tariffa fissa), 'swap' se USDT-SWAP (variabile).
    Strumenti ignoti -> 'ignoto' (fail-closed)."""
    s = (inst_perp or "").upper()
    if "XPERP" in s:
        return "xperp"
    if "SWAP" in s:
        return "swap"
    return "ignoto"


def _valori_history(storico) -> list:
    valori = []
    for d in (storico or {}).get("data") or []:
        try:
            valori.append(float(d.get("fundingRate")))
        except (TypeError, ValueError, AttributeError):
            continue
    return valori


def stima_funding(ex, inst_perp: str,
                  tariffa_dichiarata: float = TARIFFA_XPERP_DICHIARATA,
                  min_periodi: int = MIN_PERIODI_SWAP) -> StimaFunding:
    """Stima del funding per periodo per il gate di apertura (P34-F1).

    - X-Perp EEA: tariffa corrente (public/funding-rate) SE identica alla
      tariffa dichiarata alla pre-registrazione; altrimenti ok=False (la
      tariffa e' cambiata: allarme, mai apertura).
    - USDT-SWAP: percentile 10 della serie rolling (finestra >= min_periodi);
      n < min_periodi -> ok=False "campione insufficiente". Segno conservato:
      p10 negativo -> ok=False.
    - Strumento ignoto o lettura fallita -> ok=False con motivo (fail-closed,
      mai un default permissivo).
    """
    tipo = _tipo_strumento(inst_perp)
    if tipo == "ignoto":
        return StimaFunding(0.0, "strumento ignoto", False,
                            f"instId {inst_perp!r} non riconosciuto "
                            "(ne' XPERP ne' SWAP)", 0)
    try:
        if tipo == "xperp":
            r = ex.publicGetPublicFundingRate({"instId": inst_perp})
            corrente = float((r.get("data") or [{}])[0].get("fundingRate") or 0)
            if abs(corrente - tariffa_dichiarata) > EPS_TARIFFA:
                return StimaFunding(
                    corrente, "tariffa fissa X-Perp (SCOSTATA)", False,
                    f"tariffa X-Perp corrente {corrente:.8%} != dichiarata "
                    f"{tariffa_dichiarata:.8%}: la tariffa e' cambiata — "
                    "allarme P34-F4, non aprire", 0)
            return StimaFunding(corrente, "tariffa fissa X-Perp (corrente == "
                                "dichiarata 0,0001)", True, "", 0)
        storico = ex.publicGetPublicFundingRateHistory(
            {"instId": inst_perp, "limit": str(FINESTRA_HISTORY)})
        valori = _valori_history(storico)
        if len(valori) < min_periodi:
            return StimaFunding(
                0.0, "p10 rolling", False,
                f"campione insufficiente: {len(valori)} periodi < {min_periodi}",
                len(valori))
        v = _quantile(sorted(valori), PERCENTILE_SWAP)
        if v <= 0:
            return StimaFunding(v, f"p10 rolling ({len(valori)} periodi)",
                                False,
                                f"funding p10 {v:.5%} non positivo: il carry "
                                "non incassa", len(valori))
        return StimaFunding(v, f"p10 rolling ({len(valori)} periodi)", True,
                            "", len(valori))
    except Exception as e:  # noqa: BLE001
        return StimaFunding(0.0, "errore", False,
                            f"lettura funding fallita: {type(e).__name__}", 0)


def verifica_tariffa_xperp(corrente: float,
                           dichiarata: float = TARIFFA_XPERP_DICHIARATA,
                           eps: float = EPS_TARIFFA) -> Tuple[bool, str]:
    """P34-F4: confronto puro tariffa corrente vs dichiarata (per il
    watchdog carry_watch). Ritorna (ok, motivo)."""
    if abs(corrente - dichiarata) <= eps:
        return True, ""
    return False, (f"tariffa X-Perp corrente {corrente:.8%} != dichiarata "
                   f"{dichiarata:.8%}")
