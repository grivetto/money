#!/usr/bin/env python3
"""farm_protocols.py — interagisce con protocolli DeFi per airdrop farming.

Carica il wallet dal vault e permette di eseguire operazioni base
(swap, bridge, stake) su catene EVM (Arbitrum, Base, Optimism, Ethereum).

Uso: farm_protocols.py --chain arbitrum --action check-balance
     farm_protocols.py --chain base --action swap --from ETH --to USDC --amount 0.005

PRIMA DI USARE: finanzia il wallet con ETH sul chain desiderato.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# RPC pubblici per le catene target
RPC_URLS = {
    "arbitrum": "https://arb1.arbitrum.io/rpc",
    "base": "https://mainnet.base.org",
    "optimism": "https://mainnet.optimism.io",
    "ethereum": "https://eth.llamarpc.com",
}

CHAIN_IDS = {
    "arbitrum": 42161,
    "base": 8453,
    "optimism": 10,
    "ethereum": 1,
}

VAULT_DIR = Path.home() / ".denaro_vault"
WALLET_KEY_FILE = VAULT_DIR / "airdrop_wallet.key"
WALLET_ADDR_FILE = VAULT_DIR / "airdrop_wallet.address"


def load_wallet() -> tuple[str, str]:
    """Carica chiave privata e indirizzo dal vault."""
    if not WALLET_KEY_FILE.exists():
        print("ERR: wallet non trovato. Esegui setup_wallet.py prima.", file=sys.stderr)
        sys.exit(1)
    address = WALLET_ADDR_FILE.read_text().strip()
    private_key = WALLET_KEY_FILE.read_text().strip()
    return address, private_key


def get_web3(chain: str):
    """Crea connessione Web3 per la catena specificata."""
    # Import qui per evitare blocchi se web3 non serve
    from web3 import Web3
    
    rpc = RPC_URLS.get(chain)
    if not rpc:
        print(f"ERR: catena '{chain}' sconosciuta. Disponibili: {list(RPC_URLS)}", file=sys.stderr)
        sys.exit(1)
    
    w3 = Web3(Web3.HTTPProvider(rpc))
    if not w3.is_connected():
        print(f"ERR: impossibile connettersi a {chain} ({rpc})", file=sys.stderr)
        sys.exit(1)
    return w3


def check_balance(chain: str, address: str) -> dict:
    """Controlla il saldo ETH del wallet sulla catena."""
    w3 = get_web3(chain)
    balance_wei = w3.eth.get_balance(address)
    balance_eth = w3.from_wei(balance_wei, "ether")
    return {"chain": chain, "address": address, "balance_eth": float(balance_eth)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Airdrop farming — interazioni DeFi")
    ap.add_argument("--chain", choices=list(RPC_URLS), default="arbitrum",
                    help="Catena su cui operare")
    ap.add_argument("--action", choices=["check-balance", "info"], default="check-balance",
                    help="Azione da eseguire")
    args = ap.parse_args()
    
    address, _ = load_wallet()
    
    if args.action == "check-balance":
        for chain in RPC_URLS:
            try:
                info = check_balance(chain, address)
                print(f"  {chain:12s}: {info['balance_eth']:.6f} ETH")
            except Exception as e:
                print(f"  {chain:12s}: ERR ({e})")
    
    elif args.action == "info":
        print(f"Wallet: {address}")
        print(f"Catene disponibili: {', '.join(RPC_URLS)}")
        print()
        print("Per finanziare: invia ETH a questo indirizzo su Arbitrum/Base/Optimism.")
        print("Gas suggerito: 0.015-0.02 ETH per catena (~30-40€ totale).")
        print()
        print("Primi protocolli target (ottobre 2026):")
        print("  1. Arcus (arcus.xyz) — waitlist, token confermato")
        print("  2. Polymarket — piazza scommesse, token confermato")
        print("  3. Variational — 50% supply alla community")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
