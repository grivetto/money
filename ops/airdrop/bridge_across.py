#!/usr/bin/env python3
"""bridge_across.py — Bridge ETH nativo Arbitrum -> Base/Optimism via Across.

Uso:
  bridge_across.py --dest base --amount 0.004            # DRY-RUN
  bridge_across.py --dest base --amount 0.004 --live     # esegue
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

from web3 import Web3

VAULT = Path.home() / ".denaro_vault"
KEY = (VAULT / "airdrop_wallet.key").read_text().strip()
ADDR = (VAULT / "airdrop_wallet.address").read_text().strip()

RPC = "https://arb1.arbitrum.io/rpc"
SPOKE_POOL = "0xe35e9842fceaCA96570B734083f4a58e8F7C5f2A"
ZERO = "0x0000000000000000000000000000000000000000"

DEST_CHAIN_ID = {"base": 8453, "optimism": 10, "arbitrum": 42161}

ABI = json.loads("""
[{"inputs":[
   {"internalType":"address","name":"depositor","type":"address"},
   {"internalType":"address","name":"recipient","type":"address"},
   {"internalType":"address","name":"inputToken","type":"address"},
   {"internalType":"address","name":"outputToken","type":"address"},
   {"internalType":"uint256","name":"inputAmount","type":"uint256"},
   {"internalType":"uint256","name":"outputAmount","type":"uint256"},
   {"internalType":"uint256","name":"destinationChainId","type":"uint256"},
   {"internalType":"address","name":"exclusiveRelayer","type":"address"},
   {"internalType":"uint32","name":"quoteTimestamp","type":"uint32"},
   {"internalType":"uint32","name":"fillDeadline","type":"uint32"},
   {"internalType":"uint32","name":"exclusivityDeadline","type":"uint32"},
   {"internalType":"bytes","name":"message","type":"bytes"}],
  "name":"depositV3","outputs":[],"stateMutability":"payable","type":"function"}]
""")


def quote(dest_chain: int, amount_wei: int) -> dict:
    url = ("https://app.across.to/api/suggested-fees"
           f"?inputToken={ZERO}&outputToken={ZERO}"
           f"&originChainId=42161&destinationChainId={dest_chain}"
           f"&amount={amount_wei}&recipient={ADDR}")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) denaro-airdrop/1.0",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", required=True, choices=list(DEST_CHAIN_ID))
    ap.add_argument("--amount", required=True, type=float, help="ETH da bridgeare")
    ap.add_argument("--live", action="store_true")
    a = ap.parse_args()

    w3 = Web3(Web3.HTTPProvider(RPC))
    if not w3.is_connected():
        print("ERR: Arbitrum RPC non raggiungibile")
        return 1

    amount_wei = w3.to_wei(a.amount, "ether")
    dest_id = DEST_CHAIN_ID[a.dest]

    q = quote(dest_id, amount_wei)
    fee = int(q["totalRelayFee"]["total"])
    out_wei = amount_wei - fee
    relayer = q.get("exclusiveRelayer", ZERO)
    quote_ts = int(q["timestamp"])

    bal = w3.eth.get_balance(ADDR)
    print(f"Wallet  : {ADDR}")
    print(f"Saldo   : {w3.from_wei(bal,'ether')} ETH (Arbitrum)")
    print(f"Bridge  : {a.amount} ETH -> {a.dest} (chain {dest_id})")
    print(f"Fee     : {fee/1e18:.9f} ETH  ({fee/amount_wei*100:.4f}%)")
    print(f"Ricevi  : {out_wei/1e18:.9f} ETH")
    print(f"Relayer : {relayer}")
    print(f"Fill    : {q['estimatedFillTimeSec']}s")

    if bal < amount_wei:
        print("ERR: saldo insufficiente")
        return 1
    if out_wei <= 0:
        print("ERR: output <= 0")
        return 1

    contract = w3.eth.contract(address=Web3.to_checksum_address(SPOKE_POOL), abi=ABI)
    now = int(time.time())
    args = [
        Web3.to_checksum_address(ADDR),          # depositor
        Web3.to_checksum_address(ADDR),          # recipient
        Web3.to_checksum_address(ZERO),          # inputToken (native)
        Web3.to_checksum_address(ZERO),          # outputToken (native)
        amount_wei,                              # inputAmount
        out_wei,                                 # outputAmount
        dest_id,                                 # destinationChainId
        Web3.to_checksum_address(relayer),       # exclusiveRelayer
        quote_ts,                                # quoteTimestamp
        now + 21600,                             # fillDeadline (6h)
        0,                                       # exclusivityDeadline
        b"",                                     # message
    ]

    # Simulazione (eth_call) — fallisce se il deposito non sarebbe valido
    try:
        contract.functions.depositV3(*args).call({"from": ADDR, "value": amount_wei})
        print("Simulazione: OK")
    except Exception as exc:
        print(f"Simulazione FALLITA: {exc}")
        return 1

    if not a.live:
        print("\n[DRY-RUN] Nessuna transazione inviata. Aggiungi --live per eseguire.")
        return 0

    base_fee = w3.eth.get_block("latest").get("baseFeePerGas", 100_000_000)
    tx = contract.functions.depositV3(*args).build_transaction({
        "from": ADDR,
        "value": amount_wei,
        "gas": 400_000,
        "maxFeePerGas": int(base_fee * 2),
        "maxPriorityFeePerGas": w3.to_wei(0.01, "gwei"),
        "nonce": w3.eth.get_transaction_count(ADDR),
        "chainId": 42161,
    })
    signed = w3.eth.account.sign_transaction(tx, KEY)
    h = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"\nTX inviata: {h.hex()}")
    rc = w3.eth.wait_for_transaction_receipt(h, timeout=180)
    print(f"Status: {'OK' if rc.status == 1 else 'FALLITA'}  gas used: {rc.gasUsed}")
    print(f"https://arbiscan.io/tx/{h.hex()}")
    return 0 if rc.status == 1 else 1


if __name__ == "__main__":
    sys.exit(main())
