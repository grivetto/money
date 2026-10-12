"""Test del cancello unico (`money.esecuzione.cancello`).

Il cancello e' l'UNICO punto che ammette o rifiuta, condiviso da Esecutore e canary.
Qui si fissa il contratto: senza stop -> RIFIUTO (mai un default), stop dal lato
sbagliato -> RIFIUTO, equity assente -> RIFIUTO, oltre i limiti -> RIFIUTO.
"""
from money.esecuzione.cancello import MOTIVO_SENZA_STOP, gate_pre_trade


def test_senza_stop_rifiuta():
    d = gate_pre_trade(equity=1000.0, simbolo="DOGE/USDC", lato="buy", prezzo=0.10,
                       quantita=100.0, prezzo_stop=None)
    assert not d.ok
    assert MOTIVO_SENZA_STOP in d.motivi


def test_con_stop_valido_ammette():
    d = gate_pre_trade(equity=1000.0, simbolo="DOGE/USDC", lato="buy", prezzo=0.10,
                       quantita=50.0, prezzo_stop=0.095)
    assert d.ok
    assert d.prezzo_stop == 0.095


def test_stop_dal_lato_sbagliato_rifiuta():
    d = gate_pre_trade(equity=1000.0, simbolo="DOGE/USDC", lato="buy", prezzo=0.10,
                       quantita=50.0, prezzo_stop=0.105)
    assert not d.ok
    assert any("non sotto l'ingresso" in m for m in d.motivi)


def test_equity_non_positiva_rifiuta():
    d = gate_pre_trade(equity=0.0, simbolo="DOGE/USDC", lato="buy", prezzo=0.10,
                       quantita=50.0, prezzo_stop=0.095)
    assert not d.ok
    assert any("equity" in m for m in d.motivi)


def test_nozionale_oltre_concentrazione_rifiuta():
    # 25% di equity 1000 = 250; nozionale 300 (0.10 x 3000) e' oltre.
    d = gate_pre_trade(equity=1000.0, simbolo="DOGE/USDC", lato="buy", prezzo=0.10,
                       quantita=3000.0, prezzo_stop=0.095)
    assert not d.ok


def test_sell_stop_sopra_ammette():
    d = gate_pre_trade(equity=1000.0, simbolo="DOGE/USD:USD", lato="sell", prezzo=0.10,
                       quantita=50.0, prezzo_stop=0.105, leva=1.0)
    assert d.ok
