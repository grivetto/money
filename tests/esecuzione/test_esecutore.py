"""L'esecutore: sizing corretto, idempotenza, e il live che non parte per caso."""
import os

import pytest

from money.esecuzione import esecutore as ez
from money.esecuzione.rischio import attiva_kill_switch


class ExchangeCheEsplode:
    """Se il dry-run tocca l'exchange, il test deve fallire."""
    def __getattr__(self, nome):
        raise AssertionError(f"il dry-run ha chiamato l'exchange ({nome}): VIETATO")


@pytest.fixture()
def ambiente(tmp_path, monkeypatch):
    monkeypatch.delenv("MONEY_LIVE_ARMED", raising=False)
    return {
        "stato_path": str(tmp_path / "stato.json"),
        "kill_path": str(tmp_path / "KILL"),
        "promo": tmp_path / "promozione.txt",
    }


# --- sizing (la lezione int(step)) -------------------------------------------------------

def test_step_un_millesimo_non_vale_zero():
    assert ez.decimali_di_step(0.001) == 3
    assert ez.arrotonda_a_step(1.23456, 0.001) == 1.234
    assert ez.arrotonda_a_step(0.00007758, 0.00001) == 0.00007


def test_mai_arrotondare_in_su_sul_capitale(ambiente):
    e = ez.Esecutore(**ambiente_arg(ambiente))
    o = e.costruisci("BTC/EUR", "buy", 6.50075, 83784.2, 0.00001, 1.0)
    assert o.qty * o.prezzo_riferimento <= 6.50075 + 1e-9
    assert o.qty == 0.00007


def ambiente_arg(amb):
    return {"stato_path": amb["stato_path"], "kill_path": amb["kill_path"]}


def test_nozionale_sotto_min_notional_rifiutato(ambiente):
    e = ez.Esecutore(**ambiente_arg(ambiente))
    with pytest.raises(ez.Rifiutato, match="NON_FATTIBILE"):
        e.costruisci("BTC/EUR", "buy", 0.50, 80000.0, 0.00001, 1.0)


def test_input_rotti_sono_assertion(ambiente):
    e = ez.Esecutore(**ambiente_arg(ambiente))
    with pytest.raises(AssertionError):
        e.costruisci("BTC/EUR", "buy", 10.0, 0.0, 0.00001, 1.0)
    with pytest.raises(AssertionError):
        e.costruisci("BTC/EUR", "buy", 10.0, 100.0, 0.0, 1.0)


# --- idempotenza --------------------------------------------------------------------------

def test_cl_ord_id_deterministico():
    a = ez.cl_ord_id("BTC/EUR", "buy", 0.0001, "2026-09-27")
    b = ez.cl_ord_id("BTC/EUR", "buy", 0.0001, "2026-09-27")
    c = ez.cl_ord_id("BTC/EUR", "buy", 0.0002, "2026-09-27")
    assert a == b and a != c and a.startswith("mny") and len(a) <= 32


# --- esecuzione dry vs live -----------------------------------------------------------------

def test_dry_run_non_tocca_exchange_e_registra(ambiente):
    e = ez.Esecutore(exchange=ExchangeCheEsplode(), **ambiente_arg(ambiente))
    o = e.costruisci("BTC/EUR", "buy", 2.0, 80000.0, 0.00001, 1.0)
    r = e.esegui(o, equity=100.0, exchange=ExchangeCheEsplode())
    assert r["etichetta"] == ez.ETICHETTA_DRY and r["esito"] == "registrato_dry_run"
    from money.esecuzione.stato import carica
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


def test_live_armato_con_promozione_costruisce(ambiente, monkeypatch):
    monkeypatch.setenv("MONEY_LIVE_ARMED", "1")
    ambiente["promo"].write_text("promossa dal cancello\n", encoding="utf-8")
    e = ez.Esecutore(live=True, promozione_path=str(ambiente["promo"]),
                     **ambiente_arg(ambiente))
    assert e.live is True


def test_kill_switch_ferma_tutto_anche_il_dry(ambiente):
    attiva_kill_switch(ambiente["kill_path"], "test")
    e = ez.Esecutore(**ambiente_arg(ambiente))
    o = e.costruisci("BTC/EUR", "buy", 2.0, 80000.0, 0.00001, 1.0)
    with pytest.raises(ez.Rifiutato, match="kill switch"):
        e.esegui(o, equity=100.0)


def test_rischio_per_trade_blocca_ordine_grosso(ambiente):
    e = ez.Esecutore(**ambiente_arg(ambiente))
    o = e.costruisci("BTC/EUR", "buy", 5.0, 80000.0, 0.00001, 1.0)  # 5% di 100
    with pytest.raises(ez.Rifiutato, match="rischio_per_trade"):
        e.esegui(o, equity=100.0)
