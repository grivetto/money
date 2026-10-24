#!/usr/bin/env python3
"""bridge_weth.py — Wrap ETH->WETH su Arbitrum e bridge WETH via Across.

Percorso collaudato: inputToken=WETH Arbitrum, outputToken=WETH destinazione,
msg.value=0 (l'ETH nativo è già wrappato).

Uso:
  bridge_weth.py --dest base --amount 0.004            # dry-run
  bridge_weth.py --dest base --amount 0.004 --live     # esegue
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
WETH_ARB = "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1"
WETH_L2 = "0x4200000000000000000000000000000000000006"  # Base e Optimism

DEST_CHAIN_ID = {"base": 8453, "optimism": 10}

WETH_ABI = json.loads("""
[{"inputs":[],"name":"deposit","outputs":[],"stateMutability":"payable","type":"function"},
 {"inputs":[{"internalType":"address","name":"spender","type":"address"},{"internalType":"uint256","name":"amount","type":"uint256"}],
  "name":"approve","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"},
 {"inputs":[{"internalType":"address","name":"owner","type":"address"}],"name":"balanceOf",
  "outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
 {"inputs":[{"internalType":"address","name":"spender","type":"address"},{"internalType":"address","name":"owner","type":"address"}],
  "name":"allowance","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"}]
""")

SPOKE_ABI = json.loads("""
[{"inputs":[{"internalType":"address","name":"depositor","type":"address"},
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
  "name":"depositV3","outputs":[],"stateMutability":"nonpayable","type":"function"}]
""")


def quote(dest_id: int, amount_wei: int) -> dict:
    url = ("https://app.across.to/api/suggested-fees"
           f"?inputToken={WETH_ARB}&outputToken={WETH_L2}"
           f"&originChainId=42161&destinationChainId={dest_id}"
           f"&amount={amount_wei}&recipient={ADDR}")
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8.5.0",
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def send(w3, fn, *, value: int = 0, gas: int = 300_000) -> str:
    base_fee = w3.eth.get_block("latest").get("baseFeePerGas", 100_000_000)
    tx = fn.build_transaction({
        "from": ADDR, "value": value, "gas": gas,
        "maxFeePerGas": int(base_fee * 2),
        "maxPriorityFeePerGas": w3.to_wei(0.01, "gwei"),
        "nonce": w3.eth.get_transaction_count(ADDR),
        "chainId": 42161,
    })
    signed = w3.eth.account.sign_transaction(tx, KEY)
    h = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"    tx: {h.hex()}")
    rc = w3.eth.wait_for_transaction_receipt(h, timeout=180)
    print(f"    {'OK' if rc.status == 1 else 'FALLITA'} (gas {rc.gasUsed})")
    if rc.status != 1:
        raise RuntimeError("transazione fallita")
    return h.hex()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", required=True, choices=list(DEST_CHAIN_ID))
    ap.add_argument("--amount", required=True, type=float)
    ap.add_argument("--live", action="store_true")
    a = ap.parse_args()

    w3 = Web3(Web3.HTTPProvider(RPC))
    if not w3.is_connected():
        print("ERR: RPC Arbitrum non raggiungibile")
        return 1

    amt = w3.to_wei(a.amount, "ether")
    dest_id = DEST_CHAIN_ID[a.dest]
    weth = w3.eth.contract(address=Web3.to_checksum_address(WETH_ARB), abi=WETH_ABI)
    spoke = w3.eth.contract(address=Web3.to_checksum_address(SPOKE_POOL), abi=SPOKE_ABI)

    eth_bal = w3.eth.get_balance(ADDR)
    weth_bal = weth.functions.balanceOf(ADDR).call()
    print(f"Wallet     : {ADDR}")
    print(f"ETH (Arb)  : {w3.from_wei(eth_bal,'ether')}")
    print(f"WETH (Arb) : {w3.from_wei(weth_bal,'ether')}")

    # 1) wrap se WETH insufficiente
    need_wrap = max(0, amt - weth_bal)
    if need_wrap > 0:
        print(f"\n[1] Wrap {w3.from_wei(need_wrap,'ether')} ETH -> WETH")
        if need_wrap + w3.to_wei(0.0005, "ether") > eth_bal:
            print("ERR: ETH insufficiente per wrap + gas")
            return 1
        if a.live:
            send(w3, weth.functions.deposit(), value=need_wrap, gas=80_000)
        else:
            print("    [dry-run] skip")
    else:
        print("\n[1] WETH sufficiente, nessun wrap")

    # 2) approve SpokePool
    allowance = weth.functions.allowance(ADDR, SPOKE_POOL).call()
    print(f"\n[2] Allowance SpokePool: {w3.from_wei(allowance,'ether')} WETH")
    if allowance < amt:
        if a.live:
            send(w3, weth.functions.approve(Web3.to_checksum_address(SPOKE_POOL), amt), gas=80_000)
        else:
            print("    [dry-run] serve approve")

    # 3) bridge
    q = quote(dest_id, amt)
    fee = int(q["totalRelayFee"]["total"])
    out = amt - fee
    relayer = q.get("exclusiveRelayer") or "0x0000000000000000000000000000000000000000"
    ts = int(q["timestamp"])
    print(f"\n[3] Bridge {a.amount} WETH -> {a.dest} (chain {dest_id})")
    print(f"    fee   : {fee/1e18:.9f} ETH ({fee/amt*100:.4f}%)")
    print(f"    ricevi: {out/1e18:.9f} WETH")
    print(f"    fill  : {q['estimatedFillTimeSec']}s")

    # Across richiede fillDeadline <= quoteTimestamp + 21600 (6h): usiamo il
    # timestamp della quote, non 'now', altrimenti InvalidFillDeadline.
    fill_deadline = max(int(time.time()) + 600, ts + 21600)

    call_args = [
        Web3.to_checksum_address(ADDR), Web3.to_checksum_address(ADDR),
        Web3.to_checksum_address(WETH_ARB), Web3.to_checksum_address(WETH_L2),
        amt, out, dest_id, Web3.to_checksum_address(relayer),
        ts, fill_deadline, 0, b"",
    ]
    try:
        spoke.functions.depositV3(*call_args).call({"from": ADDR})
        print("    simulazione: OK")
    except Exception as exc:
        print(f"    simulazione FALLITA: {exc}")
        return 1

    if not a.live:
        print("\n[DRY-RUN] nessuna transazione inviata (aggiungi --live)")
        return 0

    print("\n[4] Invio deposito...")
    txh = send(w3, spoke.functions.depositV3(*call_args), gas=400_000)
    print(f"\nBridge inviato: https://arbiscan.io/tx/{txh}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
