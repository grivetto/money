"""test_canary_carry_p33.py — P33: lock a PRENOTAZIONE (claim) su scripts/canary_carry.py.

REQ-MERL-20261021-016. Spec: coda_catena/P33_lock_prenotazione_canary.md.

Test OFFLINE (zero rete, zero chiavi): MockCanaryEx33 + monkeypatch di
client/KILL/STATE/EVENTS/cancello/preflight/attesa_fill. Il lock e' QUELLO REALE
(modulo_stato.lock_esclusivo su file in tmp), mai uno stub nei test sul flusso:
gli scenari dimostrano che il lock non e' trattenuto oltre le sezioni brevi.

Mappa scenari spec -> test (dettaglio in LEGGIMI.md):
  spec 1 -> test_1_status_durante_open_in_flusso_rc0_e_lock_libero
  spec 2 -> test_2_close_con_opening_fresco_rifiutata_exit2
  spec 3 -> test_3_secondo_close_con_closing_fresco_rifiutato_exit2
  spec 4 -> test_4_doppio_open_concorrente_secondo_rifiutato_dal_claim
  spec 5 -> test_5_open_con_claim_stantio_procede_e_registra_evento
            test_5b_close_con_claim_stantio_procede_e_registra_evento (extra)
  spec 6 -> test_6_open_claim_scritto_a_meta_e_rimosso_alla_fine
  spec 7 -> test_7_close_claim_scritto_a_meta_e_rimosso_alla_fine
  spec 8 -> i 13 test di tests/test_canary_carry_p30.py (eseguiti in suite)
  extra  -> test_9_abort_rilascia_claim
            test_10_stato_esistente_senza_claim_e_libero

Sul codice PRE-fix (P30) questi test FALLISCONO con i difetti in LEGGIMI.md
(output integrale in rosso_pre_fix.txt): lock trattenuto per l'intero flusso,
status -> LOCK OCCUPATO a meta' open, close rifiutata dal lock invece che dal
claim, claim mai scritto, evento claim_stantio mai registrato.
"""
from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import sys
import threading
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _carica_canary():
    """Carica scripts/canary_carry.py via importlib, con ccxt stubato e cleanup.

    Stesso pattern di test_canary_carry_p30.py: la suite ha un test (test_dati) che
    esige `ccxt` FUORI da sys.modules; qui ccxt e' stubato durante l'import e
    sys.modules torna ESATTAMENTE allo stato precedente.
    """
    percorso = REPO / "scripts" / "canary_carry.py"
    spec = importlib.util.spec_from_file_location("canary_carry_under_test_p33", percorso)
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


class MockCanaryEx33:
    """Exchange finto per canary_carry: zero rete, zero chiavi, pilotabile."""

    def __init__(self, ca, *, spot_free=0.0, posizioni=None, px_spot=0.095, px_perp=0.095):
        self.ca = ca
        self.spot_free = spot_free
        self.posizioni = list(posizioni) if posizioni else []
        self.px_spot = px_spot
        self.px_perp = px_perp
        self.ordini = []      # (symbol, tipo, side, qty, price, params) in ordine di arrivo
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
        self.ordini.append((symbol, tipo, side, qty, price, params))
        return {"id": oid}

    def fetch_order(self, oid, sym):
        return {"id": oid, "status": "closed", "filled": 0.0}

    def cancel_order(self, oid, sym=None):
        self.cancelati.append((oid, sym))
        return {"id": oid, "status": "canceled"}

    # -- saldi e posizioni ---------------------------------------------------
    def fetch_balance(self):
        return {"DOGE": {"free": self.spot_free}}

    def privateGetAccountPositions(self, params):
        pos = self.posizioni.pop(0) if self.posizioni else None
        return {"data": [pos] if pos else []}

    def privatePostAccountSetLeverage(self, params):
        return {"code": "0"}


def _pos_perp(ca, ct=11.0):
    return {"instId": ca.INST, "pos": str(ct), "avgPx": "0.095",
            "upl": "0", "fundingFee": "0", "markPx": "0.095", "liqPx": "0"}


def _fake_cancello(registro):
    """Gate pre-trade finto: ok=True, registra (symbol, side, qty, prezzo, leva)."""

    def fn(ex, symbol, side, quantita, prezzo, *, leva=1.0):
        registro.append({"symbol": symbol, "side": side, "qty": quantita,
                         "prezzo": prezzo, "leva": leva})
        return types.SimpleNamespace(ok=True, motivi=())

    return fn


def _attesa_controllata(seq, eventi=None, probe=None):
    """attesa_fill finta pilotata.

    - consuma una sequenza di (esito, azione); sequenza esaurita = closed;
    - `probe`: chiamata a OGNI invocazione (fotografia dello stato a meta' flusso);
    - `eventi` = {"midflow": Event, "via": Event}: alla PRIMA invocazione segnala
      `midflow` e ATTENDE `via` — il flusso resta fermo a meta', esattamente dove
      il vecchio lock lo lasciava per minuti (a lock libero o occupato, si vede).
    """
    it = iter(seq)
    stato = {"bloccato": False}

    def fn(ex, oid, sym, secondi=60, passo=1.5):
        if probe is not None:
            probe()
        if eventi is not None and not stato["bloccato"]:
            stato["bloccato"] = True
            eventi["midflow"].set()
            if not eventi["via"].wait(timeout=15):
                raise AssertionError("test: 'via' mai ricevuto — stallo")
        try:
            esito, azione = next(it)
        except StopIteration:
            esito, azione = "closed", None
        if azione:
            azione()
        return ({"id": oid, "status": "closed" if esito == "closed" else "canceled",
                 "filled": 0.0}, esito)

    return fn


def _scenario(ca, monkeypatch, cartella, ex, attesa_fn):
    """Ambiente minimo per main(): zero rete, stato/eventi nella cartella del test."""
    monkeypatch.setattr(ca, "client", lambda: ex)
    monkeypatch.setattr(ca, "KILL", cartella / "MONEY_KILL_SWITCH")  # non esiste
    monkeypatch.setattr(ca, "STATE", cartella / "canary_state.json")
    monkeypatch.setattr(ca, "EVENTS", cartella / "canary_events.jsonl")
    monkeypatch.setattr(ca, "preflight", lambda ex: True)
    monkeypatch.setattr(ca, "cancello", _fake_cancello([]))
    monkeypatch.setattr(ca, "attesa_fill", attesa_fn)


def _main_rc(ca):
    """Esegue ca.main(); ritorna (rc, messaggio). rc None = uscita normale."""
    try:
        ca.main()
        return None, ""
    except SystemExit as e:
        return e.code, str(e)


def _stato_file(cartella):
    f = cartella / "canary_state.json"
    return json.loads(f.read_text()) if f.exists() else None


def _eventi(cartella):
    f = cartella / "canary_events.jsonl"
    if not f.exists():
        return []
    return [json.loads(l) for l in f.read_text().splitlines() if l.strip()]


def _claim_ora(tipo, pid=424242):
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {"tipo": tipo, "ts": ts, "pid": pid}


@contextlib.contextmanager
def _flusso_in_thread(ca, eventi):
    """main() del canary in un thread-servo, pilotabile da fuori (lock reale)."""
    esito = {}

    def run():
        try:
            ca.main()
        except SystemExit as e:
            esito["rc"] = e.code
        except BaseException as e:  # il test riporta l'eccezione, mai la ingoia
            esito["err"] = e

    th = threading.Thread(target=run, name="flusso-p33", daemon=True)
    th.start()
    try:
        yield esito
    finally:
        eventi["via"].set()
        th.join(timeout=20)
        if th.is_alive():  # pragma: no cover - difensivo
            raise AssertionError("thread del flusso ancora vivo: lock/attesa non rilasciati")


# ---------------------------------------------------------------------------
# spec 1 — status mentre un open e' in flusso: rc 0, lock NON trattenuto.
# ---------------------------------------------------------------------------


def test_1_status_durante_open_in_flusso_rc0_e_lock_libero(monkeypatch, cartella, capsys):
    ca = _carica_canary()
    ex = MockCanaryEx33(ca, spot_free=0.0,
                        posizioni=[_pos_perp(ca, 11.0), _pos_perp(ca, 11.0)])
    eventi = {"midflow": threading.Event(), "via": threading.Event()}
    attese = _attesa_controllata(
        [("closed", lambda: setattr(ex, "spot_free", 110.0)), ("closed", None)],
        eventi=eventi)
    _scenario(ca, monkeypatch, cartella, ex, attese)
    monkeypatch.setattr(sys, "argv", ["canary_carry.py", "open", "--execute"])

    problemi = []
    with _flusso_in_thread(ca, eventi) as esito:
        assert eventi["midflow"].wait(timeout=10), "open mai arrivato a meta' flusso"
        # (a) a meta' flusso il lock REALE deve essere libero (pre-fix: LOCK OCCUPATO)
        try:
            with ca.modulo_stato.lock_esclusivo(str(cartella / "canary_state.json")):
                pass
        except ca.modulo_stato.LockOccupato:
            problemi.append("lock occupato a meta' flusso: il lock e' ancora 'per tutto il flusso'")
        # (b) status --quiet deve uscire 0, mai LOCK OCCUPATO (pre-fix: esce in errore)
        monkeypatch.setattr(sys, "argv", ["canary_carry.py", "status", "--quiet"])
        rc_status, msg_status = _main_rc(ca)
        out = capsys.readouterr()
        testo = out.out + out.err + msg_status
        if rc_status is not None:
            problemi.append(f"status a meta' flusso: rc={rc_status!r} (atteso 0)")
        # (c) il claim attivo va mostrato nella riga di stato
        if "claim: opening" not in testo:
            problemi.append("status non mostra il claim attivo ('claim: opening' assente)")
        if "LOCK OCCUPATO" in testo:
            problemi.append("status ha prodotto LOCK OCCUPATO a meta' flusso")
    assert not problemi, "\n".join(problemi)
    assert esito == {}, f"flusso open in errore: {esito}"
    st = _stato_file(cartella)
    assert st and st.get("status") == "open", f"stato finale atteso open: {st}"
    assert "claim" not in st, f"claim non rimosso a fine open: {st.get('claim')}"


# ---------------------------------------------------------------------------
# spec 2 — close con opening fresco: exit 2 «apertura in corso», zero ordini.
# ---------------------------------------------------------------------------


def test_2_close_con_opening_fresco_rifiutata_exit2(monkeypatch, cartella, capsys):
    ca = _carica_canary()
    st0 = {"status": "closed", "claim": _claim_ora("opening", pid=777001)}
    (cartella / "canary_state.json").write_text(json.dumps(st0))
    ex = MockCanaryEx33(ca)  # nessuna posizione: senza il fix la close "chiuderebbe" tutto
    _scenario(ca, monkeypatch, cartella, ex, _attesa_controllata([]))
    monkeypatch.setattr(sys, "argv", ["canary_carry.py", "close", "--execute"])

    rc, msg = _main_rc(ca)
    out = capsys.readouterr()
    testo = out.out + out.err + msg
    assert rc == 2, f"close doveva rifiutare con exit 2 (apertura in corso), rc={rc!r} msg={msg!r}"
    assert "apertura in corso" in testo, f"manca il motivo reale «apertura in corso»: {testo!r}"
    assert ex.ordini == [], "rifiuto per operazione in corso: zero ordini"
    st1 = _stato_file(cartella)
    assert st1.get("claim") == st0["claim"], "il rifiuto NON deve toccare il claim del flusso in corso"


# ---------------------------------------------------------------------------
# spec 3 — secondo close con closing fresco: exit 2 «chiusura già in corso».
# ---------------------------------------------------------------------------


def test_3_secondo_close_con_closing_fresco_rifiutato_exit2(monkeypatch, cartella, capsys):
    ca = _carica_canary()
    st0 = {"status": "open", "claim": _claim_ora("closing", pid=777002)}
    (cartella / "canary_state.json").write_text(json.dumps(st0))
    ex = MockCanaryEx33(ca)
    _scenario(ca, monkeypatch, cartella, ex, _attesa_controllata([]))
    monkeypatch.setattr(sys, "argv", ["canary_carry.py", "close", "--execute"])

    rc, msg = _main_rc(ca)
    out = capsys.readouterr()
    testo = out.out + out.err + msg
    assert rc == 2, f"secondo close doveva rifiutare con exit 2, rc={rc!r} msg={msg!r}"
    assert "chiusura già in corso" in testo, f"manca «chiusura già in corso»: {testo!r}"
    assert ex.ordini == [], "rifiuto per operazione in corso: zero ordini"
    st1 = _stato_file(cartella)
    assert st1.get("claim") == st0["claim"], "il rifiuto NON deve toccare il claim in corso"


# ---------------------------------------------------------------------------
# spec 4 — doppio open concorrente: secondo rifiutato dal claim, primo completa.
# ---------------------------------------------------------------------------


def test_4_doppio_open_concorrente_secondo_rifiutato_dal_claim(monkeypatch, cartella, capsys):
    ca = _carica_canary()
    ex = MockCanaryEx33(ca, spot_free=0.0, posizioni=[_pos_perp(ca, 11.0)])
    eventi = {"midflow": threading.Event(), "via": threading.Event()}
    attese = _attesa_controllata(
        [("closed", lambda: setattr(ex, "spot_free", 110.0)), ("closed", None)],
        eventi=eventi)
    _scenario(ca, monkeypatch, cartella, ex, attese)
    monkeypatch.setattr(sys, "argv", ["canary_carry.py", "open", "--execute"])

    problemi = []
    with _flusso_in_thread(ca, eventi) as esito:
        assert eventi["midflow"].wait(timeout=10), "primo open mai arrivato a meta'"
        n_prima = len(ex.ordini)
        rc2, msg2 = _main_rc(ca)
        out2 = capsys.readouterr()
        testo2 = out2.out + out2.err + msg2
        if rc2 != 2:
            problemi.append(f"secondo open: rc={rc2!r} (atteso 2 — claim, non LOCK OCCUPATO)")
        if "operazione in corso" not in testo2:
            problemi.append("secondo open: manca «operazione in corso (TIPO, pid N, da Xs)»")
        if len(ex.ordini) != n_prima:
            problemi.append("il secondo open ha inviato ordini: atteso ZERO")
    assert not problemi, "\n".join(problemi)
    assert esito == {}, f"primo open in errore: {esito}"
    st = _stato_file(cartella)
    assert st and st.get("status") == "open", f"lo stato NON e' quello del primo open: {st}"
    assert "claim" not in st, "claim non rimosso dal primo open"
    # nessun lost update: il primo open ha scritto lo stato COMPLETO
    assert st.get("perp", {}).get("ct") == 11.0 and float(st.get("spot", {}).get("qty", 0)) > 0


# ---------------------------------------------------------------------------
# spec 5 — claim stantio: il successivo procede e registra claim_stantio.
# ---------------------------------------------------------------------------


def test_5_open_con_claim_stantio_procede_e_registra_evento(monkeypatch, cartella):
    ca = _carica_canary()
    ts = (datetime.now(timezone.utc) - timedelta(seconds=1000)).isoformat(timespec="seconds")
    st0 = {"status": "closed", "claim": {"tipo": "closing", "ts": ts, "pid": 999999}}
    (cartella / "canary_state.json").write_text(json.dumps(st0))
    ex = MockCanaryEx33(ca, spot_free=0.0, posizioni=[_pos_perp(ca, 11.0)])
    attese = _attesa_controllata(
        [("closed", lambda: setattr(ex, "spot_free", 110.0)), ("closed", None)])
    _scenario(ca, monkeypatch, cartella, ex, attese)
    monkeypatch.setattr(sys, "argv", ["canary_carry.py", "open", "--execute"])

    rc, msg = _main_rc(ca)
    problemi = []
    if rc is not None:
        problemi.append(f"open doveva PROCEDERE (claim stantio): rc={rc!r} msg={msg!r}")
    ev = [e for e in _eventi(cartella) if e.get("event") == "claim_stantio"]
    if not ev:
        problemi.append("evento claim_stantio assente (il claim stantio va SEMPRE registrato)")
    else:
        u = ev[-1]
        if u.get("tipo") != "closing" or u.get("pid") != 999999:
            problemi.append(f"claim_stantio senza tipo/pid del claim riciclato: {u}")
        if not (950 <= float(u.get("eta_s", -1)) <= 1150):
            problemi.append(f"claim_stantio eta_s fuori range (~1000 atteso): {u.get('eta_s')}")
    st = _stato_file(cartella)
    if not (st and st.get("status") == "open" and "claim" not in st):
        problemi.append(f"stato finale atteso open senza claim: {st}")
    assert not problemi, "\n".join(problemi)


def test_5b_close_con_claim_stantio_procede_e_registra_evento(monkeypatch, cartella):
    """Extra: come spec 5, ma il claim stantio e' di un'APERTURA e il flusso e' close."""
    ca = _carica_canary()
    ts = (datetime.now(timezone.utc) - timedelta(seconds=1000)).isoformat(timespec="seconds")
    st0 = {"status": "open", "claim": {"tipo": "opening", "ts": ts, "pid": 888888}}
    (cartella / "canary_state.json").write_text(json.dumps(st0))
    ex = MockCanaryEx33(ca)  # flat: la close non ha gambe da chiudere
    _scenario(ca, monkeypatch, cartella, ex, _attesa_controllata([]))
    monkeypatch.setattr(sys, "argv", ["canary_carry.py", "close", "--execute"])

    rc, msg = _main_rc(ca)
    problemi = []
    if rc is not None:
        problemi.append(f"close doveva PROCEDERE (claim stantio): rc={rc!r} msg={msg!r}")
    ev = [e for e in _eventi(cartella) if e.get("event") == "claim_stantio"]
    if not ev:
        problemi.append("evento claim_stantio assente")
    elif ev[-1].get("tipo") != "opening" or ev[-1].get("pid") != 888888:
        problemi.append(f"claim_stantio senza tipo/pid del claim riciclato: {ev[-1]}")
    st = _stato_file(cartella)
    if not (st and st.get("status") == "closed"):
        problemi.append(f"stato finale atteso closed: {st}")
    if st and "claim" in st:
        problemi.append(f"claim non rimosso a fine close: {st.get('claim')}")
    assert not problemi, "\n".join(problemi)


# ---------------------------------------------------------------------------
# spec 6/7 — il claim e' SU DISCO a meta' flusso e rimosso alla fine.
# ---------------------------------------------------------------------------


def _probe_letture(cartella, letture):
    def probe():
        f = cartella / "canary_state.json"
        letture.append(json.loads(f.read_text()) if f.exists() else None)
    return probe


def test_6_open_claim_scritto_a_meta_e_rimosso_alla_fine(monkeypatch, cartella):
    ca = _carica_canary()
    ex = MockCanaryEx33(ca, spot_free=0.0, posizioni=[_pos_perp(ca, 11.0)])
    letture = []
    attese = _attesa_controllata(
        [("closed", lambda: setattr(ex, "spot_free", 110.0)), ("closed", None)],
        probe=_probe_letture(cartella, letture))
    _scenario(ca, monkeypatch, cartella, ex, attese)
    monkeypatch.setattr(sys, "argv", ["canary_carry.py", "open", "--execute"])

    rc, msg = _main_rc(ca)
    problemi = []
    if rc is not None:
        problemi.append(f"open rc={rc!r} msg={msg!r}")
    if not letture:
        problemi.append("probe mai invocata: flusso non arrivato agli ordini?")
    for i, l in enumerate(letture):
        c = (l or {}).get("claim") or {}
        if c.get("tipo") != "opening":
            problemi.append(f"lettura #{i} a meta' flusso senza claim opening: {c}")
        elif c.get("pid") != os.getpid():
            problemi.append(f"lettura #{i}: pid del claim {c.get('pid')!r} != processo {os.getpid()}")
    st = _stato_file(cartella)
    if not (st and st.get("status") == "open"):
        problemi.append(f"stato finale non open: {st}")
    if st and "claim" in st:
        problemi.append("claim non rimosso a fine open")
    assert not problemi, "\n".join(problemi)


def test_7_close_claim_scritto_a_meta_e_rimosso_alla_fine(monkeypatch, cartella):
    ca = _carica_canary()
    ex = MockCanaryEx33(ca, spot_free=110.0,
                        posizioni=[_pos_perp(ca, 11.0), None, None])
    letture = []
    attese = _attesa_controllata(
        [("closed", None), ("closed", lambda: setattr(ex, "spot_free", 0.0))],
        probe=_probe_letture(cartella, letture))
    _scenario(ca, monkeypatch, cartella, ex, attese)
    monkeypatch.setattr(sys, "argv", ["canary_carry.py", "close", "--execute"])

    rc, msg = _main_rc(ca)
    problemi = []
    if rc is not None:
        problemi.append(f"close rc={rc!r} msg={msg!r}")
    if not letture:
        problemi.append("probe mai invocata: flusso non arrivato agli ordini?")
    for i, l in enumerate(letture):
        c = (l or {}).get("claim") or {}
        if c.get("tipo") != "closing":
            problemi.append(f"lettura #{i} a meta' flusso senza claim closing: {c}")
    st = _stato_file(cartella)
    if not (st and st.get("status") == "closed"):
        problemi.append(f"stato finale non closed: {st}")
    if st and "claim" in st:
        problemi.append("claim non rimosso a fine close")
    assert not problemi, "\n".join(problemi)


# ---------------------------------------------------------------------------
# extra — abort dell'open: il claim non resta orfano (rilascio nel finally).
# ---------------------------------------------------------------------------


def test_9_abort_rilascia_claim(monkeypatch, cartella):
    ca = _carica_canary()
    ex = MockCanaryEx33(ca, spot_free=0.0, posizioni=[])
    letture = []
    # il fill spot riesce ma il saldo resta 30 (< 100): abort "FILL SPOT INSUFFICIENTE"
    attese = _attesa_controllata([("closed", lambda: setattr(ex, "spot_free", 30.0))],
                                 probe=_probe_letture(cartella, letture))
    _scenario(ca, monkeypatch, cartella, ex, attese)
    monkeypatch.setattr(sys, "argv", ["canary_carry.py", "open", "--execute"])

    rc, msg = _main_rc(ca)
    problemi = []
    if "FILL SPOT INSUFFICIENTE" not in msg:
        problemi.append(f"atteso abort FILL SPOT INSUFFICIENTE: rc={rc!r} msg={msg!r}")
    c = ((letture[0] if letture else None) or {}).get("claim") or {}
    if c.get("tipo") != "opening":
        problemi.append(f"claim non scritto prima dell'abort: {c}")
    st = _stato_file(cartella)
    if st and "claim" in st:
        problemi.append(f"claim ORFANO dopo l'abort: {st.get('claim')}")
    ev = [e for e in _eventi(cartella) if e.get("event") == "claim_rilasciato"]
    if not ev:
        problemi.append("evento claim_rilasciato assente (rilascio non registrato)")
    assert not problemi, "\n".join(problemi)


# ---------------------------------------------------------------------------
# extra — stato esistente senza claim: libero (compatibilita' retroattiva).
# ---------------------------------------------------------------------------


def test_10_stato_esistente_senza_claim_e_libero(monkeypatch, cartella):
    ca = _carica_canary()
    st0 = {"status": "closed", "nota": "stato esistente pre-P33, nessun campo claim"}
    (cartella / "canary_state.json").write_text(json.dumps(st0))
    ex = MockCanaryEx33(ca, spot_free=0.0, posizioni=[_pos_perp(ca, 11.0)])
    letture = []
    attese = _attesa_controllata(
        [("closed", lambda: setattr(ex, "spot_free", 110.0)), ("closed", None)],
        probe=_probe_letture(cartella, letture))
    _scenario(ca, monkeypatch, cartella, ex, attese)
    monkeypatch.setattr(sys, "argv", ["canary_carry.py", "open", "--execute"])

    rc, msg = _main_rc(ca)
    problemi = []
    if rc is not None:
        problemi.append(f"lo stato senza claim deve essere LIBERO: rc={rc!r} msg={msg!r}")
    c = ((letture[0] if letture else None) or {}).get("claim") or {}
    if c.get("tipo") != "opening":
        problemi.append(f"claim non scritto a meta' flusso: {c}")
    st = _stato_file(cartella)
    if not (st and st.get("status") == "open" and "claim" not in st):
        problemi.append(f"stato finale atteso open senza claim: {st}")
    assert not problemi, "\n".join(problemi)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))