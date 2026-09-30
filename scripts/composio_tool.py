#!/usr/bin/env python
"""Esegue un tool Composio (Platform REST v3.1) per un utente del progetto.

Uso: python scripts/composio_tool.py <TOOL_SLUG> [--user sergio] [-d '{...}'] [--json]

La chiave COMPOSIO_API_KEY si legge dall'ambiente o da money/.env (mai stampata).
Integrazione di riferimento: JEV (auth config ac_qTjQ6rmObzt2, connessione
ca_5DLw5RxZRjG8, user "sergio"). Esempi:

  python scripts/composio_tool.py JEV_LIST_MODELS
  python scripts/composio_tool.py JEV_EVALUATE_STATE -d '{"state":"...","questions":{"q":{"type":"noul","instructions":"..."}}}'
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://backend.composio.dev/api/v3.1"


def load_key() -> str:
    key = os.environ.get("COMPOSIO_API_KEY", "")
    if key:
        return key
    envp = Path(__file__).resolve().parents[1] / ".env"
    if envp.is_file():
        for line in envp.read_text(encoding="utf-8").splitlines():
            if line.startswith("COMPOSIO_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("COMPOSIO_API_KEY non trovata (ne' in ambiente ne' in money/.env)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("slug", help="Tool slug, es. JEV_LIST_MODELS")
    ap.add_argument("--user", default="sergio", help="user_id del progetto (default: sergio)")
    ap.add_argument("-d", "--data", default="{}", help="argomenti del tool in JSON")
    ap.add_argument("--json", action="store_true", help="stampa la risposta completa")
    args = ap.parse_args()

    key = load_key()
    try:
        tool_args = json.loads(args.data)
    except json.JSONDecodeError as e:
        raise SystemExit(f"-d non e' JSON valido: {e}")

    body = json.dumps({"user_id": args.user, "arguments": tool_args}).encode("utf-8")
    req = urllib.request.Request(
        f"{API}/tools/execute/{args.slug}",
        data=body,
        method="POST",
        headers={
            "x-api-key": key,
            "Content-Type": "application/json",
            "User-Agent": "denaro-composio/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            out = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:400]}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"successful={out.get('successful')} log_id={out.get('log_id')}")
        print(json.dumps(out.get("data"), ensure_ascii=False, indent=2)[:2000])
        if out.get("error"):
            print("error:", out["error"], file=sys.stderr)
    return 0 if out.get("successful") else 1


if __name__ == "__main__":
    sys.exit(main())
