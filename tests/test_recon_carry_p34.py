"""test_recon_carry_p34.py — P34-F3: la riconciliazione legge i saldi REALI
(fetch_balance + fetch_positions), mai carry_stato.json.

Fixture: lo scaling DOT del 23/10 (registro 26/10): lo stato era fermo a
~78 ct, saldo reale 252,747 DOT, perp -253 ct — il delta dal saldo reale
non e' piu' sottostimato di 3,2x.
"""
from __future__ import annotations

import pytest

from money.recon_carry import (
    ct_firmato,
    delta_qty,
    delta_spot_mtm_usdc,
    lettura_saldi_reali,
    netto_usdc,
)


class MockReconEx:
    """Exchange finto nella FORMA REALE di ccxt (P31): contracts >= 0 + side."""

    def __init__(self, *, nome="DOT", total_spot=0.0, contracts=0.0,
                 side="short", upl=0.0, liq_px=None, px_spot=1.0,
                 px_perp=1.0):
        self.nome = nome
        self.total_spot = total_spot
        self.contracts = contracts
        self.side = side
        self.upl = upl
        self.liq_px = liq_px
        self.px_spot = px_spot
        self.px_perp = px_perp

    def fetch_balance(self):
        return {"total": {self.nome: self.total_spot}}

    def fetch_positions(self, syms=None):
        if abs(self.contracts) <= 0:
            return []
        info = {}
        if self.liq_px is not None:
            info["liqPx"] = str(self.liq_px)
        return [{"contracts": abs(self.contracts), "side": self.side,
                 "unrealizedPnl": self.upl, "info": info}]

    def fetch_ticker(self, sym):
        px = self.px_spot if "USDC" in sym else self.px_perp
        return {"last": px, "bid": px * 0.999, "ask": px * 1.001}


def test_ct_firmato_forma_reale_e_legacy():
    assert ct_firmato({"contracts": 253, "side": "short"}) == -253
    assert ct_firmato({"contracts": 39, "side": "long"}) == 39
    assert ct_firmato({"contracts": -78}) == -78      # forma legacy firmata
    assert ct_firmato({}) == 0.0


def test_lettura_saldi_reali_dot_scaling_23_10():
    ex = MockReconEx(total_spot=252.747, contracts=253, side="short",
                     upl=-1.25, liq_px=2.1, px_spot=1.141, px_perp=1.1405)
    s = lettura_saldi_reali(ex, nome="DOT", sym_perp="DOT/USD:USD-310808",
                            sym_spot="DOT/USDC", ct_val=1.0)
    assert s.qty_spot == pytest.approx(252.747)
    assert s.ct_perp == -253.0
    assert s.upl_usdc == pytest.approx(-1.25)
    assert s.liq_px == pytest.approx(2.1)
    assert s.px_spot == pytest.approx(1.141)
    assert s.px_perp == pytest.approx(1.1405)


def test_delta_dal_saldo_reale_non_dallo_stato():
    """Col numero stantio dello stato (78) il delta era -0,078: sottostima
    di 3,2x. Col saldo reale il delta e' quello vero."""
    assert delta_qty(252.747, -253, 1.0) == pytest.approx(-0.253)
    assert delta_qty(77.922, -78, 1.0) == pytest.approx(-0.078)


def test_delta_spot_mtm_e_netto():
    d = delta_spot_mtm_usdc(qty_spot=252.747, vwap_in=1.15, px_now=1.141)
    assert d == pytest.approx(252.747 * (1.141 - 1.15))
    n = netto_usdc(funding_usdc=0.9, fee_signed_usdc=-0.4, upl_usdc=-1.25,
                   delta_spot_usdc=d)
    assert n == pytest.approx(0.9 - 0.4 - 1.25 + d)


def test_lettura_pair_chiusa_zero():
    """ADA chiusa il 26/10: saldo 0, posizione 0, uPL 0, nessuna liq."""
    ex = MockReconEx(total_spot=0.0, contracts=0.0)
    s = lettura_saldi_reali(ex, nome="ADA", sym_perp="ADA/USD:USD-310404",
                            sym_spot="ADA/USDC", ct_val=10.0)
    assert s.qty_spot == 0.0
    assert s.ct_perp == 0.0
    assert s.upl_usdc == 0.0
    assert s.liq_px is None
