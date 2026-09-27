"""Esecutore: costruisce l'ordine e — solo se armato — lo invia.

Tre lezioni incise nel codice, perche' sono costate denaro vero:

1. MAI `int(step)`: con step 0.001 la quantita' diventava 0 e l'ordine
   "partiva" vuoto. Qui si arrotonda per difetto sui decimali REALI dello step.
2. Idempotenza con clOrdId DETERMINISTICO: stesso ordine, stesso id. Se il
   processo muore tra l'invio e il salvataggio dello stato, il re-invio viene
   rifiutato dall'exchange invece di duplicare la posizione.
3. Il live non e' un default: serve MONEY_LIVE_ARMED=1 + file di promozione
   del cancello + preflight. Senza, tutto esce DRY-RUN.
"""
from __future__ import annotations

import hashlib
import math
import os
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

from ..costi import get_tariffa
from . import rischio, stato as modulo_stato
from .preflight import preflight

ETICHETTA_DRY = "DRY-RUN, NON INVIATO"


class Rifiutato(Exception):
    """L'ordine non esiste. Mai silenzioso: il motivo e' sempre nel messaggio."""


@dataclass(frozen=True)
class OrdineCostruito:
    symbol: str
    side: str
    qty: float
    tipo: str
    prezzo_riferimento: float
    nozionale_eur: float
    cl_ord_id: str
    tariffa_nome: str
    etichetta: str = ETICHETTA_DRY


# --- sizing: la lezione int(step) -------------------------------------------------------

def decimali_di_step(step: float) -> int:
    testo = f"{step:.15f}".rstrip("0")
    return len(testo.split(".")[1]) if "." in testo else 0


def arrotonda_a_step(quantita: float, step: float) -> float:
    """qty = floor(q/step)*step. Con step 0.001, int(step) darebbe 0: qui 3 decimali."""
    if step <= 0 or quantita <= 0:
        return 0.0
    return round(math.floor(quantita / step) * step, decimali_di_step(step))


def quantita_da_nozionale(nozionale_eur: float, prezzo: float, step: float) -> float:
    if prezzo <= 0 or nozionale_eur <= 0:
        return 0.0
    return arrotonda_a_step(nozionale_eur / prezzo, step)


def cl_ord_id(symbol: str, side: str, qty: float, giorno: str) -> str:
    """Deterministico: stesso ordine nello stesso giorno = stesso id = dedup exchange."""
    seme = f"money|{symbol}|{side}|{qty:.10f}|{giorno}"
    return "mny" + hashlib.sha256(seme.encode()).hexdigest()[:29]


class Esecutore:
    """Costruisce ed esegue. Di default DRY-RUN: il live si ARMA, non si assume."""

    def __init__(self, exchange: Any = None, *, live: bool = False,
                 stato_path: str = "stato_esecutore.json",
                 kill_path: str = "MONEY_KILL_SWITCH",
                 promozione_path: str = "",
                 tariffa_nome: str = "okx_eea_spot") -> None:
        self.exchange = exchange
        self.stato_path = stato_path
        self.kill_path = kill_path
        self.tariffa = get_tariffa(tariffa_nome)
        self._tariffa_nome = tariffa_nome
        self.live = bool(live)
        if self.live:
            if os.environ.get("MONEY_LIVE_ARMED") != "1":
                raise Rifiutato("live richiesto ma MONEY_LIVE_ARMED != 1: resto in dry-run per costruzione")
            if not promozione_path or not os.path.exists(promozione_path):
                raise Rifiutato("live richiesto senza file di promozione del cancello: "
                                "nessun edge misurato, nessun ordine reale")

    # --- costruzione: pura, testabile, senza rete ----------------------------------------

    def costruisci(self, symbol: str, side: str, nozionale_eur: float,
                   prezzo: float, step: float, min_notional: float,
                   giorno: str = "") -> OrdineCostruito:
        """L'ordine come payload. Assertions sul percorso del capitale: qui si rompe
        PRIMA, non dopo l'invio."""
        assert prezzo > 0, "prezzo di riferimento non positivo"
        assert step > 0, "step non positivo"
        assert nozionale_eur > 0, "nozionale non positivo"
        assert self.tariffa.giro_taker < 0.05, f"tariffa insensata: {self.tariffa.giro_taker:.2%}/giro"
        if side not in ("buy", "sell"):
            raise Rifiutato(f"side {side!r} non valido")

        qty = quantita_da_nozionale(nozionale_eur, prezzo, step)
        nozionale_eff = round(qty * prezzo, 6)
        # Mai spendere piu' del nozionale: l'arrotondamento e' per difetto, e lo dimostriamo.
        assert nozionale_eff <= nozionale_eur + 1e-6, \
            f"arrotondamento in su sul capitale: {nozionale_eff} > {nozionale_eur}"
        if qty <= 0 or nozionale_eff < min_notional:
            raise Rifiutato(
                f"NON_FATTIBILE: qty={qty} nozionale={nozionale_eff:.4f} < min_notional {min_notional:.4f}")
        giorno = giorno or time.strftime("%Y-%m-%d", time.gmtime())
        return OrdineCostruito(
            symbol=symbol, side=side, qty=qty, tipo="market",
            prezzo_riferimento=prezzo, nozionale_eur=nozionale_eff,
            cl_ord_id=cl_ord_id(symbol, side, qty, giorno),
            tariffa_nome=self._tariffa_nome)

    # --- i controlli prima dell'esistenza dell'ordine -------------------------------------

    def _controlli_rischio(self, st: modulo_stato.Stato, nozionale: float,
                           equity: float) -> None:
        for nome, verdetto in (
            ("rischio_per_trade", rischio.rischio_per_trade(nozionale, equity)),
            ("stop_giornaliero", rischio.stop_giornaliero(st.pnl_giorno, st.equity_picco or equity)),
            ("drawdown", rischio.drawdown_massimo(equity, st.equity_picco or equity)),
        ):
            if not verdetto.ok:
                raise Rifiutato(f"{nome}: {verdetto.motivo}")

    # --- esecuzione ------------------------------------------------------------------------

    def esegui(self, ordine: OrdineCostruito, *, equity: float,
               exchange: Any = None, prezzo_mercato: Optional[float] = None) -> Dict[str, Any]:
        """Dry: registra e restituisce il payload. Live: preflight + invio idempotente."""
        if rischio.kill_switch_attivo(self.kill_path):
            raise Rifiutato(f"kill switch attivo ({self.kill_path}): fermo tutto")
        st = modulo_stato.carica(self.stato_path)
        st.aggiorna_picco(equity)
        self._controlli_rischio(st, ordine.nozionale_eur, equity)

        ex = exchange or self.exchange
        if not self.live:
            risultato = {**asdict(ordine), "esito": "registrato_dry_run"}
            st.ordini[ordine.cl_ord_id] = {
                "symbol": ordine.symbol, "side": ordine.side, "qty": ordine.qty,
                "stato": ETICHETTA_DRY, "ts": time.time(), "live": False}
            modulo_stato.salva(self.stato_path, st)
            return risultato

        if ex is None:
            raise Rifiutato("live senza exchange: config incompleta, ordine bloccato")
        esito_pf = preflight(ex, ordine.symbol, ordine.nozionale_eur)
        if not esito_pf.ok:
            raise Rifiutato("preflight fallito: " + "; ".join(esito_pf.motivi_rifiuto()))
        try:
            risposta = ex.create_order(ordine.symbol, ordine.tipo, ordine.side,
                                       ordine.qty, prezzo_mercato,
                                       {"clOrdId": ordine.cl_ord_id})
        except Exception as exc:
            testo = str(exc)
            if "clOrdId" in testo or "duplicate" in testo.lower():
                raise Rifiutato(f"ordine gia' presente (clOrdId deduplicato): {ordine.cl_ord_id}") from exc
            raise
        st.ordini[ordine.cl_ord_id] = {
            "symbol": ordine.symbol, "side": ordine.side, "qty": ordine.qty,
            "stato": "inviato", "ts": time.time(), "live": True,
            "exchange_id": (risposta or {}).get("id")}
        modulo_stato.salva(self.stato_path, st)
        return {**asdict(ordine), "esito": "inviato", "exchange": risposta}
