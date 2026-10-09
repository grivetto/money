"""Test del Coordinatore: macchina a stati dell'hedge a due gambe.

Exchange INIETTATO (nessuna rete, nessun conto reale): i casi che oggi facevano
divergere `esecutore.py` e `canary_carry.py` sono qui coperti come invarianti.
"""
import pytest

from money.esecuzione import coordinatore as CO
from money.esecuzione.coordinatore import Coordinatore, Gamba, HedgeGroup
from money.esecuzione.esecutore import cl_ord_id

SPOT = "DOGE/USDC"
PERP = "DOGE/USD:USD-310404"
CV = 10.0
Q_SPOT = 110.0


class ExFinto:
    """Simulatore d'exchange: `piano` = sequenza di esiti per gamba, l'ultimo si ripete.

    esiti per gamba: 'closed' (fill pieno), 'partial' (fill parziale), 'open' (mai chiuso = timeout).
    """

    def __init__(self, *, piano=None):
        self.piano = piano or {"spot": ["closed"], "perp": ["closed"]}
        self.conta = {}
        self.ordini = {}
        self.invii = []
        self.cancellati = []
        self._perp_pos = 0.0

    def load_markets(self):
        pass

    def price_to_precision(self, _symbol, px):
        return px

    def fetch_ticker(self, _symbol):
        return {"ask": 1.01, "bid": 0.99, "last": 1.0}

    def _gamba(self, symbol):
        return "perp" if symbol == PERP else "spot"

    def _prossimo_esito(self, gamba):
        lst = self.piano.get(gamba, ["closed"])
        i = self.conta.get(gamba, 0)
        self.conta[gamba] = i + 1
        return lst[min(i, len(lst) - 1)]

    def create_order(self, symbol, tipo, side, qty, price, params):
        cid = params["clOrdId"]
        gamba = self._gamba(symbol)
        esito = self._prossimo_esito(gamba)
        if esito == "closed":
            o = {"id": "ex-" + cid, "status": "closed", "filled": qty, "average": price, "clOrdId": cid}
        elif esito == "partial":
            o = {"id": "ex-" + cid, "status": "canceled", "filled": qty / 2, "average": price, "clOrdId": cid}
        else:
            o = {"id": "ex-" + cid, "status": "open", "filled": 0.0, "average": 0.0, "clOrdId": cid}
        self.ordini[cid] = o
        self.invii.append({"cid": cid, "symbol": symbol, "side": side, "qty": qty, "price": price})
        # aggiorna la posizione perp sui fill chiusi
        if symbol == PERP and o["status"] == "closed":
            if params.get("reduceOnly"):
                self._perp_pos -= qty
            else:
                self._perp_pos += qty
        return {"id": o["id"]}

    def fetch_order(self, oid, symbol=None, params=None):
        cid = (params or {}).get("clOrdId") or oid
        return self.ordini.get(cid, {"status": "open", "filled": 0.0, "clOrdId": cid})

    def cancel_order(self, oid, _symbol=None):
        self.cancellati.append(oid)
        return {"status": "canceled"}

    def privateGetAccountPositions(self, _params):
        if self._perp_pos:
            return {"data": [{"instId": PERP, "pos": str(self._perp_pos)}]}
        return {"data": []}


@pytest.fixture()
def niente_attese(monkeypatch):
    monkeypatch.setattr(CO.time, "sleep", lambda _s: None)


def _hed(ident="c1-2026-10-09", qty_spot=Q_SPOT, ct=11.0):
    return HedgeGroup(
        id=ident,
        spot=Gamba(SPOT, "buy", qty_spot, 1.01, cl_ord_id(SPOT, "buy", qty_spot, ident)),
        perp=Gamba(PERP, "sell", ct, 0.99, cl_ord_id(PERP, "sell", ct, ident), td_mode="isolated"),
        contract_value=CV)


# --- dry-run: nessun ordine, mai ------------------------------------------------------

def test_dry_run_non_invia_nulla(niente_attese):
    ex = ExFinto()
    hed = Coordinatore(ex, live=False).apri(hed=_hed())
    assert hed.stato == "PIANIFICATO"
    assert ex.invii == []


# --- apertura completa ----------------------------------------------------------------

def test_apertura_completa_coperta(niente_attese):
    ex = ExFinto()
    hed = Coordinatore(ex, live=True, timeout_s=1).apri(hed=_hed())
    assert hed.stato == "COPERTA"
    assert [i["side"] for i in ex.invii] == ["buy", "sell"]   # spot buy, perp sell
    assert hed.delta_qty == 0.0


# --- invariante 1: la gamba B non parte se A non e' riconciliata ----------------------

def test_spot_parziale_non_apre_il_perp(niente_attese):
    ex = ExFinto(piano={"spot": ["partial"], "perp": ["closed"]})
    hed = Coordinatore(ex, live=True, timeout_s=1).apri(hed=_hed())
    assert hed.stato == "FALLITO"
    assert all(i["symbol"] == SPOT for i in ex.invii), "il perp non deve MAI essere inviato"


# --- invariante 2: gamba orfana -> unwind --------------------------------------------

def test_perp_non_coperto_fa_unwind(niente_attese):
    ex = ExFinto(piano={"spot": ["closed"], "perp": ["open"]})
    hed = Coordinatore(ex, live=True, timeout_s=1).apri(hed=_hed())
    assert hed.stato == "PIATTO"
    # deve esistere una VENDITA spot di unwind
    vendite_spot = [i for i in ex.invii if i["symbol"] == SPOT and i["side"] == "sell"]
    assert vendite_spot, "la gamba spot scoperta deve essere liquidata"


# --- chiusura: verifica il piatto -----------------------------------------------------

def test_chiusura_verifica_piatto(niente_attese):
    ex = ExFinto()
    co = Coordinatore(ex, live=True, timeout_s=1)
    hed = co.apri(hed=_hed())
    assert hed.stato == "COPERTA"
    hed = co.chiudi(hed)
    assert hed.stato == "PIATTO"
    assert ex.privateGetAccountPositions({})["data"] == []


# --- idempotenza: lo stesso intento produce lo stesso clOrdId -------------------------

def test_clordid_deterministico_per_intento():
    a = cl_ord_id(SPOT, "buy", Q_SPOT, "c1-2026-10-09")
    b = cl_ord_id(SPOT, "buy", Q_SPOT, "c1-2026-10-09")
    c = cl_ord_id(SPOT, "buy", Q_SPOT, "c1-2026-10-10")
    assert a == b and a != c


# --- journal: l'intento e' su disco ---------------------------------------------------

def test_journal_scritto(niente_attese, tmp_path):
    sp = str(tmp_path / "stato.json")
    ex = ExFinto()
    hed = Coordinatore(ex, live=True, timeout_s=1, stato_path=sp).apri(hed=_hed())
    from money.esecuzione import stato as modulo_stato
    st = modulo_stato.carica(sp, fail_closed=True)
    assert hed.spot.cl_ord_id in st.ordini
    assert hed.perp.cl_ord_id in st.ordini


# --- nessun `assert` nel coordinatore (sopravvive a python -O) ------------------------

def test_coordinatore_senza_assert():
    from pathlib import Path
    sorgente = Path(CO.__file__).read_text(encoding="utf-8")
    assert "\n        assert " not in sorgente and "\n    assert " not in sorgente
