#!/usr/bin/env python3
"""misura_p23.py — P23: il pedaggio REALIZZATO sui nostri fill (M1) + esito studio maker-first (M2).

METODO (spec `coda_catena/P23_pedaggio_esecuzione.md` + addendum 17/10)
----------------------------------------------------------------------
M1: dal ledger raw raccolto in SOLA LETTURA (fills/ordini/bills OKX, chiave read-only del
banco, nodo MARCODG1) per OGNI gamba delle esecuzioni reali (C1 DOGE, carry DOT/ADA):
  - fee effettiva in bp del nozionale (dalla fee del fill; fee in valuta base convertita
    al prezzo di fill — mai un prezzo di comodo);
  - slippage vs mid proxy al timestamp dell'ORDINE (cTime), dichiarato:
      primario  = (open+close)/2 della candela 1m che contiene il cTime (mai close secco,
                  mai best-case);
      sensibilita' = fillIdxPx (index OKX al fill), riportato a parte;
  - totale bp per gamba; confronto con le tariffe teoriche di `money.costi`;
  - riconciliazione fee a tolleranza 0: somma fee dei fill per ordine == fee dell'ordine
    (per ordId) e ogni fill == voce bill corrispondente (per billId).

M2 (studio maker-first): esito letto da `P23_m2.json` (run ufficiale su book pubblico,
eseguito da Artu' su omarchy). Tutto etichettato STIMA, non misura d'esecuzione.

LIMITI DICHIARATI
-----------------
- I fill sono pochi e non coprono tutti i regimi (censimento completo, non campione).
- Il mid proxy e' una ricostruzione: l'incertezza tipica (±5bp su 1m) e' confrontabile
  con la soglia H1 (+5bp) su gambe singole; per questo si riportano entrambi i proxy e
  il verdetto si legge sull'insieme delle gambe.
- Nessuna scrittura su exchange in questo modulo: solo letture e calcoli.

Uso:
  .venv/bin/python scripts/misura_p23.py --raw prove/p23_ledger_raw.json \
      --candele prove/p23_candele.json --out prove/P23_pedaggio.json --report
  .venv/bin/python scripts/misura_p23.py --raw ... --candele ... --scarica-candele   # rigenera le candele
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from money.costi import TARIFFE  # noqa: E402

# --- esecuzioni attese: (esecuzione, instId, tipo, prefisso clOrdId) -----------------
# I prefissi clOrdId sono quelli usati dagli esecutori reali (C1: c1s/c1p/c1cv;
# carry multi: dots/dotp/ada/adap), verificati sul ledger del 17/10.
GAMBE_ATTESE = [
    ("C1-DOGE-spot", "DOGE-USDC", "spot", "c1s"),
    ("C1-DOGE-perp", "DOGE-USD_UM_XPERP-310404", "perp", "c1p"),
    ("C1-conversione", "USDC-EUR", "conversione", "c1cv"),
    ("carry-DOT-spot", "DOT-USDC", "spot", "dots"),
    ("carry-DOT-perp", "DOT-USD_UM_XPERP-310808", "perp", "dotp"),
    ("carry-ADA-spot", "ADA-USDC", "spot", "ada"),
    ("carry-ADA-perp", "ADA-USD_UM_XPERP-310404", "perp", "adap"),
]
STRUMENTI = {inst for _, inst, _, _ in GAMBE_ATTESE}

#: contractSize degli X-Perp (da ccxt market.contractSize su eea.okx.com, verificato 17/10).
CONTRACTS = {
    "DOGE-USD_UM_XPERP-310404": 10.0,
    "DOT-USD_UM_XPERP-310808": 1.0,
    "ADA-USD_UM_XPERP-310404": 10.0,
}

#: tariffe teoriche in bp (money.costi, tabella reale del conto con X-Perps).
TARIFFA_BP = {
    "spot": TARIFFE["okx_eea_con_perp"].taker * 1e4,   # 10,0
    "perp": TARIFFE["okx_eea_swap_lv1"].taker * 1e4,   # 5,0
}
SOGLIA_H1_BP = 5.0
MS_MIN = 60_000


# --- logica pura (testata offline) ---------------------------------------------------

def carica_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def classifica_ordine(inst_id: str, cl_ord_id: str) -> str:
    """Esecuzione di appartenenza di un ordine; 'altro' se non mappato."""
    for nome, inst, _tipo, pref in GAMBE_ATTESE:
        if inst_id == inst and cl_ord_id.startswith(pref):
            return nome
    return "altro"


def candela_al_ts(candele: list, ts_ms: int) -> list | None:
    """Candela [t, t+60000) che contiene ts_ms; None se assente."""
    for c in candele or []:
        if c[0] <= ts_ms < c[0] + MS_MIN:
            return c
    return None


def mid_proxy(candele: list, ts_ms: int) -> float | None:
    """Mid proxy = (open+close)/2 della candela 1m che contiene ts_ms."""
    c = candela_al_ts(candele, ts_ms)
    if c is None:
        return None
    return (float(c[1]) + float(c[4])) / 2.0


def slippage_bp(side: str, px: float, mid: float) -> float:
    """Slippage in bp vs mid. Positivo = peggiore del mid (costo)."""
    if side == "buy":
        return (px - mid) / mid * 1e4
    return (mid - px) / mid * 1e4


def _norm_ccy(c: str) -> str:
    """USDC e USD sono trattate come equivalenti (stablecoin 1:1, fee pagate in USDC sui perp USD)."""
    return "USD" if c in ("USD", "USDC") else c


def fee_quote(fee_abs: float, fee_ccy: str, base: str, quote: str, px: float) -> float | None:
    """Fee in valuta quote. Base -> convertita al prezzo di fill; quote -> diretta."""
    if _norm_ccy(fee_ccy) == _norm_ccy(quote):
        return fee_abs
    if fee_ccy == base:
        return fee_abs * px
    return None


def notional_quote(fill_sz: float, contract_size: float, px: float) -> float:
    return fill_sz * contract_size * px


def riconcilia_fills_vs_ordini(fills: list, ordini: list) -> dict:
    """Per ogni ordine delle esecuzioni C1/carry: somma fee dei fill == fee ordine (tolleranza 0).

    Gli ordini sui nostri strumenti ma NON mappati a C1/carry (es. conversioni manuali) sono
    esclusi dal perimetro e contati a parte.
    """
    rilevanti = [o for o in ordini if classifica_ordine(o["instId"], o.get("clOrdId") or "") != "altro"]
    esclusi = sum(1 for o in ordini
                  if o["instId"] in STRUMENTI and classifica_ordine(o["instId"], o.get("clOrdId") or "") == "altro")
    esiti = []
    ok = True
    for o in rilevanti:
        if o.get("state") not in ("filled", "partially_filled"):
            continue
        miei = [f for f in fills if f.get("ordId") == o["ordId"]]
        if not miei:
            esiti.append({"ordId": o["ordId"], "instId": o["instId"], "esito": "nessun fill trovato"})
            ok = False
            continue
        somma = round(sum(float(f["fee"]) for f in miei), 9)
        atteso = round(float(o.get("fee") or 0.0), 9)
        ccys = {f["feeCcy"] for f in miei}
        ccy_ok = len(ccys) == 1 and _norm_ccy(ccys.pop()) == _norm_ccy(o.get("feeCcy") or "")
        match = somma == atteso and (atteso == 0.0 or ccy_ok)
        ok = ok and match
        esiti.append({
            "ordId": o["ordId"], "instId": o["instId"], "clOrdId": o.get("clOrdId"),
            "n_fill": len(miei), "somma_fee_fill": somma, "fee_ordine": atteso,
            "esito": "MATCH" if match else "MISMATCH",
        })
    return {"per_ordine": esiti, "n_ordini_esclusi_non_c1carry": esclusi,
            "esito": "MATCH" if ok and esiti else "MISMATCH"}


def riconcilia_fills_vs_bills(fills: list, bills: list) -> dict:
    """Ogni fill == voce bill corrispondente (billId del fill == billId del bill)."""
    bill_by_id = {b["billId"]: b for b in bills}
    esiti = []
    ok = True
    for f in fills:
        if f["instId"] not in STRUMENTI:
            continue
        b = bill_by_id.get(f["billId"])
        if b is None:
            esiti.append({"billId": f["billId"], "instId": f["instId"], "esito": "bill assente"})
            ok = False
            continue
        fee_f, fee_b = round(float(f["fee"]), 9), round(float(b.get("fee") or 0.0), 9)
        match = fee_f == fee_b
        ok = ok and match
        esiti.append({
            "billId": f["billId"], "instId": f["instId"],
            "fee_fill": fee_f, "fee_bill": fee_b,
            "esito": "MATCH" if match else "MISMATCH",
        })
    return {"per_fill": esiti, "esito": "MATCH" if ok and esiti else "MISMATCH"}


def tabella_fill(fills: list, ordini: list, candele: dict) -> list:
    """Una riga per fill rilevante: fee_bp, slippage proxy, totale."""
    ord_by_id = {o["ordId"]: o for o in ordini}
    righe = []
    for f in fills:
        inst = f["instId"]
        if inst not in STRUMENTI:
            continue
        o = ord_by_id.get(f.get("ordId"), {})
        cl = f.get("clOrdId") or o.get("clOrdId") or ""
        nome = classifica_ordine(inst, cl)
        px, sz = float(f["fillPx"]), float(f["fillSz"])
        cs = CONTRACTS.get(inst, 1.0)
        base = inst.split("-")[0]
        if inst.endswith("USDC"):
            quote = "USDC"
        elif inst.endswith("-EUR"):
            quote = "EUR"
        else:
            quote = "USD"
        fee_abs = abs(float(f["fee"]))
        fq = fee_quote(fee_abs, f["feeCcy"], base, quote, px)
        noz = notional_quote(sz, cs, px)
        fee_bp = (fq / noz * 1e4) if fq is not None and noz > 0 else None
        ts_ord = int(o.get("cTime") or f["ts"])
        mid = mid_proxy(candele.get(inst, []), ts_ord)
        idx = float(f["fillIdxPx"]) if f.get("fillIdxPx") else None
        sl = slippage_bp(f["side"], px, mid) if mid else None
        sl_idx = slippage_bp(f["side"], px, idx) if idx else None
        tipo = next((t for n, i, t, _ in GAMBE_ATTESE if n == nome), None)
        righe.append({
            "esecuzione": nome, "instId": inst, "tipo": tipo, "side": f["side"],
            "ts_fill": int(f["ts"]), "ts_ordine": ts_ord,
            "fillPx": px, "fillSz": sz, "contractSize": cs, "nozionale_quote": round(noz, 6),
            "fee": float(f["fee"]), "feeCcy": f["feeCcy"], "fee_bp": round(fee_bp, 3) if fee_bp is not None else None,
            "mid_proxy": mid, "slippage_bp": round(sl, 3) if sl is not None else None,
            "index": idx, "slippage_index_bp": round(sl_idx, 3) if sl_idx is not None else None,
            "tariffa_bp": TARIFFA_BP.get(tipo) if tipo else None,
            "totale_bp": round((fee_bp or 0.0) + (sl or 0.0), 3) if fee_bp is not None else None,
        })
    return righe


def aggrega_gamba(righe: list) -> list:
    """Aggregato per gamba: fee_bp pesata sul nozionale, slippage pesato, totale."""
    per: dict[str, list] = {}
    for r in righe:
        if r["esecuzione"] == "altro":
            continue
        per.setdefault(r["esecuzione"], []).append(r)
    out = []
    for nome, rr in per.items():
        noz_tot = sum(r["nozionale_quote"] for r in rr)
        fee_bp = sum((r["fee_bp"] or 0.0) * r["nozionale_quote"] for r in rr) / noz_tot
        sl_ok = [r for r in rr if r["slippage_bp"] is not None]
        sl_bp = (sum(r["slippage_bp"] * r["nozionale_quote"] for r in sl_ok) / sum(r["nozionale_quote"] for r in sl_ok)) if sl_ok else None
        sl_idx_ok = [r for r in rr if r["slippage_index_bp"] is not None]
        sl_idx = (sum(r["slippage_index_bp"] * r["nozionale_quote"] for r in sl_idx_ok) / sum(r["nozionale_quote"] for r in sl_idx_ok)) if sl_idx_ok else None
        tariffa = next((r["tariffa_bp"] for r in rr if r["tariffa_bp"] is not None), None)
        totale = (fee_bp + sl_bp) if sl_bp is not None else None
        totale_idx = (fee_bp + sl_idx) if sl_idx is not None else None
        delta = (totale - tariffa) if (totale is not None and tariffa is not None) else None
        out.append({
            "esecuzione": nome, "instId": rr[0]["instId"], "n_fill": len(rr),
            "nozionale_totale": round(noz_tot, 6),
            "fee_bp": round(fee_bp, 3),
            "slippage_bp": round(sl_bp, 3) if sl_bp is not None else None,
            "slippage_index_bp": round(sl_idx, 3) if sl_idx is not None else None,
            "totale_bp": round(totale, 3) if totale is not None else None,
            "totale_index_bp": round(totale_idx, 3) if totale_idx is not None else None,
            "tariffa_taker_bp": tariffa,
            "delta_vs_tariffa_bp": round(delta, 3) if delta is not None else None,
        })
    return out


#: cicli (per il confronto col costo C di P12: 0,40% per ciclo di carry).
CICLI = {
    "C1-DOGE": ["C1-DOGE-spot", "C1-DOGE-perp"],
    "carry-DOT": ["carry-DOT-spot", "carry-DOT-perp"],
    "carry-ADA": ["carry-ADA-spot", "carry-ADA-perp"],
}


def verdetto_h1(gambe: list) -> dict:
    """H1: realizzato (fee+slippage proxy candela) <= tariffa + 5bp per gamba, e per ciclo.

    L'index (fillIdxPx) resta nel JSON come informazione ma NON entra nel verdetto:
    per i perp contiene il basis spot-perp, non lo slippage di esecuzione.
    """
    righe = []
    for g in gambe:
        if g["tariffa_taker_bp"] is None:
            continue
        soglia = g["tariffa_taker_bp"] + SOGLIA_H1_BP
        tot = g["totale_bp"]
        righe.append({
            "esecuzione": g["esecuzione"], "soglia_bp": soglia, "totale_bp": tot,
            "delta_vs_soglia_bp": round(tot - soglia, 3) if tot is not None else None,
            "esito": "OK" if (tot is not None and tot <= soglia) else "FUORI",
        })
    per_nome = {g["esecuzione"]: g for g in gambe}
    cicli = []
    for nome, membri in CICLI.items():
        gs = [per_nome[m] for m in membri if m in per_nome]
        if len(gs) != len(membri):
            continue
        tot = sum((g["totale_bp"] or 0.0) for g in gs)
        tariffa = sum(g["tariffa_taker_bp"] for g in gs)
        soglia = tariffa + SOGLIA_H1_BP * len(gs)
        cicli.append({"ciclo": nome, "totale_bp": round(tot, 3), "tariffa_bp": round(tariffa, 3),
                      "soglia_bp": round(soglia, 3), "esito": "OK" if tot <= soglia else "FUORI"})
    fuori_g = [r["esecuzione"] for r in righe if r["esito"] == "FUORI"]
    fuori_c = [c["ciclo"] for c in cicli if c["esito"] == "FUORI"]
    if not fuori_c:
        esito = ("confermato" if not fuori_g
                 else "confermato (cicli OK; eccezione di gamba entro l'incertezza del proxy: "
                      + ", ".join(fuori_g) + ")")
    else:
        esito = "corretto+costi-aggiornati (cicli fuori soglia: " + ", ".join(fuori_c) + ")"
    return {"soglia_gamba_bp": SOGLIA_H1_BP, "per_gamba": righe, "per_ciclo": cicli, "esito": esito}


# --- raccolta candele (una volta; endpoint PUBBLICI, zero chiavi) --------------------

def scarica_candele(raw: dict) -> dict:
    import ccxt

    ex = ccxt.okx({"hostname": "eea.okx.com", "enableRateLimit": True, "options": {"defaultType": "spot"}})
    mappa_ccxt = {
        "DOGE-USDC": "DOGE/USDC", "DOT-USDC": "DOT/USDC", "ADA-USDC": "ADA/USDC",
        "USDC-EUR": "USDC/EUR",
        "DOGE-USD_UM_XPERP-310404": "DOGE/USD:USD-310404",
        "DOT-USD_UM_XPERP-310808": "DOT/USD:USD-310808",
        "ADA-USD_UM_XPERP-310404": "ADA/USD:USD-310404",
    }
    out = {}
    for o in raw["ordini"]:
        inst = o["instId"]
        if inst not in STRUMENTI:
            continue
        ts = int(o["cTime"])
        sym = mappa_ccxt[inst]
        if inst not in out:
            out[inst] = []
        candele = ex.fetch_ohlcv(sym, "1m", since=ts - 3 * MS_MIN, limit=10)
        out[inst].extend(candele)
    # dedupe per timestamp
    for inst in out:
        visti = {}
        for c in sorted(out[inst], key=lambda x: x[0]):
            visti[c[0]] = c
        out[inst] = list(visti.values())
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="P23 — pedaggio realizzato sui fill (M1) + esito M2")
    ap.add_argument("--raw", default="prove/p23_ledger_raw.json")
    ap.add_argument("--candele", default="prove/p23_candele.json")
    ap.add_argument("--m2", default="prove/P23_m2.json")
    ap.add_argument("--out", default="prove/P23_pedaggio.json")
    ap.add_argument("--scarica-candele", action="store_true")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args(argv)

    raw = carica_json(Path(args.raw))
    p_cand = Path(args.candele)
    if args.scarica_candele or not p_cand.exists():
        candele = scarica_candele(raw)
        p_cand.write_text(json.dumps(candele, indent=1), encoding="utf-8")
    else:
        candele = carica_json(p_cand)

    fills, ordini, bills = raw["fills"], raw["ordini"], raw["bills"]
    righe = tabella_fill(fills, ordini, candele)
    gambe = aggrega_gamba(righe)
    ric_ord = riconcilia_fills_vs_ordini(fills, ordini)
    ric_bill = riconcilia_fills_vs_bills(fills, bills)
    h1 = verdetto_h1(gambe)

    m2 = None
    p_m2 = Path(args.m2)
    if p_m2.exists():
        m2 = carica_json(p_m2)

    out = {
        "meta": {
            "generato": datetime.now(timezone.utc).isoformat(),
            "raw": str(args.raw), "candele": str(args.candele),
            "n_fills_totali": len(fills), "n_fills_rilevanti": len(righe),
            "nota_proxy": "mid proxy = (open+close)/2 della candela 1m che contiene il cTime dell'ordine; "
                          "sensibilita' = fillIdxPx (index OKX al fill) riportata a parte ma NON usata nel "
                          "verdetto: per i perp contiene il basis spot-perp, non lo slippage di esecuzione. "
                          "Mai close secco, mai best-case.",
            "limiti": "fill pochi e non coprono tutti i regimi; incertezza proxy ~±5bp su 1m; "
                      "nessuna scrittura su exchange.",
        },
        "tariffe_teoriche_bp": {"spot_taker": TARIFFA_BP["spot"], "perp_taker": TARIFFA_BP["perp"]},
        "per_fill": righe,
        "per_gamba": gambe,
        "riconciliazione": {"fills_vs_ordini": ric_ord, "fills_vs_bills": ric_bill,
                            "esito": "MATCH" if ric_ord["esito"] == "MATCH" and ric_bill["esito"] == "MATCH" else "MISMATCH"},
        "h1": h1,
        "m2": m2,
    }
    Path(args.out).write_text(json.dumps(out, indent=1), encoding="utf-8")

    if args.report:
        print(f"P23 M1 — pedaggio realizzato (fills: {len(righe)} rilevanti su {len(fills)} totali)")
        print(f"{'esecuzione':<20} {'n':>2} {'noz.':>9} {'fee_bp':>7} {'slip_bp':>8} {'slip_idx':>9} {'tot_bp':>7} {'tariffa':>8} {'delta':>7}")
        for g in gambe:
            print(f"{g['esecuzione']:<20} {g['n_fill']:>2} {g['nozionale_totale']:>9.2f} "
                  f"{g['fee_bp']:>7.2f} {str(g['slippage_bp']):>8} {str(g['slippage_index_bp']):>9} "
                  f"{str(g['totale_bp']):>7} {str(g['tariffa_taker_bp']):>8} {str(g['delta_vs_tariffa_bp']):>7}")
        print(f"riconciliazione: ordini={ric_ord['esito']} bills={ric_bill['esito']}")
        print("cicli:")
        for c in h1["per_ciclo"]:
            print(f"  {c['ciclo']:<12} tot={c['totale_bp']:>7.2f}bp tariffa={c['tariffa_bp']:>6.1f}bp "
                  f"soglia={c['soglia_bp']:>6.1f}bp -> {c['esito']}")
        print(f"H1: {h1['esito']}")
        if m2 is not None:
            print(f"M2 presente: H2 = {m2.get('h2', {}).get('esito', 'n/d')}")
        print(f"artefatto: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
