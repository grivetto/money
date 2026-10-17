"""Test di scripts/misura_p23.py — P23 M1 (pedaggio realizzato sui fill).

Tutto offline: fixture sintetiche con numeri calcolati a mano; nessuna rete, nessuna chiave.
Verifica: segni dello slippage, fee in valuta base vs quote (USDC≡USD), notional con ctVal,
classificazione ordini, riconciliazione a tolleranza 0 (match e mismatch), aggregazione e
verdetto H1 (gamba + ciclo), e la guardia statica "zero percorsi di scrittura".
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import misura_p23 as m23  # noqa: E402


# --- logica pura ----------------------------------------------------------------------

def test_slippage_segni():
    # buy sopra il mid = costo (positivo); buy sotto = beneficio (negativo)
    assert m23.slippage_bp("buy", 101.0, 100.0) == 100.0
    assert m23.slippage_bp("buy", 99.0, 100.0) == -100.0
    # sell sotto il mid = costo; sell sopra = beneficio
    assert m23.slippage_bp("sell", 99.0, 100.0) == 100.0
    assert m23.slippage_bp("sell", 101.0, 100.0) == -100.0


def test_mid_proxy_candela_giusta():
    candele = [
        [1_000_000, 10.0, 11.0, 9.0, 10.5, 1.0],      # [1.000.000, 1.060.000)
        [1_060_000, 10.5, 12.0, 10.0, 11.5, 1.0],     # [1.060.000, 1.120.000)
    ]
    assert m23.mid_proxy(candele, 1_030_000) == 10.25
    assert m23.mid_proxy(candele, 1_090_000) == 11.0
    assert m23.mid_proxy(candele, 999_999) is None
    assert m23.mid_proxy(candele, 1_120_000) is None


def test_fee_quote_base_quote_equivalenze():
    # fee in valuta base -> convertita al prezzo di fill
    assert m23.fee_quote(0.5, "DOT", "DOT", "USDC", 2.0) == 1.0
    # fee in quote -> diretta
    assert m23.fee_quote(0.25, "USDC", "ADA", "USD", 0.23) == 0.25
    # USDC su mercato USD (perp) -> equivalente
    assert m23.fee_quote(0.25, "USDC", "ADA", "USD", 0.23) == 0.25
    # valuta sconosciuta -> None
    assert m23.fee_quote(0.25, "BTC", "ADA", "USD", 0.23) is None


def test_notional_quote_con_ctval():
    # 39 ct ADA X-Perp (ctVal 10) a 0.23 -> 89.7 USD
    assert round(m23.notional_quote(39.0, 10.0, 0.23), 6) == 89.7
    # spot: ctVal 1
    assert m23.notional_quote(110.0, 1.0, 0.09473) == 110.0 * 0.09473


def test_classifica_ordine():
    assert m23.classifica_ordine("DOGE-USDC", "c1s1790808201") == "C1-DOGE-spot"
    assert m23.classifica_ordine("DOGE-USD_UM_XPERP-310404", "c1p1790808205") == "C1-DOGE-perp"
    assert m23.classifica_ordine("DOT-USD_UM_XPERP-310808", "dotp9ac0b6") == "carry-DOT-perp"
    assert m23.classifica_ordine("ADA-USDC", "adas348bf") == "carry-ADA-spot"
    assert m23.classifica_ordine("DOT-USDC", "xyz123") == "altro"
    assert m23.classifica_ordine("SOL-EUR", "c1s...") == "altro"


# --- riconciliazione ------------------------------------------------------------------

def _fill(ord_id="o1", bill_id="b1", inst="DOT-USDC", fee="-0.0628125", ccy="DOT",
          px="1.154", sz="62.8125", side="buy", ts="1792105199351", idx="1.1540"):
    return {"ordId": ord_id, "billId": bill_id, "instId": inst, "fee": fee, "feeCcy": ccy,
            "fillPx": px, "fillSz": sz, "side": side, "ts": ts, "fillIdxPx": idx,
            "clOrdId": "dots68ea60d79c9854050397"}


def _ordine(ord_id="o1", inst="DOT-USDC", fee="-0.078", ccy="DOT", state="filled",
            cl="dots68ea60d79c9854050397", px="1.1562", sz="78", ctime="1792105199351"):
    return {"ordId": ord_id, "instId": inst, "fee": fee, "feeCcy": ccy, "state": state,
            "clOrdId": cl, "px": px, "sz": sz, "cTime": ctime, "side": "buy"}


def test_riconciliazione_ordini_match_esatto():
    fills = [_fill(bill_id="b1", fee="-0.0628125", sz="62.8125"),
             _fill(bill_id="b2", fee="-0.0151875", sz="15.1875", px="1.1539")]
    out = m23.riconcilia_fills_vs_ordini(fills, [_ordine()])
    assert out["esito"] == "MATCH"
    assert out["per_ordine"][0]["n_fill"] == 2
    assert out["per_ordine"][0]["somma_fee_fill"] == -0.078


def test_riconciliazione_ordini_mismatch():
    fills = [_fill(fee="-0.0628125"), _fill(bill_id="b2", fee="-0.0151875")]
    out = m23.riconcilia_fills_vs_ordini(fills, [_ordine(fee="-0.09")])
    assert out["esito"] == "MISMATCH"


def test_riconciliazione_ordini_fee_zero_ccy_diverse():
    # conversione: fill fee 0 in EUR, ordine fee 0 in USDC -> MATCH (0 == 0)
    fills = [_fill(inst="USDC-EUR", fee="0", ccy="EUR", px="0.88252", sz="13")]
    fills[0]["clOrdId"] = "c1cv1790808186"
    o = _ordine(inst="USDC-EUR", fee="0", ccy="USDC", cl="c1cv1790808186")
    out = m23.riconcilia_fills_vs_ordini(fills, [o])
    assert out["esito"] == "MATCH"


def test_riconciliazione_ordini_esclude_non_c1carry():
    o = _ordine(inst="USDC-EUR", cl="conv1791668804", fee="0", ccy="USDC")
    out = m23.riconcilia_fills_vs_ordini([], [o])
    assert out["n_ordini_esclusi_non_c1carry"] == 1
    assert out["per_ordine"] == []


def test_riconciliazione_bills_per_billid():
    fills = [_fill(bill_id="b1", fee="-0.11", ccy="DOGE", inst="DOGE-USDC")]
    bills = [{"billId": "b1", "fee": "-0.11"}]
    out = m23.riconcilia_fills_vs_bills(fills, bills)
    assert out["esito"] == "MATCH"
    # bill assente -> MISMATCH
    out2 = m23.riconcilia_fills_vs_bills(fills, [])
    assert out2["esito"] == "MISMATCH"


# --- end-to-end su fixture sintetica --------------------------------------------------

def test_tabella_e_aggregato_end_to_end():
    # gamba spot: buy 100 DOT @ 1.10, fee 0.10 DOT (=10bp), mid proxy 1.10 -> fee 10bp, slip 0
    fills = [_fill(ord_id="o1", bill_id="b1", inst="DOT-USDC", fee="-0.10", ccy="DOT",
                   px="1.10", sz="100", ts="1000000", idx="1.10")]
    ordini = [_ordine(ord_id="o1", inst="DOT-USDC", fee="-0.10", ccy="DOT", ctime="1000000")]
    candele = {"DOT-USDC": [[1_000_000, 1.10, 1.10, 1.10, 1.10, 1.0]]}
    righe = m23.tabella_fill(fills, ordini, candele)
    assert len(righe) == 1
    assert righe[0]["esecuzione"] == "carry-DOT-spot"
    assert round(righe[0]["fee_bp"], 3) == 10.0
    assert round(righe[0]["slippage_bp"], 3) == 0.0
    assert round(righe[0]["totale_bp"], 3) == 10.0
    gambe = m23.aggrega_gamba(righe)
    assert len(gambe) == 1
    assert gambe[0]["tariffa_taker_bp"] == 10.0
    assert round(gambe[0]["delta_vs_tariffa_bp"], 3) == 0.0


def test_verdetto_h1_gamba_fuori_ma_ciclo_ok():
    # due gambe del ciclo carry-DOT: spot a 18bp (fuori: soglia 15), perp a 2bp (ok: soglia 10)
    gambe = [
        {"esecuzione": "carry-DOT-spot", "tariffa_taker_bp": 10.0, "totale_bp": 18.0},
        {"esecuzione": "carry-DOT-perp", "tariffa_taker_bp": 5.0, "totale_bp": 2.0},
    ]
    h1 = m23.verdetto_h1(gambe)
    assert h1["per_gamba"][0]["esito"] == "FUORI"
    assert h1["per_ciclo"][0]["esito"] == "OK"       # 20 <= 15 + 10
    assert h1["esito"].startswith("confermato")


def test_verdetto_h1_ciclo_fuori():
    gambe = [
        {"esecuzione": "carry-ADA-spot", "tariffa_taker_bp": 10.0, "totale_bp": 30.0},
        {"esecuzione": "carry-ADA-perp", "tariffa_taker_bp": 5.0, "totale_bp": 30.0},
    ]
    h1 = m23.verdetto_h1(gambe)
    assert h1["per_ciclo"][0]["esito"] == "FUORI"    # 60 > 25
    assert h1["esito"].startswith("corretto+costi-aggiornati")


def test_verdetto_h1_salta_conversione():
    gambe = [{"esecuzione": "C1-conversione", "tariffa_taker_bp": None, "totale_bp": 0.0}]
    h1 = m23.verdetto_h1(gambe)
    assert h1["per_gamba"] == []
    assert h1["esito"] == "confermato"


# --- guardia statica ------------------------------------------------------------------

def test_nessun_percorso_di_scrittura_nel_sorgente():
    src = (Path(__file__).resolve().parents[1] / "scripts" / "misura_p23.py").read_text(encoding="utf-8")
    for vietato in ("create_order", "createOrder", "cancel_order", "cancelOrder",
                    "private_post", "privatePost", "withdraw", "transfer",
                    "set_leverage", "setLeverage"):
        assert vietato not in src, f"percorso di scrittura trovato: {vietato}"
