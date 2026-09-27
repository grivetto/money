"""Limiti del mandato: ogni freno deve bloccare esattamente al confine dichiarato."""
from money.esecuzione import rischio


def test_dentro_il_limite_passa():
    assert rischio.rischio_per_trade(2.0, 100.0).ok          # 2,0% esatto: passa
    assert rischio.rischio_per_trade(1.99, 100.0).ok


def test_oltre_il_limite_blocca():
    v = rischio.rischio_per_trade(2.01, 100.0)
    assert not v.ok and "2%" in v.motivo


def test_equity_non_positiva_blocca_sempre():
    """Un controllo che non si puo' calcolare e' un controllo fallito."""
    assert not rischio.rischio_per_trade(1.0, 0.0).ok
    assert not rischio.rischio_per_trade(1.0, -5.0).ok
    assert not rischio.rischio_per_trade(-1.0, 100.0).ok     # input rotto


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
