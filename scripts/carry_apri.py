#!/usr/bin/env python3
"""carry_apri.py — apertura REALE di una coppia carry (fase 2 di docs/20).

Riusa la meccanica VALIDATA di `canary/canary_carry.py` (C1, review 2026-10-15 PASS):
preflight -> gate pre-trade con stop ATR -> gamba spot (LIMIT) -> gamba perp (LIMIT,
short 1x isolated) -> riconciliazione delta -> journal.

DIFFERENZE rispetto a C1 (dichiarate):
  - coppia parametrica (--coppia DOT|DOGE|ADA|LINK), non hardcoded;
  - stato/eventi SEPARATI in data/carry_multi/: non tocca i file di C1;
  - riusa `money.esecuzione.invio` (unico punto di invio) e
    `money.esecuzione.cancello` (gate con stop ATR obbligatorio).

Sicurezze (identiche a C1): chiavi mai stampate; LIMIT (mai market); clOrdId
idempotenti; un solo reprice; fill parziale gestito; kill switch a file.

Uso:
  .venv/bin/python3 scripts/carry_apri.py --coppia DOT            # dry-run (default)
  .venv/bin/python3 scripts/carry_apri.py --coppia DOT --execute  # ESEGUE
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import ccxt

ROOT = Path("/home/marco/money")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from money.esecuzione.cancello import gate_pre_trade  # noqa: E402
from money.esecuzione.cancello_carry import gate_carry  # noqa: E402
from money.esecuzione.invio import Gamba, invia_gamba  # noqa: E402
from money.rischio import stop_da_atr  # noqa: E402
from scripts.carry_multi import COPPIE, leggi_env, ENV_FILE, DIR_STATO, KILL  # noqa: E402

LEVER = "1"
MGN = "isolated"
AGG_EQUITY_URL = "http://127.0.0.1:8912/api/infra.json"
#: Costo di ciclo del carry (frazione): fee spot 2x + fee perp 2x + spread 2x.
#: Numeri dal conto reale (16/10): spot taker 0,10% (USDC), perp maker 0,02%,
#: spread misurato 0,037-0,069%. Conservativo: 0,34%.
COSTO_CICLO = 0.0034


def funding_atteso(ex, inst_perp: str, periodi: int = 3) -> float:
    """Media robusta del funding recente (min dei tre valori piu' alti).

    Regola MOSAICO-4 §3.1: mai l'ultimo valore osservato. La media robusta
    evita di aprire su un picco isolato che il ciclo successivo non conferma.
    Ritorna la frazione per periodo (es. 0.0001 = 0,01%/8h).
    """
    try:
        r = ex.publicGetPublicFundingRate({"instId": inst_perp})
        storico = ex.publicGetPublicFundingRateHistory({"instId": inst_perp, "limit": "12"})
        valori = []
        for d in (storico.get("data") or [])[:periodi]:
            valori.append(abs(float(d.get("fundingRate") or 0)))
        if valori:
            return min(valori)          # il piu' prudente dei recenti
        d = (r.get("data") or [{}])[0]
        return float(d.get("fundingRate") or 0)
    except Exception:  # noqa: BLE001
        return 0.0


def ora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def cid_stabile(prefisso: str, intento: str) -> str:
    """clOrdId deterministico per intento: un retry riusa lo stesso id (idempotenza)."""
    h = hashlib.sha1(f"{prefisso}|{intento}".encode()).hexdigest()[:20]
    return f"{prefisso}{h}"[:32]


def evento(tipo: str, **kw) -> None:
    DIR_STATO.mkdir(parents=True, exist_ok=True)
    with (DIR_STATO / "eventi.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": ora(), "evento": tipo, **kw}) + "\n")


def client():
    e = leggi_env(ENV_FILE)
    return ccxt.okx({"apiKey": e["OKX_API_KEY"], "secret": e["OKX_API_SECRET"],
                     "password": e["OKX_PASSPHRASE"], "hostname": "eea.okx.com",
                     "enableRateLimit": True, "options": {"defaultType": "spot"}})


def equity_progetto() -> float:
    """Equity riconciliata dall'aggregatore (stessa fonte di dashboard/Zabbix)."""
    import urllib.request
    try:
        with urllib.request.urlopen(AGG_EQUITY_URL, timeout=8) as r:
            d = json.loads(r.read())
        c = d.get("canary") or {}
        return float(c.get("equity") or 0) or float(
            sum((b.get("total_equity") or 0) for b in (d.get("bots") or {}).values()))
    except Exception:
        return 0.0


def atr_ultimo(ex, symbol: str, n: int = 14, timeframe: str = "1d") -> float:
    """ATR semplice dalle barre giornaliere (stessa definizione di C1)."""
    o = ex.fetch_ohlcv(symbol, timeframe, limit=n + 1)
    ranges = [(h - l) for (_ts, _o, h, l, _c, _v) in o[-(n + 1):]]
    return sum(ranges[-n:]) / n if len(ranges) >= n else 0.0


def attesa_fill(ex, oid: str, sym: str, secondi: int = 60, passo: float = 1.5):
    """Attende il fill di un ordine (LIMIT). Ritorna (ordine, esito)."""
    t0 = time.time()
    while time.time() - t0 < secondi:
        try:
            o = ex.fetch_order(oid, sym)
        except Exception:
            time.sleep(passo)
            continue
        st = o.get("status")
        if st == "closed":
            return o, "closed"
        if st == "canceled":
            return o, "canceled"
        time.sleep(passo)
    return ex.fetch_order(oid, sym), "timeout"


def main() -> int:
    ap = argparse.ArgumentParser(description="Apri una coppia carry (OKX EEA)")
    ap.add_argument("--coppia", required=True)
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    nome = args.coppia.upper()
    if nome not in COPPIE:
        print(f"coppia ignota: {nome}. Disponibili: {list(COPPIE)}")
        return 1
    c = COPPIE[nome]

    if KILL.exists():
        print(f"KILL SWITCH attivo ({KILL}): nessuna apertura.")
        return 1

    ex = client()
    print(f"=== APRI {nome} {'[EXECUTE]' if args.execute else '[DRY-RUN]'} ===")
    print(f"spot {c.sym_spot} + perp {c.sym_perp} short {LEVER}x {MGN}")

    # ── PREFLIGHT ──
    oo = ex.fetch_open_orders()
    posizioni = [p for p in ex.fetch_positions([c.sym_perp])
                 if abs(float(p.get("contracts") or 0)) > 0]
    print(f"preflight: {len(oo)} ordini aperti, {len(posizioni)} posizioni su {c.sym_perp}")
    if oo:
        print("  ATTENZIONE: ordini aperti residui — preflight NON pulito")
    if posizioni:
        print(f"  ATTENZIONE: posizione gia' aperta su {c.sym_perp} — non si apre una seconda")
        return 1

    px = ex.fetch_ticker(c.sym_spot)["last"]
    n_ct = c.n_contratti(px)
    qty_spot = c.qty_spot(px)
    noz = qty_spot * px
    print(f"piano: spot {qty_spot:.6f} @ {px} = {noz:.2f} EUR ; perp {n_ct} ct")
    delta_atteso = abs(qty_spot - n_ct * c.ct_val)
    print(f"delta atteso: {delta_atteso:.6f} ({delta_atteso/qty_spot:.3%})")

    # ── GATE CARRY (delta-neutral: liquidazione + funding + delta) ──
    # NON si usa il gate direzionale: chiederebbe uno stop ATR e un budget di
    # rischio da posizione direzionale, che il carry non ha (verificato 16/10:
    # con equity 498 EUR il gate direzionale limitava il nozionale a 16 EUR).
    eq = equity_progetto()
    funding = funding_atteso(ex, c.inst_perp)
    delta_rel = delta_atteso / qty_spot if qty_spot else 1.0
    print(f"equity progetto: {eq:.2f} | funding atteso: {funding*100:.5f}%/8h | "
          f"delta: {delta_rel:.4%}")
    dec = gate_carry(nozionale=noz, funding_atteso=funding,
                     costo_ciclo=COSTO_CICLO, delta_relativo=delta_rel, leva=1.0)
    print(f"gate carry: ok={dec.ok} motivi={dec.motivi}")
    print(f"  liquidazione a {dec.distanza_liq:.1%} | payback {dec.periodi_payback:.0f} periodi (8h)")
    if not dec.ok:
        print("GATE CARRY RIFIUTA l'apertura. Non si apre.")
        return 1

    if not args.execute:
        print("\n[DRY-RUN] nessun ordine. Ripetere con --execute per aprire davvero.")
        return 0

    # ── ESECUZIONE: PRIMA spot, POI perp (la copertura si costruisce dal lato lungo) ──
    print("\n--- gamba 1/2: SPOT buy")
    px1 = ex.fetch_ticker(c.sym_spot)["ask"] * 1.002      # ask + 0,2%
    cid1 = cid_stabile(f"{nome.lower()}s", f"{c.sym_spot}|buy|{qty_spot}|{ora()[:10]}")
    try:
        o1 = invia_gamba(ex, Gamba(c.sym_spot, "buy", qty_spot, float(px1), cid1))
    except Exception as e:  # noqa: BLE001
        print(f"  invio spot FALLITO: {type(e).__name__}: {str(e)[:120]}")
        evento("apertura_fallita", gamba="spot", errore=str(e)[:200])
        return 1
    oo1, es1 = attesa_fill(ex, o1["id"], c.sym_spot, 60)
    filled1 = float(getattr(oo1, "get", lambda k, d=0: d)("filled") or 0)
    print(f"  esito spot: {es1} filled={filled1}")
    if es1 != "closed":
        try:
            ex.cancel_order(o1["id"], c.sym_spot)
        except Exception:
            pass
        print("  spot non completamente riempito: annullato il residuo, STOP (nessuna gamba scoperta)")
        evento("apertura_annullata", gamba="spot", esito=es1, filled=filled1)
        return 1

    print("\n--- gamba 2/2: PERP short")
    px2 = ex.fetch_ticker(c.sym_perp)["bid"] * 0.998      # bid - 0,2%
    cid2 = cid_stabile(f"{nome.lower()}p", f"{c.sym_perp}|sell|{n_ct}|{ora()[:10]}")
    try:
        o2 = invia_gamba(ex, Gamba(c.sym_perp, "sell", n_ct, float(px2), cid2,
                                   td_mode=MGN))
    except Exception as e:  # noqa: BLE001
        print(f"  invio perp FALLITO: {type(e).__name__}: {str(e)[:120]}")
        print("  ATTENZIONE: gamba spot APERTA e non coperta — richiede unwind manuale")
        evento("gamba_scoperta", gamba="perp", errore=str(e)[:200])
        return 1
    oo2, es2 = attesa_fill(ex, o2["id"], c.sym_perp, 60)
    filled2 = float(getattr(oo2, "get", lambda k, d=0: d)("filled") or 0)
    print(f"  esito perp: {es2} filled={filled2}")

    # ── RICONCILIAZIONE ──
    time.sleep(2)
    pos = [p for p in ex.fetch_positions([c.sym_perp])
           if abs(float(p.get("contracts") or 0)) > 0]
    ct_reale = float(pos[0]["contracts"]) if pos else 0.0
    bal = ex.fetch_balance()
    qty_reale = float((bal.get("total") or {}).get(c.nome, 0) or 0)
    delta = abs(qty_reale - ct_reale * c.ct_val)
    print(f"\nriconciliazione: spot {qty_reale:.6f} | perp {ct_reale} ct "
          f"({ct_reale*c.ct_val:.6f} unita') | delta {delta:.6f}")

    stato = {"coppie": {}}
    sf = DIR_STATO / "stato.json"
    if sf.exists():
        try:
            stato = json.loads(sf.read_text())
        except ValueError:
            pass
    stato.setdefault("coppie", {})[nome] = {
        "ts_apri": ora(), "qty_spot": qty_reale, "ct_perp": ct_reale,
        "prezzo": px, "delta": delta, "nozionale_eur": noz,
    }
    sf.parent.mkdir(parents=True, exist_ok=True)
    sf.write_text(json.dumps(stato, indent=1))
    evento("aperta", coppia=nome, qty_spot=qty_reale, ct=ct_reale, delta=delta)

    print(f"\n=== {nome} APERTA ===")
    print(f"stato: {sf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
