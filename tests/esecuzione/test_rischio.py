"""Limiti del mandato: ogni freno deve bloccare esattamente al confine dichiarato.

Il rischio per operazione si misura sullo STOP (audit #4): `nozionale x distanza_stop`
contro il tetto del 2% del mandato. Il vecchio contratto — 2% sul NOZIONALE — e'
proprio il "blocco fittizio" che rifiutava qualsiasi spot sopra ~22 EUR su un conto
da ~1.100: i test qui sotto lo fissano fuori per sempre.
"""
import pytest

from money.esecuzione import rischio


def test_dentro_il_limite_passa():
    # nozionale 30 con stop al 5%: rischio 1,5 = 1,5% di 100 — sotto il tetto del 2%
    assert rischio.rischio_per_trade(30.0, 100.0, 0.05).ok
    assert rischio.rischio_per_trade(40.0, 100.0, 0.05).ok    # 2,0% esatto: passa


def test_oltre_il_limite_blocca():
    v = rischio.rischio_per_trade(40.01, 100.0, 0.05)
    assert not v.ok and "2%" in v.motivo


def test_il_nozionale_da_solo_non_e_il_rischio():
    """Regressione audit #4: 40 EUR con stop all'1% rischiano 0,4 = 0,4% — passano.
    E' la DISTANZA dallo stop a fare il rischio, non la taglia dell'ordine."""
    assert rischio.rischio_per_trade(40.0, 100.0, 0.01).ok
    v = rischio.rischio_per_trade(240.0, 100.0, 0.01)         # 2,4% > 2%: bloccato
    assert not v.ok


def test_senza_distanza_stop_blocca():
    """Uno spot senza stop non ha un rischio definito: fail-closed, mai un default."""
    v = rischio.rischio_per_trade(1.0, 100.0)
    assert not v.ok and "stop" in v.motivo
    assert not rischio.rischio_per_trade(1.0, 100.0, 0.0).ok      # distanza zero
    assert not rischio.rischio_per_trade(1.0, 100.0, 1.5).ok      # distanza implausibile


def test_distanza_stop_relativa():
    assert rischio.distanza_stop_relativa(80000.0, 76000.0) == pytest.approx(0.05)
    assert rischio.distanza_stop_relativa(80000.0, 84000.0) == pytest.approx(0.05)


def test_equity_non_positiva_blocca_sempre():
    """Un controllo che non si puo' calcolare e' un controllo fallito."""
    assert not rischio.rischio_per_trade(1.0, 0.0, 0.05).ok
    assert not rischio.rischio_per_trade(1.0, -5.0, 0.05).ok
    assert not rischio.rischio_per_trade(-1.0, 100.0, 0.05).ok    # input rotto


def test_stop_giornaliero_al_confine():
    assert rischio.stop_giornaliero(-2.99, 100.0).ok         # -2,99%: ancora ok
    assert not rischio.stop_giornaliero(-3.0, 100.0).ok      # -3,0%: fermo
    assert not rischio.stop_giornaliero(-10.0, 100.0).ok


def test_stop_giornaliero_senza_equity_e_prudente():
    assert not rischio.stop_giornaliero(0.0, 0.0).ok


def test_drawdown_al_confine():
    assert rischio.drawdown_massimo(90.0, 100.0).ok          # -10% esatto: ok (limite incluso)
    assert not rischio.drawdown_massimo(89.99, 100.0).ok     # oltre: fermo
    assert not rischio.drawdown_massimo(50.0, 100.0).ok


def test_drawdown_con_picco_rotto_blocca():
    assert not rischio.drawdown_massimo(10.0, 0.0).ok


def test_kill_switch_file(tmp_path):
    p = str(tmp_path / "KILL")
    assert not rischio.kill_switch_attivo(p)
    rischio.attiva_kill_switch(p, "test")
    assert rischio.kill_switch_attivo(p)
    rischio.disattiva_kill_switch(p)
    assert not rischio.kill_switch_attivo(p)
