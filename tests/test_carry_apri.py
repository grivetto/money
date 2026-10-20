"""test_carry_apri.py — regressione dei fix P1 dell'audit 19/10 su scripts/carry_apri.py.

P29 (REQ-MERL-20261019-013). Test OFFLINE: MockApriEx (zero rete, zero chiavi) +
monkeypatch di client/KILL/DIR_STATO/gate_carry/equity_progetto. Ogni test riproduce
un difetto dell'audit (file:riga) e FALLISCE sul codice pre-fix.

Difetti coperti (fonte `prove/audit_capitale_20261019/AUDIT.md`, ALTA confermati):
1. carry_apri.py:62-66 — `funding_atteso` con `abs()`: il segno va conservato.
2. carry_apri.py:204-214 — fill parziale gamba spot: il riempito va LIQUIDATO.
3. carry_apri.py:216-229 — invio perp fallito: unwind automatico dello spot.
4. carry_apri.py:154-163 — preflight senza controllo del saldo spot della moneta.

Caricamento via importlib con cleanup di sys.modules (stesso pattern di
test_carry_config.py): la suite ha un test (test_dati) che esige `ccxt` FUORI da
sys.modules; qui ccxt e' stubato durante l'import e sys.modules torna
ESATTAMENTE allo stato precedente.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    # serve a carry_apri: `from scripts.carry_multi import ...` (namespace package)
    sys.path.insert(0, str(REPO))


def _carica_carry_apri():
    """Carica scripts/carry_apri.py via importlib, con ccxt stubato e cleanup."""
    percorso = REPO / "scripts" / "carry_apri.py"
    spec = importlib.util.spec_from_file_location("carry_apri_under_test", percorso)
    assert spec is not None and spec.loader is not None, f"modulo non trovato: {percorso}"
    precedenti = set(sys.modules)
    if "ccxt" not in sys.modules:
        sys.modules["ccxt"] = types.ModuleType("ccxt")
    try:
        modulo = importlib.util.module_from_spec(spec)
        # registrare PRIMA di exec_module (vedi test_carry_config.py)
        sys.modules[spec.name] = modulo
        spec.loader.exec_module(modulo)
    finally:
        for nome in set(sys.modules) - precedenti:
            del sys.modules[nome]
    return modulo


class MockApriEx:
    """Exchange finto per carry_apri: zero rete, comportamento pilotabile.

    - `spot_esito`/`spot_filled`: stato dell'ordine spot al primo fetch_order
      (per riprodurre il fill parziale dell'audit 204-214).
    - `perp_invio_fallisce`: create_order sul `perp_symbol` solleva (audit 216-229).
    - `saldo_spot`: saldo spot della moneta visto da fetch_balance (audit 154-163).
    - Gli ordini sell successivi (unwind) riempiono per intero con esito
      `unwind_esito` (default closed).
    """

    def __init__(self, *, nome="DOT", px=5.0, saldo_spot=0.0, spot_esito="closed",
                 spot_filled=None, perp_symbol=None, perp_invio_fallisce=False,
                 unwind_esito="closed"):
        self.nome = nome
        self.px = px
        self.saldo_spot = saldo_spot
        self.spot_esito = spot_esito
        self.spot_filled = spot_filled
        self.perp_symbol = perp_symbol
        self.perp_invio_fallisce = perp_invio_fallisce
        self.unwind_esito = unwind_esito
        self.ordini = []          # (symbol, side, qty, price, params) in ordine di arrivo
        self.cancelati = []
        self._n = 0
        self._stato = {}          # oid -> dict stato per fetch_order

    def _registra(self, symbol, side, qty, price, params):
        self._n += 1
        oid = f"mock-{self._n}"
        self.ordini.append((symbol, side, qty, price, params))
        if side == "sell":
            self._stato[oid] = {"status": self.unwind_esito, "filled": qty}
        else:
            self._stato[oid] = {
                "status": self.spot_esito,
                "filled": qty if self.spot_filled is None else self.spot_filled,
            }
        return {"id": oid}

    # -- letture --------------------------------------------------------------
    def fetch_open_orders(self):
        return []

    def fetch_positions(self, syms=None):
        return []

    def fetch_ticker(self, sym):
        return {"last": self.px, "bid": self.px * 0.998, "ask": self.px * 1.002}

    def fetch_balance(self):
        return {"total": {self.nome: self.saldo_spot}}

    # -- ordini ---------------------------------------------------------------
    def create_order(self, symbol, tipo, side, qty, price, params):
        if self.perp_invio_fallisce and symbol == self.perp_symbol:
            raise RuntimeError("mock: invio perp fallito")
        return self._registra(symbol, side, qty, price, params)

    def fetch_order(self, oid, sym):
        return self._stato.get(oid, {"status": "closed", "filled": 0.0})

    def cancel_order(self, oid, sym=None):
        self.cancelati.append(oid)
        return None

    # -- funding --------------------------------------------------------------
    def publicGetPublicFundingRate(self, params):
        return {"data": [{"fundingRate": "0.0001"}]}

    def publicGetPublicFundingRateHistory(self, params):
        return {"data": [{"fundingRate": "0.0001"} for _ in range(12)]}


class MockFundingEx:
    """Mock dei soli endpoint funding (per funding_atteso, audit 62-66)."""

    def __init__(self, storia):
        self._storia = storia

    def publicGetPublicFundingRate(self, params):
        return {"data": [{"fundingRate": "0.0001"}]}

    def publicGetPublicFundingRateHistory(self, params):
        return {"data": [{"fundingRate": v} for v in self._storia]}


def _fake_gate(**kw):
    """DecisioneCarry sintetica ok=True: il test guarda il percorso, non il gate."""
    return types.SimpleNamespace(ok=True, motivi=("ammissibile",),
                                 distanza_liq=0.5, periodi_payback=10.0)


def _main_con(ca, monkeypatch, cartella, ex, argv):
    """Ambiente minimo per main(): client mock, KILL assente, stato in .pytmp."""
    monkeypatch.setattr(ca, "client", lambda: ex)
    monkeypatch.setattr(ca, "KILL", cartella / "MONEY_KILL_SWITCH")  # non esiste
    monkeypatch.setattr(ca, "DIR_STATO", cartella / "carry_multi")
    monkeypatch.setattr(ca, "equity_progetto", lambda: 100.0)
    monkeypatch.setattr(ca, "gate_carry", _fake_gate)
    monkeypatch.setattr(sys, "argv", argv)
    return ca.main()


def _eventi(ca, cartella):
    f = cartella / "carry_multi" / "eventi.jsonl"
    if not f.exists():
        return []
    return [json.loads(l) for l in f.read_text().splitlines() if l.strip()]


# ---------------------------------------------------------------------------
# Fix 1 — AUDIT carry_apri.py:62-66: funding_atteso NON deve fare abs()
# ---------------------------------------------------------------------------

def test_funding_negativo_mantiene_segno_e_gate_rifiuta():
    """Il segno del funding va conservato: il gate deve vedere il valore negativo."""
    ca = _carica_carry_apri()
    ex = MockFundingEx(["-0.000200", "-0.000100", "0.000100"])
    f = ca.funding_atteso(ex, "DOT-USD_UM_XPERP-310808")
    assert f < 0, f"funding_atteso deve conservare il segno, ricevuto {f}"
    dec = ca.gate_carry(nozionale=90.0, funding_atteso=f, costo_ciclo=0.0034,
                        delta_relativo=0.0, leva=1.0)
    assert not dec.ok
    assert any("funding" in m for m in dec.motivi)


def test_funding_positivo_min_con_segno():
    """Regressione: con valori positivi resta il minimo (invariante del fix)."""
    ca = _carica_carry_apri()
    ex = MockFundingEx(["0.000300", "0.000200", "0.000100", "0.000400"])
    assert ca.funding_atteso(ex, "X") == pytest.approx(0.0001, abs=1e-12)


# ---------------------------------------------------------------------------
# Fix 2 — AUDIT carry_apri.py:204-214: fill parziale spot -> LIQUIDARE il riempito
# ---------------------------------------------------------------------------

def test_fill_parziale_spot_unwind_e_evento_con_qty(monkeypatch, cartella, capsys):
    ca = _carica_carry_apri()
    c = ca.COPPIE["DOT"]
    ex = MockApriEx(nome=c.nome, spot_esito="canceled", spot_filled=3.0)
    rc = _main_con(ca, monkeypatch, cartella, ex,
                   ["carry_apri.py", "--coppia", "DOT", "--execute"])
    assert rc == 1
    sell = [(s, q) for (s, side, q, _p, _x) in ex.ordini if side == "sell"]
    assert sell, "nessun unwind inviato: il riempito resta scoperto"
    assert sell[0][0] == c.sym_spot
    assert sell[0][1] == pytest.approx(3.0)
    ev = [e for e in _eventi(ca, cartella) if e.get("evento") == "apertura_annullata"]
    assert ev, "evento apertura_annullata assente"
    assert ev[-1].get("filled") == pytest.approx(3.0)
    assert ev[-1].get("unwind_esito") == "closed"
    assert ev[-1].get("unwind_qty") == pytest.approx(3.0)
    # il messaggio "nessuna gamba scoperta" e' VIETATO quando filled > 0
    assert "nessuna gamba scoperta" not in capsys.readouterr().out


def test_fill_parziale_zero_unwind_non_chiamato_e_messaggio_ammesso(monkeypatch,
                                                                    cartella, capsys):
    """Regressione: con filled == 0 niente unwind e messaggio invariato."""
    ca = _carica_carry_apri()
    c = ca.COPPIE["DOT"]
    ex = MockApriEx(nome=c.nome, spot_esito="canceled", spot_filled=0.0)
    rc = _main_con(ca, monkeypatch, cartella, ex,
                   ["carry_apri.py", "--coppia", "DOT", "--execute"])
    assert rc == 1
    assert [o for o in ex.ordini if o[1] == "sell"] == []
    assert "nessuna gamba scoperta" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Fix 3 — AUDIT carry_apri.py:216-229: invio perp fallito -> unwind automatico
# ---------------------------------------------------------------------------

def test_invio_perp_fallito_unwind_automatico_con_esito(monkeypatch, cartella, capsys):
    ca = _carica_carry_apri()
    c = ca.COPPIE["DOT"]
    ex = MockApriEx(nome=c.nome, perp_symbol=c.sym_perp, perp_invio_fallisce=True)
    rc = _main_con(ca, monkeypatch, cartella, ex,
                   ["carry_apri.py", "--coppia", "DOT", "--execute"])
    assert rc == 1
    sell = [(s, q) for (s, side, q, _p, _x) in ex.ordini if side == "sell"]
    assert len(sell) == 1, "atteso il SOLO unwind (la perp non e' partita)"
    assert sell[0][0] == c.sym_spot
    qty_attesa = c.qty_spot(ex.px)
    assert sell[0][1] == pytest.approx(qty_attesa)
    ev = [e for e in _eventi(ca, cartella) if e.get("evento") == "gamba_scoperta"]
    assert ev, "evento gamba_scoperta assente"
    assert ev[-1].get("qty_spot") == pytest.approx(qty_attesa)
    assert ev[-1].get("unwind_esito") == "closed"
    out = capsys.readouterr().out
    assert "unwind" in out.lower()


# ---------------------------------------------------------------------------
# Fix 4 — AUDIT carry_apri.py:154-163: preflight senza controllo saldo spot
# ---------------------------------------------------------------------------

def test_preflight_saldo_spot_residuo_rifiuta(monkeypatch, cartella, capsys):
    ca = _carica_carry_apri()
    c = ca.COPPIE["DOT"]
    ex = MockApriEx(nome=c.nome, saldo_spot=2.5)
    rc = _main_con(ca, monkeypatch, cartella, ex,
                   ["carry_apri.py", "--coppia", "DOT", "--execute"])
    assert rc == 1
    assert ex.ordini == [], "nessun ordine deve partire con saldo spot residuo"
    out = capsys.readouterr().out
    assert "saldo spot" in out
    assert "non si apre una seconda gamba" in out
