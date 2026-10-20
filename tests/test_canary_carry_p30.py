"""test_canary_carry_p30.py — regressione dei fix P2 dell'audit 19/10 su scripts/canary_carry.py.

P30 (REQ-MERL-20261020-014). Test OFFLINE: MockCanaryEx (zero rete, zero chiavi) +
monkeypatch di client/KILL/STATE/EVENTS/cancello/preflight/attesa_fill. Ogni test
riproduce un difetto dell'audit (file:riga) e FALLISCE sul codice pre-fix.

Difetti coperti (fonte `prove/audit_capitale_20261019/AUDIT.md`, ALTA confermati in
REVIEW_AUDIT.md, priorita' P2 = canary C1):
1. canary_carry.py:388-403 — reprice spot: fetch_order fallito -> filled 0 -> rinvio
   della taglia PIENA (over-buy) + race lettura/cancel.
2. canary_carry.py:429-439 — reprice perp: residuo non calcolato, rinvio dell'intera
   `ct` (over-short).
3. canary_carry.py:463-472 — unwind spot: esito di attesa_fill scartato, dichiara
   «flat» senza verifica.
4. canary_carry.py:524-557 — close non atomica: spot venduto qualunque sia l'esito
   della chiusura perp; stato marcato closed con residui.
5. canary_carry.py:187-189 + 90-95 — salva_state senza lock, open concorrenti non
   esclusi (doppia apertura).

Caricamento via importlib con cleanup di sys.modules (stesso pattern di
test_carry_apri.py): la suite ha un test (test_dati) che esige `ccxt` FUORI da
sys.modules; qui ccxt e' stubato durante l'import e sys.modules torna ESATTAMENTE
allo stato precedente.
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _carica_canary():
    """Carica scripts/canary_carry.py via importlib, con ccxt stubato e cleanup."""
    percorso = REPO / "scripts" / "canary_carry.py"
    spec = importlib.util.spec_from_file_location("canary_carry_under_test", percorso)
    assert spec is not None and spec.loader is not None, f"modulo non trovato: {percorso}"
    precedenti = set(sys.modules)
    if "ccxt" not in sys.modules:
        sys.modules["ccxt"] = types.ModuleType("ccxt")
    try:
        modulo = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = modulo
        spec.loader.exec_module(modulo)
    finally:
        for nome in set(sys.modules) - precedenti:
            del sys.modules[nome]
    return modulo


# ---------------------------------------------------------------------------
# Mock dell'exchange per il canary (zero rete, pilotabile)
# ---------------------------------------------------------------------------

class MockCanaryEx:
    """Exchange finto per canary_carry: zero rete, comportamento pilotabile.

    - `fill_spot_post_cancel` / `fill_perp_post_cancel`: filled riportato da
      fetch_order SOLO dopo che l'ordine e' stato cancellato; prima della cancel
      il filled e' 0 (riproduce la race lettura/cancel dell'audit 388-403).
    - `fetch_ok=False`: fetch_order solleva sempre (fill illeggibile).
    - `posizioni`: lista consumata da privateGetAccountPositions (una lettura
      = un elemento; None = nessuna posizione).
    - `spot_free`: saldo DOGE da fetch_balance (mutabile durante il test).
    - `balance_fallisce=True`: fetch_balance solleva (saldo non leggibile).
    """

    def __init__(self, ca, *, fill_spot_post_cancel=0.0, fill_perp_post_cancel=0.0,
                 fetch_ok=True, posizioni=None, spot_free=0.0, balance_fallisce=False,
                 px_spot=0.095, px_perp=0.095):
        self.ca = ca
        self.fill_spot_post_cancel = fill_spot_post_cancel
        self.fill_perp_post_cancel = fill_perp_post_cancel
        self.fetch_ok = fetch_ok
        self.posizioni = list(posizioni) if posizioni else []
        self.spot_free = spot_free
        self.balance_fallisce = balance_fallisce
        self.px_spot = px_spot
        self.px_perp = px_perp
        self.ordini = []      # (symbol, side, qty, price, params) in ordine di arrivo
        self.cancelati = []   # (oid, sym)
        self._n = 0

    # -- mercato -------------------------------------------------------------
    def load_markets(self):
        pass

    def fetch_ticker(self, sym):
        px = self.px_spot if sym == self.ca.SYM_SPOT else self.px_perp
        return {"last": px, "bid": px * 0.998, "ask": px * 1.002}

    def price_to_precision(self, sym, px):
        return float(px)

    # -- ordini --------------------------------------------------------------
    def create_order(self, symbol, tipo, side, qty, price, params):
        self._n += 1
        oid = f"mock-{self._n}"
        self.ordini.append((symbol, side, qty, price, params))
        return {"id": oid}

    def fetch_order(self, oid, sym):
        if not self.fetch_ok:
            raise RuntimeError("mock: fetch_order fallisce")
        if oid in {c[0] for c in self.cancelati}:
            filled = (self.fill_perp_post_cancel if sym != self.ca.SYM_SPOT
                      else self.fill_spot_post_cancel)
        else:
            filled = 0.0
        return {"id": oid, "status": "closed", "filled": filled}

    def cancel_order(self, oid, sym=None):
        self.cancelati.append((oid, sym))
        return {"id": oid, "status": "canceled"}

    # -- saldi e posizioni ---------------------------------------------------
    def fetch_balance(self):
        if self.balance_fallisce:
            raise RuntimeError("mock: fetch_balance fallisce")
        return {"DOGE": {"free": self.spot_free}}

    def privateGetAccountPositions(self, params):
        pos = self.posizioni.pop(0) if self.posizioni else None
        return {"data": [pos] if pos else []}

    def privatePostAccountSetLeverage(self, params):
        return {"code": "0"}

    def pos_perp(self, ct=11.0):
        """Dict posizione perp (instId == ca.INST) come lo ritorna OKX."""
        return {"instId": self.ca.INST, "pos": str(ct), "avgPx": "0.095",
                "upl": "0", "fundingFee": "0", "markPx": "0.095", "liqPx": "0"}


def _pos_perp(ca, ct=11.0):
    return MockCanaryEx(ca).pos_perp(ct)


def _fake_cancello(registro):
    """Gate pre-trade finto: ok=True, registra (symbol, side, qty, prezzo, leva)."""

    def fn(ex, symbol, side, quantita, prezzo, *, leva=1.0):
        registro.append({"symbol": symbol, "side": side, "qty": quantita,
                         "prezzo": prezzo, "leva": leva})
        return types.SimpleNamespace(ok=True, motivi=())

    return fn


def _attese(seq):
    """attesa_fill finta che consuma una sequenza di (esito, azione).

    Sequenza esaurita = ordini successivi si riempiono (default chiuso):
    il test che vuole il rosso per il DIFETTO non deve morire per StopIteration.
    """

    it = iter(seq)

    def fn(ex, oid, sym, secondi=60, passo=1.5):
        try:
            esito, azione = next(it)
        except StopIteration:
            esito, azione = "closed", None
        if azione:
            azione()
        return ({"id": oid, "status": "closed" if esito == "closed" else "canceled",
                 "filled": 0.0}, esito)

    return fn


def _main_con(ca, monkeypatch, cartella, ex, argv, *, attese=None):
    """Ambiente minimo per main(): client mock, KILL assente, stato/eventi in cartella."""
    monkeypatch.setattr(ca, "client", lambda: ex)
    monkeypatch.setattr(ca, "KILL", cartella / "MONEY_KILL_SWITCH")  # non esiste
    monkeypatch.setattr(ca, "STATE", cartella / "canary_state.json")
    monkeypatch.setattr(ca, "EVENTS", cartella / "canary_events.jsonl")
    monkeypatch.setattr(ca, "preflight", lambda ex: True)
    registro = []
    monkeypatch.setattr(ca, "cancello", _fake_cancello(registro))
    if attese is not None:
        monkeypatch.setattr(ca, "attesa_fill", _attese(attese))
    monkeypatch.setattr(sys, "argv", argv)
    rc = ca.main()
    return rc, registro


def _stato(ca, cartella):
    f = cartella / "canary_state.json"
    if not f.exists():
        return None
    return json.loads(f.read_text())


def _eventi(ca, cartella):
    f = cartella / "canary_events.jsonl"
    if not f.exists():
        return []
    return [json.loads(l) for l in f.read_text().splitlines() if l.strip()]


# ---------------------------------------------------------------------------
# Fix 1 — AUDIT canary_carry.py:388-403: reprice spot, mai rilanciare la taglia
# piena; il fill va letto DOPO la cancel.
# ---------------------------------------------------------------------------

def test_reprice_spot_fill_illeggibile_ferma_senza_rinvio(monkeypatch, cartella):
    """fetch_order fallisce -> STOP con riconciliazione manuale, NESSUN rinvio."""
    ca = _carica_canary()
    ex = MockCanaryEx(ca, fetch_ok=False)
    with pytest.raises(SystemExit) as ei:
        _main_con(ca, monkeypatch, cartella, ex,
                  ["canary_carry.py", "open", "--execute"],
                  attese=[("reprice", None)])
    assert "riconciliare a mano" in str(ei.value)
    buys = [o for o in ex.ordini if o[0] == ca.SYM_SPOT and o[1] == "buy"]
    assert len(buys) == 1, "il fill illeggibile NON autorizza il rinvio della taglia piena"


def test_reprice_spot_residuo_dal_fill_post_cancel(monkeypatch, cartella):
    """Fill 40 su 110 letto DOPO la cancel -> si rinvia SOLO il residuo (70)."""
    ca = _carica_canary()
    ex = MockCanaryEx(ca, fill_spot_post_cancel=40.0, spot_free=110.0,
                      posizioni=[_pos_perp(ca, 11)])
    rc, registro = _main_con(ca, monkeypatch, cartella, ex,
                             ["canary_carry.py", "open", "--execute"],
                             attese=[("reprice", None), ("closed", None), ("closed", None)])
    assert rc is None
    buys = [o[2] for o in ex.ordini if o[0] == ca.SYM_SPOT and o[1] == "buy"]
    assert buys == pytest.approx([110.0, 70.0]), f"attesi buy 110+70, ricevuti {buys}"
    cancello_reprice = [c for c in registro if c["qty"] == 70.0]
    assert cancello_reprice, "il cancello del rinvio deve vedere il residuo (70), non la taglia"


# ---------------------------------------------------------------------------
# Fix 2 — AUDIT canary_carry.py:429-439: reprice perp, residuo = ct - filled.
# ---------------------------------------------------------------------------

def test_reprice_perp_residuo_dal_fill_post_cancel(monkeypatch, cartella):
    """Fill 4 su 11 ct letto DOPO la cancel -> si rinvia SOLO il residuo (7 ct)."""
    ca = _carica_canary()
    ex = MockCanaryEx(ca, fill_perp_post_cancel=4.0, spot_free=110.0,
                      posizioni=[_pos_perp(ca, 11)])
    rc, registro = _main_con(ca, monkeypatch, cartella, ex,
                             ["canary_carry.py", "open", "--execute"],
                             attese=[("closed", None), ("reprice", None), ("closed", None)])
    assert rc is None
    sells = [o[2] for o in ex.ordini if o[0] == ca.SYM_PER and o[1] == "sell"]
    assert sells == pytest.approx([11.0, 7.0]), f"attesi sell 11+7 ct, ricevuti {sells}"
    cancello_reprice = [c for c in registro if c["symbol"] == ca.SYM_PER
                        and c["qty"] == 7.0 * ca.CT_VAL]
    assert cancello_reprice, "il cancello del rinvio perp deve vedere 7 ct (70 nozionale)"


def test_reprice_perp_fill_illeggibile_ferma_senza_rinvio(monkeypatch, cartella):
    """fetch_order fallisce sul perp -> STOP manuale, nessun rinvio dell'intera ct."""
    ca = _carica_canary()
    ex = MockCanaryEx(ca, fetch_ok=False, spot_free=110.0)
    with pytest.raises(SystemExit) as ei:
        _main_con(ca, monkeypatch, cartella, ex,
                  ["canary_carry.py", "open", "--execute"],
                  attese=[("closed", None), ("reprice", None)])
    assert "riconciliare a mano" in str(ei.value)
    sells = [o for o in ex.ordini if o[0] == ca.SYM_PER and o[1] == "sell"]
    assert len(sells) == 1, "il fill illeggibile del perp NON autorizza il rinvio"


# ---------------------------------------------------------------------------
# Fix 3 — AUDIT canary_carry.py:463-472: unwind spot, mai dichiarare flat
# senza esito verificato.
# ---------------------------------------------------------------------------

def test_verdetto_unwind():
    """Funzione di verdetto: flat SOLO con esito closed e residuo ~0."""
    ca = _carica_canary()
    assert ca.verdetto_unwind("closed", 0.0) == "flat"
    assert ca.verdetto_unwind("partial", 12.3) == "non_flat|residuo 12.3000|esito partial"
    assert ca.verdetto_unwind("closed", None) == "non_flat|esito closed|saldo non leggibile"
    assert ca.verdetto_unwind("reprice", 0.0).startswith("non_flat")


def test_unwind_non_flat_con_esito_scartato_prima_del_fix(monkeypatch, cartella):
    """Esito partial + residuo 30 -> uscita NON FLAT con esito nell'evento."""
    ca = _carica_canary()
    ex = MockCanaryEx(ca, spot_free=110.0, posizioni=[])
    with pytest.raises(SystemExit) as ei:
        _main_con(ca, monkeypatch, cartella, ex,
                  ["canary_carry.py", "open", "--execute"],
                  attese=[("closed", None), ("closed", None),
                          ("partial", lambda: setattr(ex, "spot_free", 30.0))])
    assert "NON FLAT" in str(ei.value)
    ev = [e for e in _eventi(ca, cartella) if e.get("event") == "unwind_spot"]
    assert ev, "evento unwind_spot assente"
    assert ev[-1].get("esito") == "partial"
    assert ev[-1].get("doge_residuo") == pytest.approx(30.0)
    assert str(ev[-1].get("verdetto", "")).startswith("non_flat")


def test_unwind_flat_verificato(monkeypatch, cartella):
    """Esito closed + residuo 0 -> flat VERIFICATO (messaggio e verdetto)."""
    ca = _carica_canary()
    ex = MockCanaryEx(ca, spot_free=110.0, posizioni=[])
    with pytest.raises(SystemExit) as ei:
        _main_con(ca, monkeypatch, cartella, ex,
                  ["canary_carry.py", "open", "--execute"],
                  attese=[("closed", None), ("closed", None),
                          ("closed", lambda: setattr(ex, "spot_free", 0.0))])
    assert "flat (verificato)" in str(ei.value)
    ev = [e for e in _eventi(ca, cartella) if e.get("event") == "unwind_spot"]
    assert ev and ev[-1].get("verdetto") == "flat"


# ---------------------------------------------------------------------------
# Fix 4 — AUDIT canary_carry.py:524-557: close non atomica.
# ---------------------------------------------------------------------------

def test_close_perp_parziale_non_vende_spot_e_non_chiude_stato(monkeypatch, cartella):
    """Close perp parziale -> lo spot NON si vende e lo stato NON e' closed."""
    ca = _carica_canary()
    ex = MockCanaryEx(ca, spot_free=110.0, posizioni=[_pos_perp(ca, 11)] * 3)
    with pytest.raises(SystemExit) as ei:
        _main_con(ca, monkeypatch, cartella, ex,
                  ["canary_carry.py", "close", "--execute"],
                  attese=[("partial", None)])
    assert "close NON COMPLETA" in str(ei.value)
    sells = [o for o in ex.ordini if o[0] == ca.SYM_SPOT and o[1] == "sell"]
    assert sells == [], "con la perp ancora aperta lo spot NON va venduto (short nudo)"
    st = _stato(ca, cartella)
    assert st is not None and st.get("status") != "closed", \
        "lo stato NON puo' essere closed con posizione perp residua"
    ev = _eventi(ca, cartella)
    assert any(e.get("event") == "close_spot_sospeso" for e in ev)
    assert any(e.get("event") == "close_incompleta" for e in ev)


def test_close_completa_vende_spot_e_chiude_stato(monkeypatch, cartella):
    """Close perp closed + spot closed -> stato closed e close_complete."""
    ca = _carica_canary()
    ex = MockCanaryEx(ca, spot_free=110.0, posizioni=[_pos_perp(ca, 11), None, None])
    _main_con(ca, monkeypatch, cartella, ex,
              ["canary_carry.py", "close", "--execute"],
              attese=[("closed", None),
                      ("closed", lambda: setattr(ex, "spot_free", 0.0))])
    st = _stato(ca, cartella)
    assert st is not None and st.get("status") == "closed"
    sells = [o for o in ex.ordini if o[0] == ca.SYM_SPOT and o[1] == "sell"]
    assert sells, "close completa: lo spot va venduto"
    ev = [e for e in _eventi(ca, cartella) if e.get("event") == "close_complete"]
    assert ev and ev[-1].get("pos_residua") is False


# ---------------------------------------------------------------------------
# Fix 5 — AUDIT canary_carry.py:187-189 + 90-95: lock esclusivo sullo stato.
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _spy_lock(ca, chiamate):
    chiamate.append(True)
    yield


def test_open_passa_dal_lock_esclusivo(monkeypatch, cartella):
    """open --execute usa il lock attorno a carica/intento/invio/salvataggio."""
    ca = _carica_canary()
    ex = MockCanaryEx(ca, spot_free=110.0, posizioni=[_pos_perp(ca, 11)])
    chiamate = []
    monkeypatch.setattr(ca.modulo_stato, "lock_esclusivo",
                        lambda percorso: _spy_lock(ca, chiamate))
    _main_con(ca, monkeypatch, cartella, ex,
              ["canary_carry.py", "open", "--execute"],
              attese=[("closed", None), ("closed", None)])
    assert chiamate, "open deve passare dal lock_esclusivo"
    st = _stato(ca, cartella)
    assert st is not None and st.get("status") == "open"


def test_lock_occupato_rifiuta_open_senza_ordini(monkeypatch, cartella):
    """Lock occupato -> open rifiutato con messaggio esplicito, zero ordini."""
    ca = _carica_canary()
    ex = MockCanaryEx(ca, spot_free=110.0)

    @contextlib.contextmanager
    def lock_busy(percorso):
        raise ca.modulo_stato.LockOccupato("occupato da un altro processo")
        yield  # pragma: no cover

    monkeypatch.setattr(ca.modulo_stato, "lock_esclusivo", lock_busy)
    with pytest.raises(SystemExit) as ei:
        _main_con(ca, monkeypatch, cartella, ex,
                  ["canary_carry.py", "open", "--execute"],
                  attese=[("closed", None), ("closed", None)])
    assert "LOCK OCCUPATO" in str(ei.value)
    assert ex.ordini == [], "con il lock occupato nessun ordine deve partire"


def test_close_e_status_passano_dal_lock(monkeypatch, cartella):
    """close e status usano il lock: una sola via di scrittura dello stato."""
    ca = _carica_canary()

    chiamate_close = []
    pos = _pos_perp(ca, 11)
    ex_c = MockCanaryEx(ca, spot_free=110.0, posizioni=[pos, pos, pos])
    monkeypatch.setattr(ca.modulo_stato, "lock_esclusivo",
                        lambda percorso: _spy_lock(ca, chiamate_close))
    with pytest.raises(SystemExit):
        _main_con(ca, monkeypatch, cartella, ex_c,
                  ["canary_carry.py", "close", "--execute"],
                  attese=[("partial", None)])
    assert chiamate_close, "close deve passare dal lock"

    chiamate_status = []
    ex_s = MockCanaryEx(ca, posizioni=[_pos_perp(ca, 11)], spot_free=0.0)
    monkeypatch.setattr(ca.modulo_stato, "lock_esclusivo",
                        lambda percorso: _spy_lock(ca, chiamate_status))
    rc, _ = _main_con(ca, monkeypatch, cartella, ex_s,
                      ["canary_carry.py", "status", "--quiet"])
    assert rc is None
    assert chiamate_status, "status deve passare dal lock prima di scrivere"


def test_lock_reale_esclusivo(cartella):
    """La primitiva su cui poggia il fix: due lock sullo stesso file si escludono."""
    from money.esecuzione import stato as modulo_stato

    percorso = cartella / "state.json"
    with modulo_stato.lock_esclusivo(str(percorso)):
        with pytest.raises(modulo_stato.LockOccupato):
            with modulo_stato.lock_esclusivo(str(percorso)):
                pass  # pragma: no cover


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
