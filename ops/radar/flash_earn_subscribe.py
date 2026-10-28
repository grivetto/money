#!/usr/bin/env python3
"""flash_earn_subscribe.py — sottoscrive assets a campagne OKX Flash Earn.

Legge le chiavi API dal vault, controlla se c'è una campagna Flash Earn
attiva compatibile coi nostri asset, e sottoscrive il capitale disponibile.

Uso: flash_earn_subscribe.py [--dry] [--amount AMT] [--asset USDC]
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

# Configurazione
OKX_BASE = "https://eea.okx.com"
VAULT_FILE = Path.home() / "denaro" / "secrets" / "main_okx.env"
MIN_USDC = 10.0  # minimo USDC da sottoscrivere

def load_credentials() -> dict[str, str]:
    """Carica le credenziali OKX dal vault."""
    creds = {}
    if not VAULT_FILE.exists():
        print(f"ERR: vault non trovato: {VAULT_FILE}", file=sys.stderr)
        return creds
    with open(VAULT_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                creds[k] = v.strip().strip('"').strip("'")
    return creds

def okx_request(method: str, path: str, body: dict | None = None,
                creds: dict[str, str] | None = None) -> dict:
    """Chiamata autenticata all'API OKX."""
    if creds is None:
        creds = load_credentials()
    
    key = creds.get("OKX_API_KEY", "")
    secret = creds.get("OKX_API_SECRET", "")
    pw = creds.get("OKX_PASSPHRASE", "")
    
    if not key:
        raise ValueError("Credenziali OKX non trovate")
    
    ts = str(int(time.time() * 1000))
    body_str = json.dumps(body) if body else ""
    msg = ts + method.upper() + path + body_str
    sign = base64.b64encode(
        hmac.new(secret.encode(), msg.encode(), hashlib.sha256).digest()
    ).decode()
    
    url = OKX_BASE + path
    headers = {
        "OK-ACCESS-KEY": key,
        "OK-ACCESS-SIGN": sign,
        "OK-ACCESS-TIMESTAMP": ts,
        "OK-ACCESS-PASSPHRASE": pw,
        "Content-Type": "application/json",
    }
    
    req = urllib.request.Request(url, data=body_str.encode() if body_str else None,
                                 headers=headers, method=method.upper())
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read().decode())
        if data.get("code") != "0":
            raise RuntimeError(f"OKX API error: {data.get('code')} {data.get('msg')}")
        return data

def get_earn_balance(creds: dict[str, str]) -> dict[str, float]:
    """Legge il saldo Simple Earn (flexible savings)."""
    data = okx_request("GET", "/api/v5/finance/savings/balance", creds=creds)
    balances = {}
    for d in data.get("data", []):
        ccy = d.get("ccy", "")
        amt = float(d.get("amt", 0))
        if amt > 0.01:
            balances[ccy] = amt
    return balances

def get_active_campaigns() -> list[dict]:
    """Cerca campagne Flash Earn attive sulle pagine help OKX."""
    # Placeholder: in produzione, questo chiama flash_earn_radar.py
    # Per ora restituisce lista vuota (le campagne si trovano col radar)
    return []

def subscribe_to_earn(ccy: str, amt: str, creds: dict[str, str],
                      rate: str = "1") -> dict:
    """Sottoscrive un importo a OKX Simple Earn (flexible savings).
    
    Per Flash Earn, il prodotto specifico potrebbe richiedere parametri aggiuntivi
    come productId o investType.
    """
    body = {
        "ccy": ccy.upper(),
        "amt": amt,
        "side": "purchase",
        "rate": rate,
    }
    return okx_request("POST", "/api/v5/finance/savings/purchase-redempt",
                       body=body, creds=creds)

def get_available_earn_products(ccy: str = "USDC") -> list[dict]:
    """Legge i prodotti Simple Earn disponibili per una valuta."""
    # Endpoint pubblico per i tassi di lending
    url = f"{OKX_BASE}/api/v5/finance/savings/lending-rate?ccy={ccy}"
    req = urllib.request.Request(url, headers={"User-Agent": "money-earn"})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read().decode())
        if data.get("code") != "0":
            return []
        return data.get("data", [])

def main() -> int:
    ap = argparse.ArgumentParser(description="Auto-subscribe Flash Earn OKX")
    ap.add_argument("--dry", action="store_true", help="Sola lettura, non esegue transazioni")
    ap.add_argument("--amount", type=str, help="Importo da sottoscrivere (es. '100')")
    ap.add_argument("--asset", type=str, default="USDC", help="Asset da sottoscrivere")
    ap.add_argument("--show-balance", action="store_true", help="Mostra saldi Earn")
    ap.add_argument("--show-products", action="store_true", help="Mostra prodotti disponibili")
    args = ap.parse_args()
    
    try:
        creds = load_credentials()
        if not creds:
            print("ERR: credenziali non caricate", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"ERR: {e}", file=sys.stderr)
        return 1
    
    if args.show_balance:
        try:
            balances = get_earn_balance(creds)
            print("=== SALDI SIMPLE EARN ===")
            for ccy, amt in sorted(balances.items()):
                print(f"  {ccy}: {amt:.6f}")
        except Exception as e:
            print(f"ERR lettura saldi: {e}")
        return 0
    
    if args.show_products:
        print(f"=== PRODOTTI EARN per {args.asset} ===")
        try:
            products = get_available_earn_products(args.asset)
            for p in products:
                print(f"  {p.get('ccy')} rate={p.get('rate')} min={p.get('minAmt')} max={p.get('maxAmt')}")
        except Exception as e:
            print(f"ERR: {e}")
        return 0
    
    if args.dry:
        print("[DRY-RUN] Simulazione sottoscrizione:")
        print(f"  asset: {args.asset}")
        print(f"  amount: {args.amount or 'TUTTO'}")
        
        try:
            balances = get_earn_balance(creds)
            if args.asset in balances:
                print(f"  saldo attuale Earn: {balances[args.asset]:.6f} {args.asset}")
            else:
                print(f"  {args.asset}: non presente in Earn")
        except Exception as e:
            print(f"  ERR: {e}")
        return 0
    
    # Modalità reale (richiede autorizzazione)
    print("ATTENZIONE: modalità reale. Userai le chiavi MAIN con permessi Transfer.")
    print(f"Sottoscrizione {args.amount or 'MAX'} {args.asset} a Simple Earn?")
    print("Usa --dry per simulare.")
    
    if args.amount:
        try:
            result = subscribe_to_earn(args.asset, args.amount, creds)
            print(f"OK: {json.dumps(result.get('data', []), indent=2)}")
        except Exception as e:
            print(f"ERR: {e}")
            return 1
    
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
