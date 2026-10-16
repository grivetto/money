#!/usr/bin/env python3
"""setup_ricerca_items.py — crea gli item Zabbix della ricerca edge (trapper).

PERCHE' ESISTE
==============
`push_metrics.py` invia i valori con `sender`/trapper, ma un item deve ESISTERE
su Zabbix perche' il valore venga accettato: senza item, i valori della ricerca
venivano spediti e scartati (verificato: 62 push, 0 item `ricerca.*`).

Crea (idempotente) gli item sui host `mc2` e `MARCODG1`:
  mc2      : ricerca.promosse, ricerca.archiviate, ricerca.funding_scan.n,
             ricerca.funding_scan.candidati, ricerca.funding_scan.miglior_netto,
             ricerca.basis.exp_conservativa, ricerca.basis.contango
  MARCODG1 : canary.review_pass, canary.review_tot

Uso:  .venv/bin/python3 ops/zabbix/setup_ricerca_items.py
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

API = "http://127.0.0.1:1080/api_jsonrpc.php"

ITEMS = [
    # (host_key, key, name, value_type)  value_type: 3 = unsigned int, 0 = float
    ("mc2", "ricerca.promosse", "Ricerca — strategie promosse", 3),
    ("mc2", "ricerca.archiviate", "Ricerca — strategie archiviate", 3),
    ("mc2", "ricerca.funding_scan.n", "Ricerca — funding scan: simboli", 3),
    ("mc2", "ricerca.funding_scan.candidati", "Ricerca — funding scan: candidati", 3),
    ("mc2", "ricerca.funding_scan.miglior_netto", "Ricerca — funding scan: miglior netto annuo", 0),
    ("mc2", "ricerca.basis.exp_conservativa", "Ricerca — basis: expectancy conservativa", 0),
    ("mc2", "ricerca.basis.contango", "Ricerca — basis: frazione contango", 0),
    ("MARCODG1", "canary.review_pass", "Canary C1 — criteri review PASS", 3),
    ("MARCODG1", "canary.review_tot", "Canary C1 — criteri review totali", 3),
]


def rpc(method, params, auth=None):
    body = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    if auth:
        body["auth"] = auth
    req = urllib.request.Request(API, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def main() -> int:
    cred = Path.home() / ".zbx_cred"
    if cred.exists():
        u, p = cred.read_text().strip().split(":", 1)
    else:
        import os
        u, p = os.environ.get("ZBX_USER", "Admin"), os.environ.get("ZBX_PASS", "")
    try:
        auth = rpc("user.login", {"username": u, "password": p})["result"]
    except Exception as e:  # noqa: BLE001
        print(f"login fallito: {e}")
        return 1

    hosts = rpc("host.get", {"output": ["hostid", "host"],
                             "filter": {"host": ["mc2", "MARCODG1"]}}, auth)["result"]
    by_host = {h["host"]: h["hostid"] for h in hosts}
    mancanti_host = [k for k, _, _, _ in ITEMS if k not in by_host]
    if mancanti_host:
        print(f"ATTENZIONE: host non trovati in Zabbix: {set(mancanti_host)}")
        print(f"host disponibili: {list(by_host)}")

    creati = 0
    for host_key, key, name, vt in ITEMS:
        hid = by_host.get(host_key)
        if not hid:
            print(f"  salto {key}: host {host_key} assente")
            continue
        esistenti = rpc("item.get", {"hostids": [hid], "output": ["itemid"],
                                     "filter": {"key_": key}}, auth)["result"]
        if esistenti:
            print(f"  ok   {key} (esiste)")
            continue
        r = rpc("item.create", [{
            "name": name, "key_": key, "hostid": hid,
            "type": 2,            # Zabbix trapper
            "value_type": vt,     # 0=float, 3=unsigned int
            "history": "90d", "trends": "365d",
        }], auth)
        # item.create risponde {"result": {"itemids": [...]}} — non a livello root
        esito = (r or {}).get("result") or {}
        if esito.get("itemids"):
            creati += 1
            print(f"  NEW  {key} = {name}")
        else:
            print(f"  ERR  {key}: {r.get('error')}")

    print(f"\nitem creati: {creati}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
