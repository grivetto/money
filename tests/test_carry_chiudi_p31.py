"""test_carry_chiudi_p31.py — regressione dei fix F1-F6 di P31 (audit 20/10).

Ogni test qui sotto FALLISCE sul codice pre-fix (rosso documentato in
rosso_pre_fix.txt) e passa con i fix F1-F6 di P31.

Forma reale di ccxt (verificata da Artu' sull'account OKX reale):
`fetch_positions` restituisce `contracts` POSITIVO (taglia) e la direzione
nel campo `side` ("short"/"long"); `info["pos"]` e' il valore con segno.
Il MockClientP31 la riproduce fedelmente, a differenza del mock di P28 che
usa `contracts` firmato e mascherava A1.
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
    """Come test_carry_chiudi.py: modulo sotto test via importlib, ccxt
    stubato, sys.modules ripulito a fine caricamento."""
    percorso = RADICE / "scripts" / "carry_chiudi.py"
    spec = importlib.util.spec_from_file_location("carry_chiudi_p31_under_test",
                                                  percorso)
    assert spec is not None and spec.loader is not None
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
C = mod.COPPIE["DOT"]
SYM_PERP, SYM_SPOT = C.sym_perp, C.sym_spot


class MockClientP31:
    """Exchange finto nella FORMA REALE di ccxt: contracts >= 0 + side.
    Comparti separati trading/funding/earn; ordini per clOrdId; fill parziale
    configurabile (F6); pos_sequence per letture discordanti (F4)."""

    def __init__(self, *, coin="DOT", pos_ct=0.0, pos_side=None, info_pos=None,
                 pos_sequence=None, spot_qty=0.0, funding_qty=0.0, earn_qty=0.0,
                 px_perp=10.0, px_spot=10.0, spread=0.0005,
                 min_ct=0.0, min_spot=0.0, fee_rate=0.001,
                 stay_open=None, fail_after_register=None,
                 partial_first_spot=None, partial_first_perp=None):
        self.coin = coin
        self.pos_ct = float(pos_ct)
        self.pos_side = pos_side
        self.info_pos = info_pos
        self.pos_sequence = (list(pos_sequence)
                             if pos_sequence is not None else None)
        self.spot_qty = float(spot_qty)
        self.funding_qty = float(funding_qty)
        self.earn_qty = float(earn_qty)
        self.px_perp = float(px_perp)
        self.px_spot = float(px_spot)
        self.spread = float(spread)
        self.min_ct = float(min_ct)
        self.min_spot = float(min_spot)
        self.fee_rate = float(fee_rate)
        self.calls = []
        self.ordini = []
        self.cancel_calls = []
        self.stay_open = set(stay_open or ())
        self.fail_after_register = set(fail_after_register or ())
        self.partial_first_spot = partial_first_spot
        self.partial_first_perp = partial_first_perp
        self._spot_first_done = False
        self._perp_first_done = False
        self._orders = {}
        self._open_by_cid = {}
        self._n = 0

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

    def _prossima_pos(self):
        if self.pos_sequence is not None:
            if self._n < len(self.pos_sequence):
                v = self.pos_sequence[self._n]
            else:
                v = self.pos_ct
            self._n += 1
            return v
        return self.pos_ct

    def fetch_positions(self, symbols=None):
        self.calls.append(("fetch_positions", list(symbols or [])))
        v = self._prossima_pos()
        if v is None:
            return []
        ct = float(v)
        if abs(ct) <= 1e-9:
            return []
        # FORMA REALE ccxt: contracts positivo, direzione in side
        side = self.pos_side or ("short" if ct < 0 else "long")
        ipos = self.info_pos if self.info_pos is not None else ct
        return [{"symbol": (symbols or ["?"])[0], "contracts": abs(ct),
                 "side": side, "info": {"pos": ipos}}]

    def fetch_balance(self, params=None):
        tipo = (params or {}).get("type") if isinstance(params, dict) else None
        tipo = tipo or "trading"
        self.calls.append(("fetch_balance", tipo))
        if tipo == "funding":
            q = self.funding_qty
        elif tipo == "earn":
            q = self.earn_qty
        else:
            q = self.spot_qty
        return {"total": {self.coin: q}, "free": {self.coin: q}}

    # -- ordini -------------------------------------------------------------
    def create_order(self, symbol, tipo, side, qty, prezzo, params=None):
        params = params or {}
        cid = params.get("clOrdId", "")
        self.calls.append(("create_order", symbol, tipo, side, qty, prezzo,
                           dict(params)))
        self.ordini.append({"symbol": symbol, "tipo": tipo, "side": side,
                            "qty": float(qty), "prezzo": float(prezzo),
                            "params": dict(params)})
        oid = f"mock-{len(self.ordini)}"
        if symbol in self.fail_after_register:
            # timeout DOPO che la sede ha accettato: l'ordine e' vivo
            o = {"id": oid, "symbol": symbol, "side": side, "status": "open",
                 "filled": 0.0, "average": None, "price": float(prezzo),
                 "fee": None, "clientOrderId": cid}
            self._orders[oid] = o
            self._open_by_cid[cid] = o
            raise RuntimeError("mock: RequestTimeout dopo l'accettazione")
        if symbol in self.stay_open:
            o = {"id": oid, "symbol": symbol, "side": side, "status": "open",
                 "filled": 0.0, "average": None, "price": float(prezzo),
                 "fee": None, "clientOrderId": cid}
            self._orders[oid] = o
            self._open_by_cid[cid] = o
            return o
        if "USD:" in symbol and not self._perp_first_done \
                and self.partial_first_perp is not None:
            self._perp_first_done = True
            eff = min(float(self.partial_first_perp), float(qty))
            self.pos_ct += eff if side == "buy" else -eff
            fee = eff * float(prezzo) * self.fee_rate   # forma reale ccxt
            o = {"id": oid, "symbol": symbol, "side": side, "status": "open",
                 "filled": eff, "average": float(prezzo),
                 "price": float(prezzo),
                 "fee": {"cost": fee, "currency": "USDC"},
                 "clientOrderId": cid}
            self._orders[oid] = o
            self._open_by_cid[cid] = o
            return o
        if "USD:" not in symbol and not self._spot_first_done \
                and self.partial_first_spot is not None:
            self._spot_first_done = True
            eff = min(float(self.partial_first_spot), float(qty))
            self.spot_qty -= eff
            fee = eff * float(prezzo) * self.fee_rate   # forma reale ccxt
            o = {"id": oid, "symbol": symbol, "side": side, "status": "open",
                 "filled": eff, "average": float(prezzo),
                 "price": float(prezzo),
                 "fee": {"cost": fee, "currency": "USDC"},
                 "clientOrderId": cid}
            self._orders[oid] = o
            self._open_by_cid[cid] = o
            return o
        if "USD:" in symbol:
            eff = self._fill_perp(side, float(qty), params)
        else:
            eff = self._fill_spot(side, float(qty))
        status = "closed" if eff >= float(qty) - 1e-12 else "partial"
        fee = eff * float(prezzo) * self.fee_rate
        o = {"id": oid, "symbol": symbol, "side": side, "status": status,
             "filled": eff, "average": float(prezzo), "price": float(prezzo),
             "fee": {"cost": fee, "currency": "USDC"}, "clientOrderId": cid}
        self._orders[oid] = o
        return o

    def _fill_perp(self, side, qty, params):
        reduce_only = bool(params.get("reduceOnly"))
        if side == "buy":
            cap = max(-self.pos_ct, 0.0) if reduce_only else qty
            eff = min(qty, cap)
            self.pos_ct += eff
        else:
            cap = max(self.pos_ct, 0.0) if reduce_only else qty
            eff = min(qty, cap)
            self.pos_ct -= eff
        return eff

    def _fill_spot(self, side, qty):
        if side == "sell":
            eff = min(qty, self.spot_qty)
            self.spot_qty -= eff
        else:
            eff = qty
            self.spot_qty += eff
        return eff

    def fetch_order(self, oid, symbol):
        self.calls.append(("fetch_order", oid, symbol))
        if oid in self._orders:
            return dict(self._orders[oid])
        if oid in self._open_by_cid:
            return dict(self._open_by_cid[oid])
        return {"id": oid, "status": "canceled"}

    def fetch_open_orders(self, symbol=None):
        self.calls.append(("fetch_open_orders", symbol))
        return [dict(o) for o in self._open_by_cid.values()
                if symbol is None or o.get("symbol") == symbol]

    def cancel_order(self, oid, symbol):
        self.calls.append(("cancel_order", oid, symbol))
        self.cancel_calls.append((oid, symbol))
        if oid in self._orders:
            self._orders[oid]["status"] = "canceled"
        for cid, o in list(self._open_by_cid.items()):
            if o["id"] == oid or cid == oid:
                o["status"] = "canceled"
                del self._open_by_cid[cid]
        return {"id": oid, "status": "canceled"}

    def scritture(self):
        return [c for c in self.calls if c[0] in ("create_order", "cancel_order")]


def noop_sleep(_):
    return None


def cfg(**over):
    base = dict(coppia="DOT", motivo="", execute=True)
    base.update(over)
    return mod.Config(**base)


def scrivi_stato(stato_dir, voce):
    stato_dir.mkdir(parents=True, exist_ok=True)
    (stato_dir / "stato.json").write_text(json.dumps({"coppie": {"DOT": voce}}))


def leggi_eventi(stato_dir):
    righe = (stato_dir / "eventi.jsonl").read_text().splitlines()
    return [json.loads(r) for r in righe if r.strip()]


# ---------------------------------------------------------------------------
# F1 (ALTA) — lato e taglia dalla forma reale di ccxt
# ---------------------------------------------------------------------------

def test_f1_short_reale_piano_buy_e_ordine_buy(tmp_path, capsys):
    """Forma reale (contracts=+78, side=short): chiusura BUY reduceOnly.
    PRE-FIX: qty_perp legge +78 -> sell reduceOnly su short -> non chiude."""
    mock = MockClientP31(pos_ct=-78.0, pos_side="short", info_pos=-78.0,
                         spot_qty=78.0)
    stato_dir = tmp_path / "stato"
    rc = mod.esegui(mock, cfg(stato_dir=stato_dir), sleep_fn=noop_sleep)
    assert rc == 0
    out = capsys.readouterr().out
    assert "buy 78 ct reduceOnly" in out
    assert [(o["symbol"], o["side"], o["qty"]) for o in mock.ordini] == [
        (SYM_PERP, "buy", 78.0), (SYM_SPOT, "sell", 78.0)]
    assert mock.ordini[0]["params"]["reduceOnly"] is True
    stato = json.loads((stato_dir / "stato.json").read_text())
    assert stato["coppie"]["DOT"]["status"] == "closed"


def test_f1_long_reale_chiusa_con_sell(tmp_path, capsys):
    """Forma reale long: sell reduceOnly (regressione: pre-fix gia' ok)."""
    mock = MockClientP31(pos_ct=5.0, pos_side="long", info_pos=5.0,
                         spot_qty=5.0)
    stato_dir = tmp_path / "stato"
    rc = mod.esegui(mock, cfg(stato_dir=stato_dir), sleep_fn=noop_sleep)
    assert rc == 0
    out = capsys.readouterr().out
    assert "sell 5 ct reduceOnly" in out
    assert (mock.ordini[0]["symbol"], mock.ordini[0]["side"]) == (SYM_PERP, "sell")
    stato = json.loads((stato_dir / "stato.json").read_text())
    assert stato["coppie"]["DOT"]["status"] == "closed"


def test_f1_contraddizione_side_info_pos_exit1_zero_ordini(tmp_path, capsys):
    """contracts=78, side=short ma info.pos=+78: contraddizione -> exit 1,
    ZERO ordini (il segno non si deduce mai da una fonte ambigua)."""
    mock = MockClientP31(pos_ct=-78.0, pos_side="short", info_pos=78.0,
                         spot_qty=78.0)
    stato_dir = tmp_path / "stato"
    rc = mod.esegui(mock, cfg(stato_dir=stato_dir), sleep_fn=noop_sleep)
    assert rc == 1
    assert mock.ordini == []
    assert "incoerente" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# F2 (ALTA) — eccezione su create_order != "ordine non inviato"
# ---------------------------------------------------------------------------

def test_f2_eccezione_ordine_vivo_perp_incerto_cancel_exit1(tmp_path, capsys):
    """create_order perp solleva ma l'ordine e' vivo (clOrdId): annullarlo,
    esito=incerto, exit 1, gamba spot MAI tentata."""
    mock = MockClientP31(pos_ct=-8.0, pos_side="short", info_pos=-8.0,
                         spot_qty=8.0, fail_after_register={SYM_PERP})
    stato_dir = tmp_path / "stato"
    rc = mod.esegui(mock, cfg(stato_dir=stato_dir), sleep_fn=noop_sleep)
    assert rc == 1
    stato = json.loads((stato_dir / "stato.json").read_text())
    voce = stato["coppie"]["DOT"]
    assert voce["status"] == "chiusura_fallita"
    assert voce["esiti"] == {"perp": "incerto", "spot": "non_tentato"}
    assert mock.cancel_calls != []                 # ordine vivo annullato
    assert [o["symbol"] for o in mock.ordini] == [SYM_PERP]  # zero spot
    assert mock.spot_qty == 8.0                    # spot intatto
    ev = leggi_eventi(stato_dir)
    ev_perp = [e for e in ev if e["evento"] == "chiusura_perp"][0]
    assert ev_perp["esito"] == "incerto"
    assert ev_perp["cl_ord_id"] == mock.ordini[0]["params"]["clOrdId"]
    assert "VERIFICA MANUALE" in capsys.readouterr().out


def test_f2_eccezione_ordine_vivo_spot_incerto_cancel_exit1(tmp_path, capsys):
    """create_order SPOT solleva ma l'ordine e' vivo: incerto, exit 1."""
    mock = MockClientP31(pos_ct=-8.0, pos_side="short", info_pos=-8.0,
                         spot_qty=8.0, fail_after_register={SYM_SPOT})
    stato_dir = tmp_path / "stato"
    rc = mod.esegui(mock, cfg(stato_dir=stato_dir), sleep_fn=noop_sleep)
    assert rc == 1
    stato = json.loads((stato_dir / "stato.json").read_text())
    voce = stato["coppie"]["DOT"]
    assert voce["status"] == "chiusura_fallita"
    assert voce["esiti"] == {"perp": "closed", "spot": "incerto"}
    assert mock.cancel_calls != []
    assert [o["symbol"] for o in mock.ordini] == [SYM_PERP, SYM_SPOT]
    assert "VERIFICA MANUALE" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# F3 (ALTA) — la gamba spot si decide con stato + funding/earn
# ---------------------------------------------------------------------------

def test_f3_spot_in_funding_rifiuto_exit2_zero_ordini(tmp_path, capsys):
    """stato qty_spot=90, trading 0, funding 90: la gamba e' in funding ->
    rifiuto exit 2 PRIMA di qualsiasi ordine (la perp non si tocca)."""
    mock = MockClientP31(pos_ct=-78.0, pos_side="short", info_pos=-78.0,
                         spot_qty=0.0, funding_qty=90.0)
    stato_dir = tmp_path / "stato"
    scrivi_stato(stato_dir, {"qty_spot": 90.0, "ct_perp": -78.0})
    rc = mod.esegui(mock, cfg(stato_dir=stato_dir), sleep_fn=noop_sleep)
    assert rc == 2
    assert mock.ordini == []
    out = capsys.readouterr().out
    assert "funding/earn" in out
    assert mock.pos_ct == -78.0                     # perp intatta


def test_f3_spot_atteso_sparito_exit2(tmp_path, capsys):
    """stato qty_spot=90 ma 0 ovunque (trading+funding+earn): exit 2."""
    mock = MockClientP31(pos_ct=-78.0, pos_side="short", info_pos=-78.0,
                         spot_qty=0.0, funding_qty=0.0, earn_qty=0.0)
    stato_dir = tmp_path / "stato"
    scrivi_stato(stato_dir, {"qty_spot": 90.0, "ct_perp": -78.0})
    rc = mod.esegui(mock, cfg(stato_dir=stato_dir), sleep_fn=noop_sleep)
    assert rc == 2
    assert mock.ordini == []
    assert "0 in trading+funding/earn" in capsys.readouterr().out


def test_f3_spot_assente_qty0_closed_con_nota(tmp_path, capsys):
    """stato qty_spot=0, tutto 0: closed MAI senza nota_chiudi esplicita."""
    mock = MockClientP31(pos_ct=-8.0, pos_side="short", info_pos=-8.0,
                         spot_qty=0.0)
    stato_dir = tmp_path / "stato"
    scrivi_stato(stato_dir, {"qty_spot": 0.0, "ct_perp": -8.0})
    rc = mod.esegui(mock, cfg(stato_dir=stato_dir), sleep_fn=noop_sleep)
    assert rc == 0
    stato = json.loads((stato_dir / "stato.json").read_text())
    voce = stato["coppie"]["DOT"]
    assert voce["status"] == "closed"
    assert voce["esiti"] == {"perp": "closed", "spot": "assente"}
    assert "gamba spot assente (qty attesa 0)" in voce["nota_chiudi"]


# ---------------------------------------------------------------------------
# F4 (MEDIA) — "perp assente" mai con una sola lettura
# ---------------------------------------------------------------------------

def test_f4_letture_discordanti_exit1_zero_ordini(tmp_path, capsys):
    """1a lettura in chiudi_perp vuota, 2a vede -78: discordanti -> exit 1,
    nessun ordine (lo spot NON viene venduto con lo short scoperto)."""
    mock = MockClientP31(pos_ct=-78.0, pos_side="short", info_pos=-78.0,
                         spot_qty=78.0,
                         pos_sequence=[-78.0, None, -78.0])
    stato_dir = tmp_path / "stato"
    scrivi_stato(stato_dir, {"qty_spot": 78.0, "ct_perp": -78.0})
    rc = mod.esegui(mock, cfg(stato_dir=stato_dir), sleep_fn=noop_sleep)
    assert rc == 1
    assert mock.ordini == []
    assert mock.spot_qty == 78.0
    assert "discordanti" in capsys.readouterr().out


def test_f4_due_letture_zero_stato_ct_nonzero_exit1(tmp_path, capsys):
    """2 letture a 0 ma stato ct_perp=-78: exit 1, zero ordini."""
    mock = MockClientP31(pos_ct=0.0, spot_qty=78.0,
                         pos_sequence=[None, None, None])
    stato_dir = tmp_path / "stato"
    scrivi_stato(stato_dir, {"qty_spot": 78.0, "ct_perp": -78.0})
    rc = mod.esegui(mock, cfg(stato_dir=stato_dir), sleep_fn=noop_sleep)
    assert rc == 1
    assert mock.ordini == []
    assert mock.spot_qty == 78.0
    assert "stato ct_perp" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# F5 (MEDIA) — qty spot = qty della coppia, non l'intero saldo
# ---------------------------------------------------------------------------

def test_f5_saldo_sopra_qty_stato_exit2(tmp_path, capsys):
    """saldo 190 vs qty_spot 90: rifiuto exit 2 (serve --qty esplicito)."""
    mock = MockClientP31(pos_ct=-78.0, pos_side="short", info_pos=-78.0,
                         spot_qty=190.0)
    stato_dir = tmp_path / "stato"
    scrivi_stato(stato_dir, {"qty_spot": 90.0, "ct_perp": -78.0})
    rc = mod.esegui(mock, cfg(stato_dir=stato_dir), sleep_fn=noop_sleep)
    assert rc == 2
    assert mock.ordini == []
    assert "supera la qty della coppia" in capsys.readouterr().out


def test_f5_saldo_entro_tolleranza_vende_saldo(tmp_path, capsys):
    """saldo 90.05 vs qty_spot 90 (entro tolleranza): vende 90.05."""
    mock = MockClientP31(pos_ct=-78.0, pos_side="short", info_pos=-78.0,
                         spot_qty=90.05)
    stato_dir = tmp_path / "stato"
    scrivi_stato(stato_dir, {"qty_spot": 90.0, "ct_perp": -78.0})
    rc = mod.esegui(mock, cfg(stato_dir=stato_dir), sleep_fn=noop_sleep)
    assert rc == 0
    spot_ordini = [o for o in mock.ordini if o["symbol"] == SYM_SPOT]
    assert len(spot_ordini) == 1
    assert abs(spot_ordini[0]["qty"] - 90.05) < 1e-9
    stato = json.loads((stato_dir / "stato.json").read_text())
    assert stato["coppie"]["DOT"]["status"] == "closed"


# ---------------------------------------------------------------------------
# F6 (MEDIA) — fill cumulato dopo reprice
# ---------------------------------------------------------------------------

def test_f6_fill_cumulato_reprice_spot(tmp_path, capsys):
    """Spot 8: 1o ordine fill 3 (cancel), reprice fill 5 -> filled=8,
    attesa 0, fee sommate, chiusura riconciliata alla prima lettura."""
    mock = MockClientP31(pos_ct=-8.0, pos_side="short", info_pos=-8.0,
                         spot_qty=8.0, partial_first_spot=3.0)
    stato_dir = tmp_path / "stato"
    rc = mod.esegui(mock, cfg(stato_dir=stato_dir), sleep_fn=noop_sleep)
    assert rc == 0
    spot_ordini = [o for o in mock.ordini if o["symbol"] == SYM_SPOT]
    assert [(o["qty"]) for o in spot_ordini] == [8.0, 5.0]
    stato = json.loads((stato_dir / "stato.json").read_text())
    voce = stato["coppie"]["DOT"]
    assert voce["status"] == "closed"
    # fee = somma di entrambi i fill (3+5) sulla gamba spot + perp 8
    assert abs(voce["fee"] - 0.16) < 0.01
    out = capsys.readouterr().out
    assert "RICONCILIAZIONE OK" in out
    assert "convergenza alla lettura 1" in out


def test_f6_fill_cumulato_reprice_perp(tmp_path, capsys):
    """Perp 8: 1o buy fill 3 (cancel), reprice fill 5 -> fee cumulate."""
    mock = MockClientP31(pos_ct=-8.0, pos_side="short", info_pos=-8.0,
                         spot_qty=8.0, partial_first_perp=3.0)
    stato_dir = tmp_path / "stato"
    rc = mod.esegui(mock, cfg(stato_dir=stato_dir), sleep_fn=noop_sleep)
    assert rc == 0
    perp_ordini = [o for o in mock.ordini if o["symbol"] == SYM_PERP]
    assert [o["qty"] for o in perp_ordini] == [8.0, 5.0]
    assert mock.pos_ct == 0.0
    stato = json.loads((stato_dir / "stato.json").read_text())
    voce = stato["coppie"]["DOT"]
    assert voce["status"] == "closed"
    assert abs(voce["fee"] - 0.16) < 0.01
    assert "RICONCILIAZIONE OK" in capsys.readouterr().out
