#!/usr/bin/env python3
"""probe_bybit_account.py — verifica read-only delle chiavi Bybit (validita', permessi, fee).

NON stampa mai chiavi o segreti: solo lunghezze, permessi e tassi.
Chiamate: /v5/user/query-api (chiave), /v5/account/fee-rate (fee reali),
/v5/account/wallet-balance (saldi). Nessun ordine, nessuna scrittura.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ENV = Path("/home/sergio/money/.env")
HOST = "https://api.bybit.com"


def leggi_env(path: Path) -> dict:
    d = {}
    for riga in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        riga = riga.strip()
        if "=" in riga and not riga.startswith("#"):
            k, v = riga.split("=", 1)
            d[k.strip()] = v.strip().strip('"').strip("'")
    return d


def trova(env: dict, *nomi: str):
    for n in nomi:
        for k, v in env.items():
            if k.lower() == n.lower() and v:
                return v
    return None


env = leggi_env(ENV)
chiave = trova(env, "Bybit_API_key", "BYBIT_API_KEY")
segreto = trova(env, "Bybit_API_secret", "BYBIT_API_SECRET")
if not chiave or not segreto:
    print("chiavi Bybit NON trovate in", ENV)
    raise SystemExit(1)
print(f"chiave : presente, len={len(chiave)}, inizio={chiave[:4]}... (valore non riprodotto)")
print(f"segreto: presente, len={len(segreto)}")


def bybit(path: str, params: dict | None = None, host: str = HOST):
    params = params or {}
    qs = urlencode(params)
    ts = str(int(time.time() * 1000))
    recv = "5000"
    firma = hmac.new(segreto.encode(), (ts + chiave + recv + qs).encode(),
                     hashlib.sha256).hexdigest()
    url = f"{host}{path}" + (f"?{qs}" if qs else "")
    req = Request(url, headers={"X-BAPI-API-KEY": chiave, "X-BAPI-TIMESTAMP": ts,
                                "X-BAPI-RECV-WINDOW": recv, "X-BAPI-SIGN": firma})
    with urlopen(req, timeout=20) as r:
        return json.loads(r.read())


for host, etichetta in ((HOST, "bybit.com"), ("https://api.bybit.nl", "bybit.nl (EEA)")):
    print(f"\n--- host {etichetta} ---")
    try:
        d = bybit("/v5/user/query-api", host=host)
    except HTTPError as exc:
        print(f"  HTTP {exc.code}: {exc.read()[:200]}")
        continue
    except Exception as exc:
        print(f"  errore rete: {type(exc).__name__}: {exc}")
        continue
    print(f"  retCode={d.get('retCode')} retMsg={d.get('retMsg')}")
    res = d.get("result") or {}
    if res:
        print(f"  readOnly={res.get('readOnly')} | permissions={res.get('permissions')}")
        print(f"  ips={res.get('ips') or 'nessuna restrizione'} | expiredAt={res.get('expiredAt')}")
        print(f"  note={res.get('note')}")
    if d.get("retCode") != 0:
        continue

    for cat in ("spot", "linear"):
        try:
            f = bybit("/v5/account/fee-rate", {"category": cat}, host=host)
            for x in (f.get("result", {}).get("list") or [])[:3]:
                print(f"  fee {cat}: {x.get('symbol')} maker={x.get('makerFeeRate')} "
                      f"taker={x.get('takerFeeRate')}")
        except Exception as exc:
            print(f"  fee {cat}: {type(exc).__name__}")

    for at in ("UNIFIED", "SPOT"):
        try:
            w = bybit("/v5/account/wallet-balance", {"accountType": at}, host=host)
            if w.get("retCode") == 0:
                for acc in (w.get("result", {}).get("list") or []):
                    print(f"  wallet {at}: equity={acc.get('totalEquity')} "
                          f"usd={acc.get('totalWalletBalance')}")
                    for c in (acc.get("coin") or [])[:8]:
                        if float(c.get("walletBalance") or 0) != 0:
                            print(f"     {c.get('coin')}: {c.get('walletBalance')}")
            else:
                print(f"  wallet {at}: {w.get('retMsg')}")
        except Exception as exc:
            print(f"  wallet {at}: {type(exc).__name__}")
