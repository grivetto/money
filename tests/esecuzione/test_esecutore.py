"""L'esecutore: sizing corretto, idempotenza per INTENTO, journal/recovery,
lock esclusivo e il live che non parte per caso (revisione Manus 06/10)."""
import pytest

from money.esecuzione import esecutore as ez
from money.esecuzione import stato as modulo_stato
from money.esecuzione.rischio import attiva_kill_switch
from money.esecuzione.stato import Stato, carica, salva


class ExchangeCheEsplode:
    """Se il dry-run tocca l'exchange, il test deve fallire."""
    def __getattr__(self, nome):
        raise AssertionError(f"il dry-run ha chiamato l'exchange ({nome}): VIETATO")


class ExchangeFinto:
    """Exchange minimale per il percorso live (preflight + invio + recovery)."""

    def __init__(self, perm="read_only,trade", ordini=None, esplodi_fetch=False):
        self._perm = perm
        self.ordini = dict(ordini or {})       # clOrdId -> risposta fetch_order
        self.invii = []
        self.esplodi_fetch = esplodi_fetch

    def privateGetAccountConfig(self):
        return {"data": [{"perm": self._perm}]}

    def load_markets(self):
        self.markets = {"BTC/EUR": {"active": True, "limits": {"cost": {"min": 1.0}}}}

    def fetch_balance(self, _params):
        return {"EUR": {"free": 1000.0}}

    def create_order(self, symbol, tipo, side, qty, prezzo=None, params=None):
        cid = params["clOrdId"]
        self.invii.append({"clOrdId": cid, "symbol": symbol, "side": side, "qty": qty})
        self.ordini[cid] = {"id": "ex-" + cid, "status": "closed", "clOrdId": cid}
        return {"id": "ex-" + cid}

    def fetch_order(self, oid, symbol=None, params=None):
        if self.esplodi_fetch:
            raise ConnectionError("rete giu'")
        cid = (params or {}).get("clOrdId") or oid
        if cid in self.ordini:
            return self.ordini[cid]
        raise Exception("Order not found")


@pytest.fixture()
def ambiente(tmp_path, monkeypatch):
    monkeypatch.delenv("MONEY_LIVE_ARMED", raising=False)
    return {
        "stato_path": str(tmp_path / "stato.json"),
        "kill_path": str(tmp_path / "KILL"),
        "promo": tmp_path / "promozione.txt",
    }


def ambiente_arg(amb):
    return {"stato_path": amb["stato_path"], "kill_path": amb["kill_path"]}


@pytest.fixture()
def live(ambiente, monkeypatch):
    """Armatura completa: MONEY_LIVE_ARMED=1 + PromotionArtifact FIRMATO e valido.

    Il lock live non accetta piu' un file qualsiasi: la fixture costruisce l'artefatto
    con `promozione.crea` e lo scrive con `promozione.scrivi`, come farebbe il cancello.
    """
    from money.esecuzione import promozione as PR

    monkeypatch.setenv("MONEY_LIVE_ARMED", "1")
    art = PR.crea(strategy_id="test_live", nome="fixture", capitale_max_eur=100.0,
                  n_tentativi_ipotesi=24, n_tentativi_cumulativi=311838, dsr=0.97)
    ambiente["promozione"] = str(PR.scrivi(art, ambiente["promo"].parent))
    return ambiente


def test_live_rifiuta_file_di_promozione_spazzatura(ambiente, monkeypatch):
    """Regressione: prima il lock accettava qualsiasi file esistente (verificato in probe)."""
    monkeypatch.setenv("MONEY_LIVE_ARMED", "1")
    ambiente["promo"].write_text('{"non": "una promozione"}', encoding="utf-8")
    with pytest.raises(ez.Rifiutato, match="promozione non valida"):
        ez.Esecutore(live=True, promozione_path=str(ambiente["promo"]), **ambiente_arg(ambiente))


def test_live_rifiuta_promozione_manomessa(live):
    import json
    from pathlib import Path

    p = Path(live["promozione"])
    d = json.loads(p.read_text(encoding="utf-8"))
    d["capitale_max_eur"] = 999999.0          # manomissione: l'hash non torna piu'
    p.write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(ez.Rifiutato, match="promozione non valida"):
        ez.Esecutore(live=True, promozione_path=live["promozione"], **ambiente_arg(live))


# --- sizing (la lezione int(step)) -------------------------------------------------------

def test_step_un_millesimo_non_vale_zero():
    assert ez.decimali_di_step(0.001) == 3
    assert ez.arrotonda_a_step(1.23456, 0.001) == 1.234
    assert ez.arrotonda_a_step(0.00007758, 0.00001) == 0.00007


def test_mai_arrotondare_in_su_sul_capitale(ambiente):
    e = ez.Esecutore(**ambiente_arg(ambiente))
    o = e.costruisci("BTC/EUR", "buy", 6.50075, 83784.2, 0.00001, 1.0, intent_id="t1")
    assert o.qty * o.prezzo_riferimento <= 6.50075 + 1e-9
    assert o.qty == 0.00007


def test_nozionale_sotto_min_notional_rifiutato(ambiente):
    e = ez.Esecutore(**ambiente_arg(ambiente))
    with pytest.raises(ez.Rifiutato, match="NON_FATTIBILE"):
        e.costruisci("BTC/EUR", "buy", 0.50, 80000.0, 0.00001, 1.0, intent_id="t1")


def test_input_rotti_sono_rifiutati(ambiente):
    """Invarianti economiche = eccezioni applicative, NON assert: con `python -O` gli
    assert vengono rimossi e un controllo di capitale non puo' sparire."""
    e = ez.Esecutore(**ambiente_arg(ambiente))
    with pytest.raises(ez.Rifiutato, match="prezzo"):
        e.costruisci("BTC/EUR", "buy", 10.0, 0.0, 0.00001, 1.0, intent_id="t1")
    with pytest.raises(ez.Rifiutato, match="step"):
        e.costruisci("BTC/EUR", "buy", 10.0, 100.0, 0.0, 1.0, intent_id="t1")
    with pytest.raises(ez.Rifiutato, match="nozionale"):
        e.costruisci("BTC/EUR", "buy", 0.0, 100.0, 0.00001, 1.0, intent_id="t1")


# --- idempotenza per INTENTO (non per giorno) -------------------------------------------

def test_cl_ord_id_per_intento_non_per_giorno():
    a = ez.cl_ord_id("BTC/EUR", "buy", 0.0001, "intent-1")
    b = ez.cl_ord_id("BTC/EUR", "buy", 0.0001, "intent-1")
    c = ez.cl_ord_id("BTC/EUR", "buy", 0.0001, "intent-2")
    assert a == b and a != c and a.startswith("mny") and len(a) <= 32


def test_due_intenti_uguali_stesso_giorno_hanno_id_diversi(ambiente):
    """Il caso che il vecchio schema giorno+quantita' non distingueva."""
    e = ez.Esecutore(**ambiente_arg(ambiente))
    o1 = e.costruisci("BTC/EUR", "buy", 2.0, 80000.0, 0.00001, 1.0, intent_id="segnale-A")
    o2 = e.costruisci("BTC/EUR", "buy", 2.0, 80000.0, 0.00001, 1.0, intent_id="segnale-B")
    assert o1.cl_ord_id != o2.cl_ord_id


def test_retry_dopo_restart_stesso_id(ambiente):
    e = ez.Esecutore(**ambiente_arg(ambiente))
    o1 = e.costruisci("BTC/EUR", "buy", 2.0, 80000.0, 0.00001, 1.0, intent_id="segnale-A")
    e2 = ez.Esecutore(**ambiente_arg(ambiente))  # "restart"
    o2 = e2.costruisci("BTC/EUR", "buy", 2.0, 80000.0, 0.00001, 1.0, intent_id="segnale-A")
    assert o1.cl_ord_id == o2.cl_ord_id


def test_intent_id_obbligatorio(ambiente):
    e = ez.Esecutore(**ambiente_arg(ambiente))
    with pytest.raises(ez.Rifiutato, match="intent_id"):
        e.costruisci("BTC/EUR", "buy", 2.0, 80000.0, 0.00001, 1.0)
    with pytest.raises(ez.Rifiutato, match="intent_id"):
        e.costruisci("BTC/EUR", "buy", 2.0, 80000.0, 0.00001, 1.0, intent_id="spazi no!")


# --- esecuzione dry vs live --------------------------------------------------------------

def test_dry_run_non_tocca_exchange_e_registra(ambiente):
    e = ez.Esecutore(exchange=ExchangeCheEsplode(), **ambiente_arg(ambiente))
    o = e.costruisci("BTC/EUR", "buy", 2.0, 80000.0, 0.00001, 1.0, intent_id="t1")
    r = e.esegui(o, equity=100.0, exchange=ExchangeCheEsplode())
    assert r["etichetta"] == ez.ETICHETTA_DRY and r["esito"] == "registrato_dry_run"
    st = carica(ambiente["stato_path"])
    assert o.cl_ord_id in st.ordini and st.ordini[o.cl_ord_id]["live"] is False


def test_live_senza_armatura_rifiutato(ambiente):
    with pytest.raises(ez.Rifiutato, match="MONEY_LIVE_ARMED"):
        ez.Esecutore(live=True, **ambiente_arg(ambiente))


def test_live_armato_ma_senza_promozione_rifiutato(ambiente, monkeypatch):
    monkeypatch.setenv("MONEY_LIVE_ARMED", "1")
    with pytest.raises(ez.Rifiutato, match="promozione"):
        ez.Esecutore(live=True, promozione_path=str(ambiente["promo"]),
                     **ambiente_arg(ambiente))


def test_live_armato_con_promozione_costruisce(live):
    e = ez.Esecutore(live=True, promozione_path=live["promozione"], **ambiente_arg(live))
    assert e.live is True


def test_kill_switch_ferma_tutto_anche_il_dry(ambiente):
    attiva_kill_switch(ambiente["kill_path"], "test")
    e = ez.Esecutore(**ambiente_arg(ambiente))
    o = e.costruisci("BTC/EUR", "buy", 2.0, 80000.0, 0.00001, 1.0, intent_id="t1")
    with pytest.raises(ez.Rifiutato, match="kill switch"):
        e.esegui(o, equity=100.0)


def test_rischio_per_trade_blocca_ordine_grosso(ambiente):
    e = ez.Esecutore(**ambiente_arg(ambiente))
    o = e.costruisci("BTC/EUR", "buy", 5.0, 80000.0, 0.00001, 1.0, intent_id="t1")  # 5% di 100
    with pytest.raises(ez.Rifiutato, match="rischio_per_trade"):
        e.esegui(o, equity=100.0)


# --- live: stato corrotto, lock, recovery (revisione Manus 06/10) ------------------------

def test_live_rifiuta_stato_corrotto(live):
    with open(live["stato_path"], "w", encoding="utf-8") as f:
        f.write("{corrotto")
    e = ez.Esecutore(live=True, promozione_path=live["promozione"], **ambiente_arg(live))
    o = e.costruisci("BTC/EUR", "buy", 2.0, 80000.0, 0.00001, 1.0, intent_id="i1")
    with pytest.raises(modulo_stato.StatoCorrotto):
        e.esegui(o, equity=1000.0, exchange=ExchangeFinto())


def test_un_solo_writer_per_stato(live):
    e = ez.Esecutore(live=True, promozione_path=live["promozione"], **ambiente_arg(live))
    o = e.costruisci("BTC/EUR", "buy", 2.0, 80000.0, 0.00001, 1.0, intent_id="i1")
    with modulo_stato.lock_esclusivo(live["stato_path"]):
        with pytest.raises(modulo_stato.LockOccupato):
            e.esegui(o, equity=1000.0, exchange=ExchangeFinto())


def test_live_invia_e_registra_inviato(live):
    ex = ExchangeFinto()
    e = ez.Esecutore(live=True, promozione_path=live["promozione"], **ambiente_arg(live))
    o = e.costruisci("BTC/EUR", "buy", 2.0, 80000.0, 0.00001, 1.0, intent_id="i1")
    r = e.esegui(o, equity=1000.0, exchange=ex)
    assert r["esito"] == "inviato"
    st = carica(live["stato_path"])
    assert st.ordini[o.cl_ord_id]["stato"] == "inviato"
    assert ex.invii and ex.invii[0]["clOrdId"] == o.cl_ord_id


def test_restart_riconcilia_l_ordine_arrivato(live):
    """Crash DOPO create_order e prima del salvataggio: il pendente resta 'intent'
    su disco; al riavvio viene trovato sull'exchange per clOrdId e riconciliato
    PRIMA che parta il nuovo ordine."""
    ex = ExchangeFinto()
    e = ez.Esecutore(live=True, promozione_path=live["promozione"], **ambiente_arg(live))
    o1 = e.costruisci("BTC/EUR", "buy", 2.0, 80000.0, 0.00001, 1.0, intent_id="i1")
    salva(live["stato_path"], Stato(ordini={
        o1.cl_ord_id: {"symbol": "BTC/EUR", "side": "buy", "qty": o1.qty,
                       "stato": "intent", "ts": 0.0, "live": True}}))
    ex.ordini[o1.cl_ord_id] = {"id": "ex-1", "status": "closed", "clOrdId": o1.cl_ord_id}
    o2 = e.costruisci("BTC/EUR", "sell", 2.0, 80000.0, 0.00001, 1.0, intent_id="i2")
    e.esegui(o2, equity=1000.0, exchange=ex)
    st = carica(live["stato_path"])
    assert st.ordini[o1.cl_ord_id]["stato"] == "riconciliato"
    assert st.ordini[o2.cl_ord_id]["stato"] == "inviato"


def test_restart_segna_assente_l_ordine_mai_arrivato(live):
    ex = ExchangeFinto()
    e = ez.Esecutore(live=True, promozione_path=live["promozione"], **ambiente_arg(live))
    o1 = e.costruisci("BTC/EUR", "buy", 2.0, 80000.0, 0.00001, 1.0, intent_id="i1")
    salva(live["stato_path"], Stato(ordini={
        o1.cl_ord_id: {"symbol": "BTC/EUR", "side": "buy", "qty": o1.qty,
                       "stato": "intent", "ts": 0.0, "live": True}}))
    o2 = e.costruisci("BTC/EUR", "buy", 2.0, 80000.0, 0.00001, 1.0, intent_id="i2")
    e.esegui(o2, equity=1000.0, exchange=ex)
    st = carica(live["stato_path"])
    assert st.ordini[o1.cl_ord_id]["stato"] == "assente_su_exchange"


def test_recovery_con_rete_giu_blocca_i_nuovi_invii(live):
    ex = ExchangeFinto(esplodi_fetch=True)
    e = ez.Esecutore(live=True, promozione_path=live["promozione"], **ambiente_arg(live))
    o1 = e.costruisci("BTC/EUR", "buy", 2.0, 80000.0, 0.00001, 1.0, intent_id="i1")
    salva(live["stato_path"], Stato(ordini={
        o1.cl_ord_id: {"symbol": "BTC/EUR", "side": "buy", "qty": o1.qty,
                       "stato": "inviato", "ts": 0.0, "live": True}}))
    o2 = e.costruisci("BTC/EUR", "buy", 2.0, 80000.0, 0.00001, 1.0, intent_id="i2")
    with pytest.raises(ez.Rifiutato, match="recovery"):
        e.esegui(o2, equity=1000.0, exchange=ex)
    assert ex.invii == []  # nessun nuovo ordine e' partito
