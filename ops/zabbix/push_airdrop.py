#!/usr/bin/env python3
"""push_airdrop.py — pubblica le metriche del wallet airdrop su Zabbix.

Gira su MARCODG1 (l'API Zabbix è locale su 127.0.0.1:1080).
Legge `/home/marco/money/ops/dashboard/airdrop_status.json` (scritto dal cron
di mc2) e spinge gli item trapper `airdrop.*` sull'host `mc2`.

Item creati al primo giro se assenti (type=2 trapper, value_type=0 float).
Nessuna credenziale nel sorgente: usa ~/.zbx_cred (formato "Utente:Password").
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

API = os.environ.get("ZBX_API", "http://127.0.0.1:1080/api_jsonrpc.php")
STATUS_FILE = Path(os.environ.get("AIRDROP_STATUS_FILE",
                                  "/home/marco/money/ops/dashboard/airdrop_status.json"))
HOST = os.environ.get("ZBX_HOST", "mc2")

# key -> (nome visibile, unità)
ITEMS = {
    "airdrop.usdc_total": ("Airdrop wallet USDC totale", "USDC"),
    "airdrop.eth_total": ("Airdrop wallet ETH totale", "ETH"),
    "airdrop.chains_ok": ("Airdrop catene RPC ok", ""),
    "airdrop.age_min": ("Airdrop eta ultimo dato", "min"),
    "airdrop.health": ("Airdrop salute collettore (1=ok)", ""),
}


def rpc(method: str, params, auth: str | None = None):
    body = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    if auth:
        body["auth"] = auth
    req = urllib.request.Request(API, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            out = json.loads(r.read())
    except Exception as exc:
        print("RPC %s errore di rete: %s" % (method, exc), file=sys.stderr)
        return None
    if "error" in out:
        print("RPC %s: %s" % (method, out["error"].get("data", out["error"])), file=sys.stderr)
        return None
    return out.get("result")


def login() -> str | None:
    cred = Path(os.environ.get("ZBX_CRED_FILE", str(Path.home() / ".zbx_cred")))
    try:
        user, pwd = cred.read_text().strip().split(":", 1)
    except Exception:
        user = os.environ.get("ZBX_USER", "Admin")
        pwd = os.environ.get("ZBX_PASS", "")
    return rpc("user.login", {"username": user, "password": pwd})


def ensure_items(auth: str) -> dict:
    """Ritorna {key: itemid}, creando gli item mancanti sull'host."""
    hosts = rpc("host.get", {"filter": {"host": [HOST]}, "output": ["hostid"]}, auth)
    if not hosts:
        print("host %s non trovato" % HOST, file=sys.stderr)
        return {}
    hostid = hosts[0]["hostid"]

    existing = rpc("item.get", {"hostids": [hostid], "output": ["itemid", "key_"],
                                "filter": {"key_": list(ITEMS)}}, auth) or []
    by_key = {i["key_"]: i["itemid"] for i in existing}

    missing = [k for k in ITEMS if k not in by_key]
    if missing:
        created = rpc("item.create", [{
            "hostid": hostid,
            "name": ITEMS[k][0],
            "key_": k,
            "type": 2,        # trapper: il valore arriva da history.push
            "value_type": 0,  # float
            "units": ITEMS[k][1],
            "delay": "0",
        } for k in missing], auth)
        if created:
            for it in created["itemids"]:
                got = rpc("item.get", {"itemids": [it], "output": ["key_"]}, auth)
                if got:
                    by_key[got[0]["key_"]] = it
        else:
            print("creazione item fallita (%s)" % ", ".join(missing), file=sys.stderr)
    return by_key


def main() -> int:
    if not STATUS_FILE.is_file():
        print("ERR: %s assente" % STATUS_FILE, file=sys.stderr)
        return 1
    try:
        d = json.loads(STATUS_FILE.read_text())
    except Exception as exc:
        print("ERR: JSON illeggibile: %s" % exc, file=sys.stderr)
        return 1

    gen = d.get("generated_at", "")
    age_min = 0.0
    if gen:
        try:
            import calendar
            # generated_at è UTC: timegm, non mktime (che applicherebbe il fuso locale)
            ts = calendar.timegm(time.strptime(gen, "%Y-%m-%dT%H:%M:%SZ"))
            age_min = max(0.0, (time.time() - ts) / 60.0)
        except Exception:
            age_min = -1.0

    tot = d.get("totals") or {}
    health = d.get("health") or {}

    values = {
        "airdrop.usdc_total": round(float(tot.get("usdc") or 0), 6),
        "airdrop.eth_total": round(float(tot.get("eth") or 0), 8),
        "airdrop.chains_ok": int(health.get("chains_ok") or 0),
        "airdrop.age_min": round(age_min, 1),
        "airdrop.health": 1 if health.get("ok") else 0,
    }

    auth = login()
    if not auth:
        return 2
    ids = ensure_items(auth)
    if not ids:
        return 3

    payload = [{"host": HOST, "key": k, "value": str(values[k])}
               for k in values if k in ids]
    res = rpc("history.push", payload, auth)
    rpc("user.logout", [], auth)

    if res is None:
        return 4
    print("push ok: %d item (usdc=%.2f eth=%.6f chains=%d age=%.1fmin)" % (
        len(payload), values["airdrop.usdc_total"], values["airdrop.eth_total"],
        values["airdrop.chains_ok"], values["airdrop.age_min"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
