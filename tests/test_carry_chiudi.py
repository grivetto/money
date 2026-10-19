"""test_carry_chiudi.py — chiusura delta-neutral di una coppia carry (P28).

Test OFFLINE con MockClient (zero rete, zero chiavi, zero ordini reali):
il mock CONTA ogni chiamata, cosi' le asserzioni "dry-run = zero scritture" e
"sequenza perp -> spot" sono misurate, non dichiarate. Il modulo sotto test
viene caricato via importlib con `ccxt` stubato (pattern test_carry_config):
carry_chiudi.py ha percorsi hardcoded per MARCODG1 che non esistono su altri
nodi, e l'import non li usa (solo sys.path.insert innocui).

Criteri di accettazione della spec P28 coperti:
1. chiusura completa (entrambe le gambe), stato + evento aggiornati;
2. dry-run: zero scritture (contatore mock == 0, nessun file stato/eventi);
3. gia'-chiusa: no-op idempotente, exit 0;
4. perp assente -> solo spot (fallback C1); spot assente -> solo perp con nota;
5. perp non si chiude -> spot NON venduto; spot non si chiude dopo perp ->
   errore esplicito (spot residuo long, da sistemare a mano);
6. riconciliazione: timeout -> FAIL_CHIUSURA con nota (poll esteso REQ-008);
   latenza -> convergenza dopo N letture -> DONE;
7. guardie: coppia ignota -> rifiuto; qty mai > posizione reale (rilettura);
   mai invertire il segno (reduceOnly + lato opposto); minimi di mercato.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

RADICE = Path(__file__).resolve().parents[1]
for _p in (RADICE, RADICE / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def _carica_modulo():
    """Carica scripts/carry_chiudi.py come modulo (offline, zero inquinamento).

    carry_chiudi importa `ccxt` e `scripts.carry_multi` (che importa `ccxt`
    a sua volta): ccxt viene stubato, e alla fine sys.modules torna
    ESATTAMENTE allo stato precedente (come test_carry_config).
    """
    percorso = RADICE / "scripts" / "carry_chiudi.py"
    spec = importlib.util.spec_from_file_location("carry_chiudi_under_test",
                                                  percorso)
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


mod = _carica_modulo()
COPPIE = mod.COPPIE
C = COPPIE["DOT"]                       # ct_val 1.0, sym_spot DOT/USDC
SYM_PERP, SYM_SPOT = C.sym_perp, C.sym_spot


# ---------------------------------------------------------------------------
# MockClient: zero rete, conta ogni chiamata, latenze configurabili
# ---------------------------------------------------------------------------

class MockClient:
    """Exchange finto per i test (pattern earn_move): muta saldi/posizioni in
    modo coerente con reduceOnly, con latenza di aggiornamento configurabile
    (lezione REQ-008: la lettura vede il pre-chiusura per N letture)."""

    def __init__(self, *, coin="DOT", pos_ct=0.0, spot_qty=0.0,
                 px_perp=10.0, px_spot=10.0, spread=0.0005,
                 min_ct=0.0, min_spot=0.0, fee_rate=0.001,
                 pos_delay_reads=0, spot_delay_reads=0,
                 stay_open=None, fail_send=None,
                 pos_shift_reads=None, pos_shift_to=None):
        self.coin = coin
        self.pos_ct = float(pos_ct)
        self.spot_qty = float(spot_qty)
        self.px_perp = float(px_perp)
        self.px_spot = float(px_spot)
        self.spread = float(spread)
        self.min_ct = float(min_ct)
        self.min_spot = float(min_spot)
        self.fee_rate = float(fee_rate)
        self.calls = []          # (nome_chiamata, ...) in ordine
        self.ordini = []         # dict di create_order: symbol/side/qty/prezzo/params
        self.stay_open = set(stay_open or ())
        self.fail_send = set(fail_send or ())
        self.pos_delay_reads = pos_delay_reads
        self.spot_delay_reads = spot_delay_reads
        self.pos_shift_reads = pos_shift_reads
        self.pos_shift_to = pos_shift_to
        self._pos_reads = 0
        self._pos_shifted = False
        self._pos_hidden = 0.0
        self._pos_wait = 0
        self._spot_hidden = 0.0
        self._spot_wait = 0
        self._order_states = {}

    # -- letture ------------------------------------------------------------
    def load_markets(self):
        self.calls.append(("load_markets",))

    def market(self, symbol):
        self.calls.append(("market", symbol))
        if "USD:" in symbol:
            return {"limits": {"amount": {"min": self.min_ct}}}
        return {"limits": {"amount": {"min": self.min_spot}}}

    def fetch_ticker(self, symbol):
        self.calls.append(("fetch_ticker", symbol))
        base = self.px_perp if "USD:" in symbol else self.px_spot
        return {"last": base, "bid": base * (1 - self.spread),
                "ask": base * (1 + self.spread)}

    def price_to_precision(self, symbol, price):
        return round(float(price), 8)

    def fetch_positions(self, symbols=None):
        self.calls.append(("fetch_positions", list(symbols or [])))
        self._pos_reads += 1
        if (self.pos_shift_reads is not None
                and self._pos_reads >= self.pos_shift_reads
                and not self._pos_shifted):
            self._pos_shifted = True
            self.pos_ct = float(self.pos_shift_to)
        pos = self.pos_ct
        if self._pos_wait > 0:                    # latenza: mostra il pre-chiusura
            self._pos_wait -= 1
            pos += self._pos_hidden
            if self._pos_wait == 0:
                self._pos_hidden = 0.0
        if abs(pos) <= 1e-9:
            return []
        return [{"symbol": (symbols or ["?"])[0], "contracts": pos}]

    def fetch_balance(self):
        self.calls.append(("fetch_balance",))
        q = self.spot_qty
        if self._spot_wait > 0:                   # latenza: mostra il pre-chiusura
            self._spot_wait -= 1
            q += self._spot_hidden
            if self._spot_wait == 0:
                self._spot_hidden = 0.0
        return {"total": {self.coin: q}, "free": {self.coin: q}}

    # -- ordini -------------------------------------------------------------
    def create_order(self, symbol, tipo, side, qty, prezzo, params=None):
        params = params or {}
        self.calls.append(("create_order", symbol, tipo, side, qty, prezzo,
                           dict(params)))
        self.ordini.append({"symbol": symbol, "tipo": tipo, "side": side,
                            "qty": float(qty), "prezzo": float(prezzo),
                            "params": dict(params)})
        oid = f"mock-{len(self.ordini)}"
        if symbol in self.fail_send:
            self._order_states[oid] = {"id": oid, "status": "open", "filled": 0.0}
            raise RuntimeError("mock: invio rifiutato")
        if symbol in self.stay_open:
            o = {"id": oid, "symbol": symbol, "side": side, "status": "open",
                 "filled": 0.0, "average": None, "price": float(prezzo),
                 "fee": None}
            self._order_states[oid] = o
            return o
        if "USD:" in symbol:
            eff = self._fill_perp(side, float(qty), params)
        else:
            eff = self._fill_spot(side, float(qty))
        status = "closed" if eff >= float(qty) - 1e-12 else "partial"
        fee = eff * float(prezzo) * self.fee_rate
        o = {"id": oid, "symbol": symbol, "side": side, "status": status,
             "filled": eff, "average": float(prezzo), "price": float(prezzo),
             "fee": {"cost": fee, "currency": "USDC"}}
        self._order_states[oid] = o
        return o

    def _fill_perp(self, side, qty, params):
        reduce_only = bool(params.get("reduceOnly"))
        if side == "buy":
            cap = max(-self.pos_ct, 0.0) if reduce_only else qty
            eff = min(qty, cap)
            self.pos_ct += eff
            applicato = eff
        else:
            cap = max(self.pos_ct, 0.0) if reduce_only else qty
            eff = min(qty, cap)
            self.pos_ct -= eff
            applicato = -eff
        if self.pos_delay_reads > 0:
            self._pos_hidden = -applicato
            self._pos_wait = self.pos_delay_reads
        return eff

    def _fill_spot(self, side, qty):
        if side == "sell":
            eff = min(qty, self.spot_qty)
            self.spot_qty -= eff
            applicato = eff
        else:
            eff = qty
            self.spot_qty += eff
            applicato = -eff
        if self.spot_delay_reads > 0:
            self._spot_hidden = applicato
            self._spot_wait = self.spot_delay_reads
        return eff

    def fetch_order(self, oid, symbol):
        self.calls.append(("fetch_order", oid, symbol))
        if oid not in self._order_states:
            return {"id": oid, "status": "canceled"}
        return dict(self._order_states[oid])

    def cancel_order(self, oid, symbol):
        self.calls.append(("cancel_order", oid, symbol))
        if oid in self._order_states:
            self._order_states[oid]["status"] = "canceled"
        return {"id": oid, "status": "canceled"}

    def scritture(self):
        return [c for c in self.calls if c[0] in ("create_order", "cancel_order")]


def noop_sleep(_):
    return None


def cfg(**over):
    base = dict(coppia="DOT", motivo="", execute=True)
    base.update(over)
    return mod.Config(**base)


def leggi_eventi(stato_dir):
    righe = (stato_dir / "eventi.jsonl").read_text().splitlines()
    return [json.loads(r) for r in righe if r.strip()]


# ---------------------------------------------------------------------------
# 1. Chiusura completa
# ---------------------------------------------------------------------------

def test_chiusura_completa_entrambe_le_gambe(tmp_path, capsys):
    mock = MockClient(pos_ct=-8.0, spot_qty=8.0)
    stato_dir = tmp_path / "stato"
    rc = mod.esegui(mock, cfg(stato_dir=stato_dir), sleep_fn=noop_sleep)
    assert rc == 0
    # sequenza: PERP poi SPOT, entrambi LIMIT
    assert [(o["symbol"], o["side"], o["qty"]) for o in mock.ordini] == [
        (SYM_PERP, "buy", 8.0), (SYM_SPOT, "sell", 8.0)]
    # perp: reduceOnly + margine dichiarato; spot: reduceOnly assente
    assert mock.ordini[0]["params"]["reduceOnly"] is True
    assert mock.ordini[0]["params"]["tdMode"] == "isolated"
    assert "reduceOnly" not in mock.ordini[1]["params"]
    # posizioni a zero nel mock
    assert mock.pos_ct == 0.0 and mock.spot_qty == 0.0
    # stato aggiornato: status closed, ts_chiudi, esiti, fee
    stato = json.loads((stato_dir / "stato.json").read_text())
    voce = stato["coppie"]["DOT"]
    assert voce["status"] == "closed"
    assert voce["ts_chiudi"]
    assert voce["esiti"] == {"perp": "closed", "spot": "closed"}
    assert voce["fee"] is not None and voce["fee"] > 0
    # eventi: iniziata, perp, spot, completa
    tipi = [e["evento"] for e in leggi_eventi(stato_dir)]
    assert tipi == ["chiusura_iniziata", "chiusura_perp", "chiusura_spot",
                    "chiusura_completa"]
    out = capsys.readouterr().out
    assert "RICONCILIAZIONE OK" in out and "CHIUSA" in out


def test_motivo_registrato_in_eventi_e_stato(tmp_path):
    mock = MockClient(pos_ct=-8.0, spot_qty=8.0)
    stato_dir = tmp_path / "stato"
    rc = mod.esegui(mock, cfg(stato_dir=stato_dir, motivo="deterioramento funding"),
                    sleep_fn=noop_sleep)
    assert rc == 0
    ev = leggi_eventi(stato_dir)
    assert ev[0]["evento"] == "chiusura_iniziata"
    assert ev[0]["motivo"] == "deterioramento funding"
    stato = json.loads((stato_dir / "stato.json").read_text())
    assert stato["coppie"]["DOT"]["motivo_chiudi"] == "deterioramento funding"


def test_fee_somma_delle_due_gambe_in_stato(tmp_path):
    mock = MockClient(pos_ct=-8.0, spot_qty=8.0, fee_rate=0.001)
    stato_dir = tmp_path / "stato"
    rc = mod.esegui(mock, cfg(stato_dir=stato_dir), sleep_fn=noop_sleep)
    assert rc == 0
    stato = json.loads((stato_dir / "stato.json").read_text())
    # fee = 8*prezzo*0,1% per gamba, prezzo = ask*1,002 / bid*0,998 (~10)
    fee = stato["coppie"]["DOT"]["fee"]
    assert fee is not None
    assert abs(fee - 0.16) < 0.01


# ---------------------------------------------------------------------------
# 2. Dry-run: zero scritture
# ---------------------------------------------------------------------------

def test_dryrun_zero_scritture(tmp_path, capsys):
    mock = MockClient(pos_ct=-8.0, spot_qty=8.0)
    stato_dir = tmp_path / "stato"
    rc = mod.esegui(mock, cfg(execute=False, stato_dir=stato_dir),
                    sleep_fn=noop_sleep)
    assert rc == 0
    assert mock.ordini == []
    assert mock.scritture() == []
    assert all(c[0].startswith("fetch") or c[0] in ("load_markets", "market")
               for c in mock.calls)
    assert not stato_dir.exists()          # zero file stato/eventi
    out = capsys.readouterr().out
    assert "DRY-RUN" in out and "0 ordini" in out
    assert "gamba 1/2 perp" in out and "gamba 2/2 spot" in out
    assert "stima fee" in out


# ---------------------------------------------------------------------------
# 3. Gia' chiusa: no-op idempotente
# ---------------------------------------------------------------------------

def test_gia_chiusa_noop_idempotente(tmp_path, capsys):
    mock = MockClient(pos_ct=0.0, spot_qty=0.0)
    stato_dir = tmp_path / "stato"
    rc = mod.esegui(mock, cfg(stato_dir=stato_dir), sleep_fn=noop_sleep)
    assert rc == 0
    assert mock.ordini == [] and mock.scritture() == []
    assert not stato_dir.exists()
    assert "gia' chiusa" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# 4/5. Gambe parziali: solo spot (fallback C1) / solo perp con nota
# ---------------------------------------------------------------------------

def test_perp_assente_solo_spot_fallback_c1(tmp_path, capsys):
    mock = MockClient(pos_ct=0.0, spot_qty=8.0)
    stato_dir = tmp_path / "stato"
    rc = mod.esegui(mock, cfg(stato_dir=stato_dir), sleep_fn=noop_sleep)
    assert rc == 0
    assert [(o["symbol"], o["side"], o["qty"]) for o in mock.ordini] == [
        (SYM_SPOT, "sell", 8.0)]
    assert mock.spot_qty == 0.0
    stato = json.loads((stato_dir / "stato.json").read_text())
    assert stato["coppie"]["DOT"]["status"] == "closed"
    assert stato["coppie"]["DOT"]["esiti"] == {"perp": "assente", "spot": "closed"}
    assert "RICONCILIAZIONE OK" in capsys.readouterr().out


def test_spot_assente_solo_perp_con_nota(tmp_path, capsys):
    mock = MockClient(pos_ct=-8.0, spot_qty=0.0)
    stato_dir = tmp_path / "stato"
    rc = mod.esegui(mock, cfg(stato_dir=stato_dir), sleep_fn=noop_sleep)
    assert rc == 0
    assert [(o["symbol"], o["side"], o["qty"]) for o in mock.ordini] == [
        (SYM_PERP, "buy", 8.0)]
    assert mock.pos_ct == 0.0
    stato = json.loads((stato_dir / "stato.json").read_text())
    assert stato["coppie"]["DOT"]["esiti"] == {"perp": "closed", "spot": "assente"}
    out = capsys.readouterr().out
    assert "gamba 2/2 spot: assente" in out and "RICONCILIAZIONE OK" in out


# ---------------------------------------------------------------------------
# 6. Fallimenti espliciti
# ---------------------------------------------------------------------------

def test_perp_non_si_chiude_spot_non_venduto(tmp_path, capsys):
    mock = MockClient(pos_ct=-8.0, spot_qty=8.0, stay_open={SYM_PERP})
    stato_dir = tmp_path / "stato"
    rc = mod.esegui(mock, cfg(stato_dir=stato_dir), sleep_fn=noop_sleep)
    assert rc == 1
    # retry perp (2 ordini) e ZERO ordini spot: nessuna posizione nuda
    assert [o["symbol"] for o in mock.ordini] == [SYM_PERP, SYM_PERP]
    assert mock.spot_qty == 8.0                    # spot INTATTO
    assert mock.pos_ct == -8.0                     # perp residua
    stato = json.loads((stato_dir / "stato.json").read_text())
    voce = stato["coppie"]["DOT"]
    assert voce["status"] == "chiusura_fallita"
    assert voce["esiti"] == {"perp": "reprice", "spot": "non_tentato"}
    assert "NON viene venduta" in voce["nota_chiudi"]
    ev = leggi_eventi(stato_dir)
    assert ev[-1]["evento"] == "chiusura_fallita"
    assert "FALLIMENTO CHIUSURA" in capsys.readouterr().out


def test_spot_non_si_chiude_dopo_perp_nota_residuo(tmp_path, capsys):
    mock = MockClient(pos_ct=-8.0, spot_qty=8.0, stay_open={SYM_SPOT})
    stato_dir = tmp_path / "stato"
    rc = mod.esegui(mock, cfg(stato_dir=stato_dir), sleep_fn=noop_sleep)
    assert rc == 1
    # perp chiusa, spot tentato 2 volte e residuo
    assert [o["symbol"] for o in mock.ordini] == [SYM_PERP, SYM_SPOT, SYM_SPOT]
    assert mock.pos_ct == 0.0
    assert mock.spot_qty == 8.0
    stato = json.loads((stato_dir / "stato.json").read_text())
    voce = stato["coppie"]["DOT"]
    assert voce["status"] == "chiusura_fallita"
    assert voce["esiti"]["perp"] == "closed"
    assert voce["esiti"]["spot"] == "reprice"
    assert "spot residuo" in voce["nota_chiudi"]
    assert "LONG" in voce["nota_chiudi"]
    ev = leggi_eventi(stato_dir)
    assert ev[-1]["evento"] == "chiusura_fallita"


def test_invio_perp_fallito_spot_mai_tentato(tmp_path, capsys):
    mock = MockClient(pos_ct=-8.0, spot_qty=8.0, fail_send={SYM_PERP})
    stato_dir = tmp_path / "stato"
    rc = mod.esegui(mock, cfg(stato_dir=stato_dir), sleep_fn=noop_sleep)
    assert rc == 1
    assert [o["symbol"] for o in mock.ordini] == [SYM_PERP]   # solo il tentativo fallito
    assert mock.spot_qty == 8.0
    stato = json.loads((stato_dir / "stato.json").read_text())
    voce = stato["coppie"]["DOT"]
    assert voce["status"] == "chiusura_fallita"
    assert voce["esiti"] == {"perp": "invio_fallito", "spot": "non_tentato"}
    assert "invio perp FALLITO" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# 7. Riconciliazione: poll esteso (lezione REQ-008)
# ---------------------------------------------------------------------------

def test_riconciliazione_timeout_fail_con_nota(tmp_path, capsys):
    mock = MockClient(pos_ct=-8.0, spot_qty=8.0, pos_delay_reads=10**9,
                      spot_delay_reads=10**9)
    stato_dir = tmp_path / "stato"
    rc = mod.esegui(mock, cfg(stato_dir=stato_dir), sleep_fn=noop_sleep)
    assert rc == 1
    # gli ordini sono partiti e riempiti (stato vero del mock), ma le letture
    # non convergono mai -> FAIL_CHIUSURA senza azioni correttive oltre i
    # 2 ordini previsti
    assert len(mock.ordini) == 2
    stato = json.loads((stato_dir / "stato.json").read_text())
    voce = stato["coppie"]["DOT"]
    assert voce["status"] == "chiusura_fallita"
    assert "latenza" in voce["nota_chiudi"]
    assert "nessuna azione correttiva automatica" in voce["nota_chiudi"]
    ev = leggi_eventi(stato_dir)
    assert ev[-1]["evento"] == "chiusura_fallita"
    out = capsys.readouterr().out
    assert "FAIL_CHIUSURA" in out
    assert "nessuna azione correttiva automatica" in out


def test_riconciliazione_latenza_poi_converge(tmp_path, capsys):
    mock = MockClient(pos_ct=-8.0, spot_qty=8.0, pos_delay_reads=3,
                      spot_delay_reads=3)
    stato_dir = tmp_path / "stato"
    rc = mod.esegui(mock, cfg(stato_dir=stato_dir), sleep_fn=noop_sleep)
    assert rc == 0
    out = capsys.readouterr().out
    assert "RICONCILIAZIONE OK" in out and "convergenza alla lettura 4" in out
    stato = json.loads((stato_dir / "stato.json").read_text())
    assert stato["coppie"]["DOT"]["status"] == "closed"


# ---------------------------------------------------------------------------
# 8. Guardie
# ---------------------------------------------------------------------------

def test_coppia_ignota_rifiutata(capsys):
    rc = mod.main(["--coppia", "BTC"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "RIFIUTO" in err and "coppia ignota" in err


def test_env_mancante_execute_rifiuto_e_dryrun_errore(monkeypatch, tmp_path,
                                                      capsys):
    inesistente = tmp_path / "nope.env"
    monkeypatch.setattr(mod, "ENV_FILE", inesistente)
    assert mod.main(["--coppia", "DOT", "--execute"]) == 2
    err = capsys.readouterr().err
    assert "RIFIUTO" in err and "--execute" in err
    assert mod.main(["--coppia", "DOT"]) == 1
    err = capsys.readouterr().err
    assert "env-file mancante" in err


def test_qty_mai_sopra_posizione_reale_rilettura(tmp_path):
    # tra il pre-check e l'ordine la posizione cambia (-8 -> -12): l'ordine
    # usa la posizione ATTuale riletta, mai una qty superiore al reale
    mock = MockClient(pos_ct=-8.0, spot_qty=8.0,
                      pos_shift_reads=2, pos_shift_to=-12.0)
    stato_dir = tmp_path / "stato"
    rc = mod.esegui(mock, cfg(stato_dir=stato_dir), sleep_fn=noop_sleep)
    assert rc == 0
    assert mock.ordini[0]["qty"] == 12.0
    assert mock.ordini[0]["params"]["reduceOnly"] is True
    assert mock.pos_ct == 0.0


def test_posizione_lunga_chiusa_senza_invertire_segno(tmp_path):
    # anomalia: perp LONG (+8): si chiude con SELL reduceOnly, mai invertendo
    mock = MockClient(pos_ct=8.0, spot_qty=8.0)
    stato_dir = tmp_path / "stato"
    rc = mod.esegui(mock, cfg(stato_dir=stato_dir), sleep_fn=noop_sleep)
    assert rc == 0
    assert [(o["symbol"], o["side"]) for o in mock.ordini] == [
        (SYM_PERP, "sell"), (SYM_SPOT, "sell")]
    assert mock.ordini[0]["params"]["reduceOnly"] is True
    assert mock.pos_ct == 0.0


def test_guardia_min_order_size_perp(tmp_path, capsys):
    mock = MockClient(pos_ct=-8.0, spot_qty=8.0, min_ct=100.0)
    rc = mod.esegui(mock, cfg(stato_dir=tmp_path / "stato"),
                    sleep_fn=noop_sleep)
    assert rc == 2
    assert mock.ordini == []
    out = capsys.readouterr().out
    assert "RIFIUTO" in out
    assert "minimo" in out


def test_guardia_min_order_size_spot(tmp_path, capsys):
    mock = MockClient(pos_ct=-8.0, spot_qty=8.0, min_spot=100.0)
    rc = mod.esegui(mock, cfg(stato_dir=tmp_path / "stato"),
                    sleep_fn=noop_sleep)
    assert rc == 2
    assert mock.ordini == []
    assert "RIFIUTO" in capsys.readouterr().out


def test_stato_assente_avviso_ma_procede(tmp_path, capsys):
    # stato.json assente: avviso, MAI bloccante — governano le posizioni reali
    mock = MockClient(pos_ct=-8.0, spot_qty=8.0)
    stato_dir = tmp_path / "stato_vuoto"
    rc = mod.esegui(mock, cfg(execute=False, stato_dir=stato_dir),
                    sleep_fn=noop_sleep)
    assert rc == 0
    out = capsys.readouterr().out
    assert "ATTENZIONE" in out and "posizioni REALI" in out


# ---------------------------------------------------------------------------
# Utilita'
# ---------------------------------------------------------------------------

def test_cid_stabile_deterministico_e_diverso():
    a = mod.cid_stabile("dotx", "close_perp|X|8|2026-10-19")
    b = mod.cid_stabile("dotx", "close_perp|X|8|2026-10-19")
    c = mod.cid_stabile("dotx", "close_perp|X|8|2026-10-20")
    assert a == b and a != c
    assert len(a) <= 32


def test_leggi_stato_mancante_o_corrotto(tmp_path):
    assert mod.leggi_stato(tmp_path / "vuoto") == {"coppie": {}}
    (tmp_path / "stato.json").write_text("{corrotto")
    assert mod.leggi_stato(tmp_path) == {"coppie": {}}


def test_attesa_fill_timeout_reprice_e_cancel_partial(tmp_path):
    mock = MockClient(stay_open={SYM_PERP})
    c = COPPIE["DOT"]
    o = mock.create_order(c.sym_perp, "limit", "buy", 8.0, 10.0,
                          {"reduceOnly": True, "tdMode": "isolated"})
    oo, es = mod.attesa_fill(mock, o["id"], c.sym_perp, 3, noop_sleep)
    assert es == "reprice"
    mock.cancel_order(o["id"], c.sym_perp)
    oo, es = mod.attesa_fill(mock, o["id"], c.sym_perp, 2, noop_sleep)
    assert es == "partial"


def test_somma_fee():
    assert mod.somma_fee([None, None]) is None
    assert abs(mod.somma_fee([0.1, 0.2]) - 0.3) < 1e-12
    assert abs(mod.somma_fee([None, 0.2]) - 0.2) < 1e-12


def test_senza_implementazione_il_test_fallirebbe():
    # prova rosso-verde: il modulo deve esportare il core e il dict COPPIE
    assert callable(mod.esegui) and callable(mod.main)
    assert "DOT" in COPPIE and "LTC" in COPPIE and "AVAX" in COPPIE
