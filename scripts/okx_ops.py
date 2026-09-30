#!/usr/bin/env python3
"""Operazioni controllate sul conto MAIN OKX EEA — test "Futures mode" (acctLv 2).

Subcomandi (ogni scrittura richiede --execute; default = sola lettura/stampa):
  status                          saldi funding/trading + acctLv
  transfer --amt 20               EUR funding -> trading (from=6, to=18)
  swap-buy --pair USDC/EUR --qty 10   limit buy alzato sull'ask (taker), attende fill
  set-lever --inst DOT-USD_UM_XPERP-310808 --lever 1
  order-probe --inst <instId> [--off -0.04] [--td cross]
                                  ordine limite LONTANO dal mercato -> verifica -> ANNULLA subito

Sicurezze: mai stampare chiavi; clOrdId idempotente; nessuna size oltre i minimi;
l'ordine-probe NON deve mai riempirsi (prezzo fuori mercato) e viene annullato in ogni caso.
"""
import re
import sys
import time
from pathlib import Path

import ccxt

ENV = Path("/home/marco/denaro/secrets/main_okx.env")


def leggi_env(path):
    d = {}
    for ln in Path(path).read_text().splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or "=" not in ln:
            continue
        k, v = ln.split("=", 1)
        d[k.strip()] = v.strip().strip('"').strip("'")
    return d


def client():
    env = leggi_env(ENV)
    return ccxt.okx({
        "apiKey": env["OKX_API_KEY"], "secret": env["OKX_API_SECRET"],
        "password": env["OKX_PASSPHRASE"], "hostname": "eea.okx.com",
        "enableRateLimit": True, "options": {"defaultType": "spot"},
    })


def arg(nome, default=None):
    for i, a in enumerate(sys.argv):
        if a == nome:
            return sys.argv[i + 1]
    return default


def flag(nome):
    return nome in sys.argv


def saldi(ex, prefisso=""):
    tr = ex.privateGetAccountBalance()["data"][0]
    print(f"{prefisso}TRADING totalEq = {tr.get('totalEq')}")
    for r in tr.get("details", []):
        if r.get("ccy") in ("EUR", "USDC", "USDT"):
            print(f"  trading {r.get('ccy')}: availEq={r.get('availEq')} eq={r.get('eq')}")
    fu = ex.privateGetAssetBalances({"ccy": "EUR,USDC,USDT"})["data"]
    for r in fu:
        print(f"  funding {r.get('ccy')}: availBal={r.get('availBal')}")


def main():
    ex = client()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "status":
        cfg = ex.privateGetAccountConfig()["data"][0]
        print(f"acctLv={cfg.get('acctLv')} perm={cfg.get('perm')} posMode={cfg.get('posMode')}")
        saldi(ex)

    elif cmd == "transfer":
        amt = arg("--amt", "20")
        if not flag("--execute"):
            print(f"[DRY] transferirei {amt} EUR: funding(6) -> trading(18)")
            return
        r = ex.privatePostAssetTransfer({"ccy": "EUR", "amt": str(amt), "from": "6", "to": "18"})
        print("transfer resp:", r.get("code"), r.get("data"))
        time.sleep(3)
        saldi(ex, "post-transfer ")

    elif cmd == "swap-buy":
        pair, qty = arg("--pair"), arg("--qty")
        if not pair or not qty:
            sys.exit("servono --pair e --qty")
        ex.load_markets()
        t = ex.fetch_ticker(pair)
        px = ex.price_to_precision(pair, float(t["ask"]) * 1.005)
        print(f"buy {qty} {pair} a {px} (ask {t['ask']})")
        if not flag("--execute"):
            print("[DRY] ordine non inviato")
            return
        o = ex.create_order(pair, "limit", "buy", float(qty), float(px))
        print("order:", o["id"], o["status"])
        oo = None
        try:
            for _ in range(20):
                time.sleep(2)
                oo = ex.fetch_order(o["id"], pair)
                if oo["status"] in ("closed", "canceled"):
                    break
        except Exception as e:
            print("poll ERR:", type(e).__name__, str(e)[:120])
        if oo is None:
            print(f"ATTENZIONE: stato non letto; annullo preventivamente {o['id']}")
            try:
                ex.cancel_order(o["id"], pair)
            except Exception as e2:
                print("cancel:", type(e2).__name__, str(e2)[:100])
        else:
            print(f"esito: {oo['status']} filled={oo.get('filled')} avg={oo.get('average')} fee={oo.get('fee')}")

    elif cmd == "set-lever":
        inst, lever = arg("--inst"), arg("--lever", "1")
        if not inst:
            sys.exit("serve --inst")
        if not flag("--execute"):
            print(f"[DRY] set-lever {inst} = {lever}x (cross)")
            return
        r = ex.privatePostAccountSetLeverage({"instId": inst, "lever": str(lever), "mgnMode": "cross"})
        print("set-lever resp:", r.get("code"), r.get("data"))

    elif cmd == "order-probe":
        inst = arg("--inst")
        off = float(arg("--off", "-0.04"))
        td = arg("--td", "cross")
        if not inst:
            sys.exit("serve --inst")
        ex.load_markets()
        m = next((mm for mm in ex.markets.values() if mm["id"] == inst), None)
        if m is None:
            sys.exit(f"strumento {inst} non trovato nei mercati")
        sym = m["symbol"]
        t = ex.fetch_ticker(sym)
        last = float(t["last"])
        target = last * (1.0 + off)
        try:
            lim = ex.request("public/price-limit", "public", "GET", {"instId": inst})["data"][0]
            buy_lmt = float(lim.get("buyLmt") or "0")
            sell_lmt = float(lim.get("sellLmt") or "0")
            print(f"price-limit: buyLmt={buy_lmt} sellLmt={sell_lmt}")
            if sell_lmt and target < sell_lmt:
                target = sell_lmt * 1.0001
            if buy_lmt:
                target = min(target, buy_lmt * 0.999)
        except Exception as e:
            print("price-limit n/d:", type(e).__name__, str(e)[:80])
        px = ex.price_to_precision(sym, target)
        sz = m["limits"]["amount"]["min"]
        cid = f"hdt{int(time.time())}"
        print(f"PDA: {sym} | sz={sz} (min) | px={px} (last={last}, off={off}) | td={td} | clOrdId={cid}")
        if not flag("--execute"):
            print("[DRY] nessun ordine inviato")
            return
        o = ex.create_order(sym, "limit", "buy", sz, float(px),
                            params={"tdMode": td, "clOrdId": cid})
        print("ORDER CREATO:", o["id"], o["status"])
        time.sleep(2)
        pend = ex.fetch_open_orders(sym)
        print("ordini aperti visti:", len(pend))
        try:
            ex.cancel_order(o["id"], sym)
            print("cancel inviato")
        except Exception as e:
            print("cancel ERR:", type(e).__name__, str(e)[:120])
        time.sleep(2)
        oo = None
        try:
            oo = ex.fetch_order(o["id"], sym)
        except Exception as e:
            print("fetch ERR:", type(e).__name__, str(e)[:120])
        if oo is not None:
            print(f"FINE: stato_finale={oo['status']} filled={oo.get('filled')}")
        else:
            try:
                ex.cancel_order(o["id"], sym)
                print("secondo cancel inviato (ripetuto)")
            except Exception as e2:
                print("secondo cancel:", type(e2).__name__, str(e2)[:120])

    else:
        sys.exit(f"subcomando sconosciuto: {cmd}")


if __name__ == "__main__":
    main()
