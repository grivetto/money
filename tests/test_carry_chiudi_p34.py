"""test_carry_chiudi_p34.py — P34-F2 in scripts/carry_chiudi.py: il verdetto
della chiusura economica nel piano e il rifiuto --solo-economica sotto
soglia (zero ordini).

Caricamento via importlib con ccxt stubato (stesso pattern di
test_carry_chiudi_p31.py).
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

RADICE = Path(__file__).resolve().parents[1]
for _p in (RADICE, RADICE / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def _carica():
    percorso = RADICE / "scripts" / "carry_chiudi.py"
    spec = importlib.util.spec_from_file_location("carry_chiudi_p34_ut",
                                                  percorso)
    assert spec is not None and spec.loader is not None
    precedenti = set(sys.modules)
    if "ccxt" not in sys.modules:
        sys.modules["ccxt"] = types.ModuleType("ccxt")
    try:
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
    finally:
        for n in set(sys.modules) - precedenti:
            del sys.modules[n]
    return mod


mod = _carica()
C = mod.COPPIE["ADA"]


class MockChiudiP34:
    """Minimo per esegui(): posizione reale short, saldo spot, ticker.
    create_order solleva: i test gate non devono MAI arrivare a inviare."""

    def __init__(self, nome="ADA", ct=39.0, q_spot=389.61, px=0.2065):
        self.nome = nome
        self.ct = ct
        self.q_spot = q_spot
        self.px = px
        self.ordini = []

    def load_markets(self):
        pass

    def fetch_positions(self, syms=None):
        if abs(self.ct) <= 0:
            return []
        return [{"contracts": abs(self.ct), "side": "short",
                 "info": {"pos": str(-abs(self.ct))}}]

    def fetch_balance(self):
        return {"free": {self.nome: self.q_spot},
                "total": {self.nome: self.q_spot}}

    def fetch_ticker(self, sym):
        return {"last": self.px, "bid": self.px * 0.998, "ask": self.px * 1.002}

    def market(self, sym):
        return {"limits": {"amount": {"min": 1.0}}}

    def fetch_open_orders(self):
        return []

    def create_order(self, *a, **k):
        raise AssertionError("nessun ordine atteso nei test del gate")

    def fetch_order(self, *a, **k):
        return {"status": "closed", "filled": 0.0}

    def cancel_order(self, *a, **k):
        return None

    def price_to_precision(self, sym, px):
        return px


def _esegui(ex, **cfg_kw):
    cfg = mod.Config(coppia="ADA", **cfg_kw)
    return mod.esegui(ex, cfg, sleep_fn=lambda s: None)


def test_dry_run_stampa_verdetto_economico_rifiuto(capsys):
    ex = MockChiudiP34()
    rc = _esegui(ex, netto_stimato=0.093)
    assert rc == 0
    out = capsys.readouterr().out
    assert "chiusura economica: ok=False" in out
    assert "0.0930" in out


def test_dry_run_verdetto_ok_sopra_soglia(capsys):
    ex = MockChiudiP34()
    rc = _esegui(ex, netto_stimato=0.50, solo_economica=True)
    assert rc == 0
    assert "chiusura economica: ok=True" in capsys.readouterr().out


def test_solo_economica_sotto_soglia_rifiuta_zero_ordini(capsys):
    ex = MockChiudiP34()
    rc = _esegui(ex, netto_stimato=0.093, solo_economica=True, execute=True)
    assert rc == 2
    assert ex.ordini == []
    assert "RIFIUTO" in capsys.readouterr().out


def test_solo_economica_senza_netto_rifiuta_fail_closed(capsys):
    ex = MockChiudiP34()
    rc = _esegui(ex, solo_economica=True, execute=True)
    assert rc == 2
    assert ex.ordini == []
    assert "fail-closed" in capsys.readouterr().out


def test_senza_netto_niente_verdetto_flow_invariato(capsys):
    """Senza --netto-stimato il flusso di riduzione di rischio resta intatto."""
    ex = MockChiudiP34()
    rc = _esegui(ex)
    assert rc == 0
    assert "chiusura economica" not in capsys.readouterr().out
