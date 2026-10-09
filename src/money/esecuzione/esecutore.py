"""Esecutore: costruisce l'ordine e — solo se armato — lo invia.

Lezioni incise nel codice, perche' sono costate denaro vero (1, 4) o arrivano
dalla revisione esterna del 06/10 (2, 3):

1. MAI `int(step)`: con step 0.001 la quantita' diventava 0 e l'ordine
   "partiva" vuoto. Qui si arrotonda per difetto sui decimali REALI dello step.
2. Idempotenza con clOrdId DETERMINISTICO **per intento**: stesso intento ->
   stesso id (il retry e' sicuro, l'exchange deduplica); intenti diversi ->
   id diversi (anche con stessa quantita' e stesso giorno). L'identita' NON e'
   il giorno: due entrate legittime coincidenti collidevano.
3. Journal + recovery: l'intento e' registrato e SALVATO prima dell'invio;
   se il processo muore tra create_order e il salvataggio, al riavvio
   `recupera`/il prossimo `esegui` interroga l'exchange per clOrdId e
   riconcilia PRIMA di qualunque nuovo ordine. Un solo writer per stato
   (lock esclusivo); stato corrotto sul live = arresto, non ripartenza da zero.
4. Il live non e' un default: serve MONEY_LIVE_ARMED=1 + file di promozione
   del cancello + preflight. Senza, tutto esce DRY-RUN.
"""
from __future__ import annotations

import hashlib
import math
import os
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from ..costi import get_tariffa
from . import rischio, stato as modulo_stato
from .preflight import preflight

ETICHETTA_DRY = "DRY-RUN, NON INVIATO"

#: Stati per cui esiste la possibilita' che un ordine sia arrivato all'exchange
#: senza che noi l'abbiamo registrato: richiedono recovery prima di nuovi invii.
STATI_PENDENTI = ("intent", "inviato")

#: Caratteri ammessi in un intent_id (sottoinsieme sicuro per clOrdId dei venue).
_CHARSET_INTENT = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-")


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
    intent_id: str = ""
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


# --- idempotenza per INTENTO (non per giorno) -------------------------------------------

def _valida_intent_id(intent_id: str) -> str:
    s = str(intent_id or "")
    if not s:
        raise Rifiutato(
            "intent_id obbligatorio: l'identita' dell'ordine non puo' dipendere dal giorno "
            "(due intenti legittimi uguali nello stesso giorno devono restare distinti)")
    if len(s) > 40 or any(c not in _CHARSET_INTENT for c in s):
        raise Rifiutato(f"intent_id non valido (max 40, [A-Za-z0-9._-]): {s!r}")
    return s


def cl_ord_id(symbol: str, side: str, qty: float, intent_id: str,
              *, schema_version: int = 2) -> str:
    """Deterministico PER INTENTO: il retry riusa lo stesso intent_id e ottiene lo
    stesso id (dedup exchange); un segnale NUOVO richiede un intent_id NUOVO."""
    intent = _valida_intent_id(intent_id)
    seme = f"money|v{schema_version}|{symbol}|{side}|{qty:.10f}|{intent}"
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
                   intent_id: str = "") -> OrdineCostruito:
        """L'ordine come payload. Controlli sul percorso del capitale: qui si rompe
        PRIMA, non dopo l'invio. `intent_id` identifica UN intento: stesso intento
        anche dopo un restart -> stesso clOrdId.

        Le invarianti economiche sono ECCEZIONI APPLICATIVE (Rifiutato), non `assert`:
        con Python ottimizzato (`-O`) gli assert vengono rimossi e un controllo di
        capitale non puo' dipendere da questo.
        """
        if not prezzo > 0:
            raise Rifiutato(f"prezzo di riferimento non positivo: {prezzo!r}")
        if not step > 0:
            raise Rifiutato(f"step non positivo: {step!r}")
        if not nozionale_eur > 0:
            raise Rifiutato(f"nozionale non positivo: {nozionale_eur!r}")
        if not self.tariffa.giro_taker < 0.05:
            raise Rifiutato(f"tariffa insensata: {self.tariffa.giro_taker:.2%}/giro")
        if side not in ("buy", "sell"):
            raise Rifiutato(f"side {side!r} non valido")

        qty = quantita_da_nozionale(nozionale_eur, prezzo, step)
        nozionale_eff = round(qty * prezzo, 6)
        # Mai spendere piu' del nozionale: l'arrotondamento e' per difetto, e lo dimostriamo.
        if nozionale_eff > nozionale_eur + 1e-6:
            raise Rifiutato(
                f"arrotondamento in su sul capitale: {nozionale_eff} > {nozionale_eur}")
        if qty <= 0 or nozionale_eff < min_notional:
            raise Rifiutato(
                f"NON_FATTIBILE: qty={qty} nozionale={nozionale_eff:.4f} < min_notional {min_notional:.4f}")
        return OrdineCostruito(
            symbol=symbol, side=side, qty=qty, tipo="market",
            prezzo_riferimento=prezzo, nozionale_eur=nozionale_eff,
            cl_ord_id=cl_ord_id(symbol, side, qty, intent_id),
            tariffa_nome=self._tariffa_nome, intent_id=intent_id)

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

    # --- recovery: pendenti riconciliati con l'exchange PRIMA di nuovi invii ---------------

    def _recupera_pendenti(self, st: modulo_stato.Stato, ex: Any) -> int:
        """Per ogni ordine in stato pendente (intent/inviato) interroga l'exchange
        per clOrdId:
        - trovato        -> 'riconciliato' (era arrivato: non va mai rinviato);
        - non trovato    -> 'assente_su_exchange' (non era mai arrivato: sicuro);
        - errore di rete -> Rifiutato: nessun nuovo invio finche' non si sa.
        Salva lo stato aggiornato. Ritorna quanti pendenti ha esaminato."""
        pendenti = [(oid, o) for oid, o in st.ordini.items()
                    if isinstance(o, dict) and o.get("stato") in STATI_PENDENTI]
        for oid, o in pendenti[:50]:
            try:
                risposta = ex.fetch_order(None, o.get("symbol"), {"clOrdId": oid})
            except Exception as exc:
                testo = str(exc).lower().replace(" ", "")
                if "notfound" in testo or "doesnotexist" in testo or "ordernotexist" in testo:
                    o["stato"] = "assente_su_exchange"
                    o["recovery_ts"] = time.time()
                    continue
                raise Rifiutato(
                    f"recovery impossibile per {oid} ({exc.__class__.__name__}): "
                    "nessun nuovo invio finche' i pendenti non sono riconciliati") from exc
            o["stato"] = "riconciliato"
            o["recovery_ts"] = time.time()
            o["exchange_status"] = (risposta or {}).get("status")
        if pendenti:
            modulo_stato.salva(self.stato_path, st)
        return len(pendenti[:50])

    def recupera(self, exchange: Any = None) -> int:
        """Recovery di boot: riconcilia i pendenti con l'exchange (clOrdId).
        Da chiamare PRIMA di armare l'esecuzione live. Ritorna quanti pendenti
        ha esaminato; 0 = nulla da recuperare."""
        ex = exchange or self.exchange
        if ex is None:
            raise Rifiutato("recovery richiesto ma exchange assente: BLOCCO")
        with modulo_stato.lock_esclusivo(self.stato_path):
            st = modulo_stato.carica(self.stato_path, fail_closed=True)
            return self._recupera_pendenti(st, ex)

    # --- esecuzione ------------------------------------------------------------------------

    def esegui(self, ordine: OrdineCostruito, *, equity: float,
               exchange: Any = None, prezzo_mercato: Optional[float] = None) -> Dict[str, Any]:
        """Dry: registra e restituisce il payload. Live: recovery + preflight + invio
        idempotente, tutto sotto lock esclusivo (un solo writer per stato)."""
        if rischio.kill_switch_attivo(self.kill_path):
            raise Rifiutato(f"kill switch attivo ({self.kill_path}): fermo tutto")
        with modulo_stato.lock_esclusivo(self.stato_path):
            st = modulo_stato.carica(self.stato_path, fail_closed=self.live)
            st.aggiorna_picco(equity)
            self._controlli_rischio(st, ordine.nozionale_eur, equity)

            ex = exchange or self.exchange
            if not self.live:
                risultato = {**asdict(ordine), "esito": "registrato_dry_run"}
                st.ordini[ordine.cl_ord_id] = {
                    "symbol": ordine.symbol, "side": ordine.side, "qty": ordine.qty,
                    "intent_id": ordine.intent_id,
                    "stato": ETICHETTA_DRY, "ts": time.time(), "live": False}
                modulo_stato.salva(self.stato_path, st)
                return risultato

            if ex is None:
                raise Rifiutato("live senza exchange: config incompleta, ordine bloccato")

            # pendenti prima di qualunque nuovo invio (recovery obbligatorio)
            self._recupera_pendenti(st, ex)

            esito_pf = preflight(ex, ordine.symbol, ordine.nozionale_eur)
            if not esito_pf.ok:
                raise Rifiutato("preflight fallito: " + "; ".join(esito_pf.motivi_rifiuto()))

            # journal: l'intento e' su disco PRIMA che l'ordine possa esistere
            st.ordini[ordine.cl_ord_id] = {
                "symbol": ordine.symbol, "side": ordine.side, "qty": ordine.qty,
                "intent_id": ordine.intent_id,
                "stato": "intent", "ts": time.time(), "live": True}
            modulo_stato.salva(self.stato_path, st)
            try:
                risposta = ex.create_order(ordine.symbol, ordine.tipo, ordine.side,
                                           ordine.qty, prezzo_mercato,
                                           {"clOrdId": ordine.cl_ord_id})
            except Exception as exc:
                testo = str(exc)
                if "clOrdId" in testo or "duplicate" in testo.lower():
                    st.ordini[ordine.cl_ord_id].update({
                        "stato": "inviato", "nota": "dedup exchange: l'ordine esisteva gia'",
                        "ts": time.time()})
                    modulo_stato.salva(self.stato_path, st)
                    raise Rifiutato(
                        f"ordine gia' presente (clOrdId deduplicato): {ordine.cl_ord_id}") from exc
                st.ordini[ordine.cl_ord_id].update({
                    "stato": "invio_fallito", "errore": testo[:200], "ts": time.time()})
                modulo_stato.salva(self.stato_path, st)
                raise
            st.ordini[ordine.cl_ord_id].update({
                "stato": "inviato", "ts": time.time(),
                "exchange_id": (risposta or {}).get("id")})
            modulo_stato.salva(self.stato_path, st)
            return {**asdict(ordine), "esito": "inviato", "exchange": risposta}
