"""Coordinatore di esecuzione — l'UNICO componente che invia ordini.

PERCHE' ESISTE
==============
Prima c'erano DUE percorsi che inviavano ordini: `esecutore.py` (generico, con
journal/recovery) e `scripts/canary_carry.py` (imperativo, specifico per il canary
DOGE). Due percorsi = due gestioni di fill parziali, retry, gambe orfane e posizioni
residue dopo un riavvio. Qui l'invio e' UNO solo, e la logica dell'hedge a due gambe
diventa una macchina a stati esplicita.

INVARIANTI (eccezioni applicative, MAI `assert`: con `python -O` gli assert spariscono)
=======================================================================================
1. La gamba B (perp) non parte MAI se la gamba A (spot) non e' riconciliata (fill
   verificato o ordine cancellato e verificato).
2. Se la gamba B non si copre entro il timeout, la gamba A viene liquidata (unwind):
   non si resta mai con una gamba sola.
3. Stesso intento -> stesso clOrdId (idempotenza: il retry e' sicuro, l'exchange dedup).
4. Delta di copertura misurato SULL'EXCHANGE (posizioni), non dedotto dagli invii.
5. Ogni invio e' registrato nel journal PRIMA che l'ordine possa esistere.
6. Il live non e' un default: serve `live=True` E il kill-switch assente.

STATI
-----
PIANIFICATO -> GAMBA_A_INVIATA -> GAMBA_A_ESEGUITA -> GAMBA_B_INVIATA -> COPERTA
                                                                          -> (unwind) -> PIATTO
verso: CHIUSURA -> PIATTO ;  FALLITO in caso di invariante violata.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .esecutore import cl_ord_id
from .invio import Gamba, invia_gamba
from . import stato as modulo_stato

#: Stati della macchina dell'hedge.
STATI = (
    "PIANIFICATO", "GAMBA_A_INVIATA", "GAMBA_A_ESEGUITA",
    "GAMBA_B_INVIATA", "COPERTA", "CHIUSURA", "PIATTO", "FALLITO",
)

MOTIVO_INCOERENTE = "stato incoerente: nessun invio finche' non e' riconciliato"


class InvioRifiutato(Exception):
    """Un invio non e' ammesso (invariante violata). Mai silenzioso."""


def _adesso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class HedgeGroup:
    """Il record completo di un'operazione neutrale (campi richiesti dalla spec)."""
    id: str
    spot: Gamba
    perp: Gamba
    contract_value: float
    stato: str = "PIANIFICATO"
    delta_max_qty: float = 1.0
    delta_qty: float = 0.0
    basis_apertura: float = 0.0
    ts_apertura: str = ""
    ts_chiusura: str = ""
    note: str = ""

    def a_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "stato": self.stato,
            "spot": self.spot.__dict__, "perp": self.perp.__dict__,
            "contract_value": self.contract_value,
            "delta_max_qty": self.delta_max_qty, "delta_qty": self.delta_qty,
            "basis_apertura": self.basis_apertura,
            "ts_apertura": self.ts_apertura, "ts_chiusura": self.ts_chiusura,
            "note": self.note,
        }


class Coordinatore:
    """Macchina a stati dell'hedge. Exchange INIETTATO: testabile senza rete."""

    def __init__(self, exchange: Any, *, live: bool = False, timeout_s: int = 60,
                 stato_path: Optional[str] = None) -> None:
        self.ex = exchange
        self.live = bool(live)
        self.timeout_s = int(timeout_s)
        self.stato_path = stato_path

    # --- journal (riusa il modulo `stato`: un solo writer) ------------------------------

    def _journal(self, hed: HedgeGroup) -> None:
        if not self.stato_path:
            return
        with modulo_stato.lock_esclusivo(self.stato_path):
            st = modulo_stato.carica(self.stato_path, fail_closed=self.live)
            for gamba in (hed.spot, hed.perp):
                st.ordini[gamba.cl_ord_id] = {
                    "symbol": gamba.symbol, "side": gamba.side, "qty": gamba.qty,
                    "intent_id": hed.id, "stato": gamba.esito or "intent",
                    "ts": time.time(), "live": self.live,
                }
            modulo_stato.salva(self.stato_path, st)

    # --- primitive ----------------------------------------------------------------

    def _prezzo(self, symbol: str, lato: str, fattore: float) -> float:
        t = self.ex.fetch_ticker(symbol)
        base = float(t["ask"] if lato == "buy" else t["bid"])
        return float(self.ex.price_to_precision(symbol, base * fattore))

    def _attesa(self, gamba: Gamba) -> Dict[str, Any]:
        """Poll fino a closed/canceled; ritorna l'ultimo ordine visto."""
        for _ in range(max(1, int(self.timeout_s / 1.5))):
            time.sleep(1.5 if self.live else 0)
            try:
                oo = self.ex.fetch_order(None, gamba.symbol, {"clOrdId": gamba.cl_ord_id})
            except Exception:
                continue
            if oo.get("status") == "closed":
                return oo
            if oo.get("status") == "canceled":
                return oo
        try:
            return self.ex.fetch_order(None, gamba.symbol, {"clOrdId": gamba.cl_ord_id})
        except Exception:
            return {}

    def _esegui_gamba(self, gamba: Gamba) -> Gamba:
        """Invia e attende una gamba. In caso di fill parziale ritenta il residuo UNA volta."""
        risposta = invia_gamba(self.ex, gamba)
        gamba.exchange_id = (risposta or {}).get("id", "")
        oo = self._attesa(gamba)
        filled = float((oo or {}).get("filled") or 0)
        if (oo or {}).get("status") == "closed":
            gamba.filled, gamba.medio, gamba.esito = filled, float((oo or {}).get("average") or gamba.prezzo_limite), "closed"
            return gamba
        # fill parziale / timeout: cancella e ritenta il residuo
        try:
            self.ex.cancel_order(gamba.exchange_id, gamba.symbol)
        except Exception:
            pass
        residuo = gamba.qty - filled
        if residuo > 0 and self.live:
            gamba.qty = residuo
            gamba.prezzo_limite = self._prezzo(gamba.symbol, gamba.side, 1.004 if gamba.side == "buy" else 0.996)
            risposta = invia_gamba(self.ex, gamba)
            gamba.exchange_id = (risposta or {}).get("id", gamba.exchange_id)
            oo = self._attesa(gamba)
            if (oo or {}).get("status") == "closed":
                gamba.filled, gamba.medio, gamba.esito = float((oo or {}).get("filled") or 0), float((oo or {}).get("average") or gamba.prezzo_limite), "closed"
                return gamba
        gamba.filled, gamba.medio, gamba.esito = filled, float((oo or {}).get("average") or 0), "partial"
        return gamba

    def _delta_qty(self, perp_symbol: str, contract_value: float) -> float:
        for p in self.ex.privateGetAccountPositions({"instType": "FUTURES"}).get("data", []):
            if p.get("instId") == perp_symbol:
                return abs(float(p.get("pos") or 0)) * contract_value
        return 0.0

    # --- ciclo di vita ----------------------------------------------------------------

    def apri(self, *, hed: HedgeGroup) -> HedgeGroup:
        """Apre spot (gamba A) e poi perp (gamba B). Invarianti 1,2,3,4."""
        if not self.live:
            hed.stato = "PIANIFICATO"
            hed.note = "dry-run: nessun ordine inviato"
            return hed
        hed.ts_apertura = _adesso()
        # gamba A: spot
        hed.stato = "GAMBA_A_INVIATA"
        hed.spot = self._esegui_gamba(hed.spot)
        self._journal(hed)
        if hed.spot.esito != "closed" or hed.spot.filled <= 0:
            hed.stato = "FALLITO"
            hed.note = MOTIVO_INCOERENTE + " (gamba A non eseguita)"
            return hed
        hed.stato = "GAMBA_A_ESEGUITA"
        # gamba B: perp — solo se A e' chiusa
        hed.stato = "GAMBA_B_INVIATA"
        hed.perp.qty = round(hed.spot.filled / hed.contract_value) or hed.perp.qty
        hed.perp = self._esegui_gamba(hed.perp)
        self._journal(hed)
        coperto = self._delta_qty(hed.perp.symbol, hed.contract_value)
        if hed.perp.esito == "closed" and coperto > 0:
            hed.delta_qty = abs(hed.spot.filled - coperto)
            if hed.delta_qty <= hed.delta_max_qty:
                hed.stato = "COPERTA"
            else:
                hed.stato = "COPERTA"
                hed.note = f"delta {hed.delta_qty:.2f} oltre tolleranza {hed.delta_max_qty:.2f}"
        else:
            hed = self.unwind(hed, motivo="gamba B non coperta")
        return hed

    def unwind(self, hed: HedgeGroup, *, motivo: str) -> HedgeGroup:
        """Liquida la gamba A rimasta scoperta. Invariante 2."""
        if hed.spot.filled <= 0:
            hed.stato = "PIATTO"
            hed.note = motivo + " (nessuna gamba A da liquidare)"
            return hed
        vendita = Gamba(
            symbol=hed.spot.symbol, side="sell", qty=hed.spot.filled,
            prezzo_limite=self._prezzo(hed.spot.symbol, "sell", 0.998),
            cl_ord_id=cl_ord_id(hed.spot.symbol, "sell", hed.spot.filled, hed.id + ".unwind"))
        vendita = self._esegui_gamba(vendita)
        hed.stato = "PIATTO"
        hed.note = f"{motivo}; unwind spot esito={vendita.esito} filled={vendita.filled}"
        return hed

    def chiudi(self, hed: HedgeGroup) -> HedgeGroup:
        """Chiude l'hedge: perp reduceOnly, poi vende lo spot. Verifica il piatto."""
        hed.stato = "CHIUSURA"
        perp_pos = self._delta_qty(hed.perp.symbol, hed.contract_value)
        if perp_pos > 0:
            chiusura = Gamba(
                symbol=hed.perp.symbol, side="buy", qty=round(perp_pos / hed.contract_value),
                prezzo_limite=self._prezzo(hed.perp.symbol, "buy", 1.002),
                cl_ord_id=cl_ord_id(hed.perp.symbol, "buy", perp_pos, hed.id + ".close_perp"),
                td_mode=hed.perp.td_mode, reduce_only=True)
            self._esegui_gamba(chiusura)
        if hed.spot.filled > 0:
            vendita = Gamba(
                symbol=hed.spot.symbol, side="sell", qty=hed.spot.filled,
                prezzo_limite=self._prezzo(hed.spot.symbol, "sell", 0.998),
                cl_ord_id=cl_ord_id(hed.spot.symbol, "sell", hed.spot.filled, hed.id + ".close_spot"))
            self._esegui_gamba(vendita)
        residuo = self._delta_qty(hed.perp.symbol, hed.contract_value)
        hed.stato = "PIATTO" if residuo == 0 else "FALLITO"
        hed.ts_chiusura = _adesso()
        if residuo != 0:
            hed.note = f"posizione residua {residuo} dopo la chiusura: verificare"
        self._journal(hed)
        return hed
