#!/usr/bin/env python3
"""setup_wallet.py — genera wallet on-chain per airdrop farming.

Crea un wallet Ethereum (ECDSA) e salva le chiavi in modo sicuro
nel vault Denaro (600, git-ignored).

Uso: setup_wallet.py [--show-address]
"""
from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path

from eth_account import Account

VAULT_DIR = Path.home() / ".denaro_vault"
WALLET_KEY_FILE = VAULT_DIR / "airdrop_wallet.key"
WALLET_ADDR_FILE = VAULT_DIR / "airdrop_wallet.address"


def generate_wallet() -> tuple[str, str]:
    """Genera un nuovo wallet Ethereum e restituisce (address, private_key_hex)."""
    acct = Account.create()
    return acct.address, acct.key.hex()


def save_wallet(address: str, private_key: str) -> None:
    """Salva il wallet nel vault Denaro con permessi restrittivi."""
    VAULT_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)

    # Salva chiave privata (solo il proprietario può leggere)
    WALLET_KEY_FILE.write_text(private_key)
    WALLET_KEY_FILE.chmod(0o600)

    # Salva indirizzo (pubblico, può essere letto)
    WALLET_ADDR_FILE.write_text(address + "\n")
    WALLET_ADDR_FILE.chmod(0o644)

    print(f"Wallet generato e salvato in {VAULT_DIR}")
    print(f"  chiave: {WALLET_KEY_FILE} (600)")
    print(f"  address: {WALLET_ADDR_FILE} (644)")


def load_wallet() -> tuple[str, str] | None:
    """Carica il wallet esistente. Restituisce (address, private_key) o None."""
    if not WALLET_KEY_FILE.exists() or not WALLET_ADDR_FILE.exists():
        return None
    address = WALLET_ADDR_FILE.read_text().strip()
    private_key = WALLET_KEY_FILE.read_text().strip()
    return address, private_key


def main() -> int:
    ap = argparse.ArgumentParser(description="Setup wallet on-chain per airdrop")
    ap.add_argument("--show-address", action="store_true",
                    help="Mostra solo l'indirizzo (non genera nuovo wallet)")
    ap.add_argument("--force", action="store_true",
                    help="Forza rigenerazione wallet (SOVRASCRIVE il esistente!)")
    args = ap.parse_args()

    # Controlla se esiste già
    existing = load_wallet()

    if args.show_address:
        if existing:
            print(existing[0])
        else:
            print("Nessun wallet trovato. Esegui senza --show-address per crearne uno.")
        return 0

    if existing and not args.force:
        print(f"Wallet già esistente: {existing[0]}")
        print("Usa --force per rigenerarlo (ATTENZIONE: perdi il vecchio wallet!)")
        return 0

    if existing and args.force:
        print("ATTENZIONE: stai per sovrascrivere il wallet esistente!")
        print(f"Vecchio address: {existing[0]}")
        confirm = input("Confermi? [s/N] ")
        if confirm.lower() != "s":
            print("Annullato.")
            return 0

    address, private_key = generate_wallet()
    save_wallet(address, private_key)
    print(f"\nNuovo wallet: {address}")
    print("\nPer finanziarlo, invia ETH su Arbitrum/Base/Optimism a questo indirizzo.")
    print("Gas suggerito: 0.02 ETH (~40€) per iniziare.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
