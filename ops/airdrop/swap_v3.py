#!/usr/bin/env python3
"""swap_v3.py — Swap ETH->USDC su Base/Optimism via Uniswap V3 SwapRouter02.

Uso:
  swap_v3.py --chain base     --amount 0.001          # dry-run
  swap_v3.py --chain base     --amount 0.001 --live
  swap_v3.py --chain optimism --amount 0.001 --live
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from web3 import Web3

VAULT = Path.home() / ".denaro_vault"
KEY = (VAULT / "airdrop_wallet.key").read_text().strip()
ADDR = (VAULT / "airdrop_wallet.address").read_text().strip()

CFG = {
    "base": {
        "rpc": "https://mainnet.base.org",
        "chain_id": 8453,
        "router": "0x2626664c2603336E57B271c5C0b26F421741e481",
        "weth": "0x4200000000000000000000000000000000000006",
        "usdc": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    },
    "optimism": {
        "rpc": "https://mainnet.optimism.io",
        "chain_id": 10,
        "router": "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
        "weth": "0x4200000000000000000000000000000000000006",
        "usdc": "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85",
    },
}

WETH_ABI = json.loads("""
[{"inputs":[],"name":"deposit","outputs":[],"stateMutability":"payable","type":"function"},
 {"inputs":[{"internalType":"address","name":"spender","type":"address"},{"internalType":"uint256","name":"amount","type":"uint256"}],
  "name":"approve","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"},
 {"inputs":[{"internalType":"address","name":"o","type":"address"}],"name":"balanceOf",
  "outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"}]
""")

ROUTER_ABI = json.loads("""
[{"inputs":[{"components":[
    {"internalType":"address","name":"tokenIn","type":"address"},
    {"internalType":"address","name":"tokenOut","type":"address"},
    {"internalType":"uint24","name":"fee","type":"uint24"},
    {"internalType":"address","name":"recipient","type":"address"},
    {"internalType":"uint256","name":"amountIn","type":"uint256"},
    {"internalType":"uint256","name":"amountOutMinimum","type":"uint256"},
    {"internalType":"uint160","name":"sqrtPriceLimitX96","type":"uint160"}],
   "internalType":"struct IV3SwapRouter.ExactInputSingleParams","name":"params","type":"tuple"}],
  "name":"exactInputSingle","outputs":[{"internalType":"uint256","name":"amountOut","type":"uint256"}],
  "stateMutability":"payable","type":"function"}]
""")

FEE_TIERS = [500, 3000, 10000]


def send(w3, fn, *, value: int = 0, gas: int = 400_000, chain_id: int) -> str:
    base_fee = w3.eth.get_block("latest").get("baseFeePerGas", 1_000_000_000)
    priority = w3.to_wei(0.001, "gwei")
    # Su L2 (Optimism/Base) il base fee può essere ~0: il max fee deve comunque
    # coprire il priority fee, altrimenti il nodo rifiuta la tx.
    max_fee = max(base_fee * 2 + priority, priority * 2)
    tx = fn.build_transaction({
        "from": ADDR, "value": value, "gas": gas,
        "maxFeePerGas": max_fee,
        "maxPriorityFeePerGas": priority,
        "nonce": w3.eth.get_transaction_count(ADDR, "pending"),
        "chainId": chain_id,
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
    ap.add_argument("--chain", required=True, choices=list(CFG))
    ap.add_argument("--amount", required=True, type=float, help="ETH da swappare")
    ap.add_argument("--live", action="store_true")
    a = ap.parse_args()

    c = CFG[a.chain]
    w3 = Web3(Web3.HTTPProvider(c["rpc"], request_kwargs={"timeout": 20}))
    if not w3.is_connected():
        print(f"ERR: RPC {a.chain} non raggiungibile")
        return 1

    amt = w3.to_wei(a.amount, "ether")
    eth_bal = w3.eth.get_balance(ADDR)
    print(f"Chain      : {a.chain} ({c['chain_id']})")
    print(f"ETH        : {w3.from_wei(eth_bal,'ether')}")
    if eth_bal < amt + w3.to_wei(0.0003, "ether"):
        print("ERR: ETH insufficiente (serve margine per gas)")
        return 1

    # 1) wrap
    weth = w3.eth.contract(address=Web3.to_checksum_address(c["weth"]), abi=WETH_ABI)
    wbal = weth.functions.balanceOf(ADDR).call()
    if wbal < amt:
        print(f"[1] wrap {a.amount} ETH -> WETH")
        if a.live:
            send(w3, weth.functions.deposit(), value=amt, gas=80_000, chain_id=c["chain_id"])
        else:
            print("    [dry-run] skip")
    else:
        print("[1] WETH già sufficiente")

    # 2) approve router
    print("[2] approve router")
    if a.live:
        send(w3, weth.functions.approve(Web3.to_checksum_address(c["router"]), amt),
             gas=80_000, chain_id=c["chain_id"])
    else:
        print("    [dry-run] skip")

    # 3) trova fee tier con liquidità (simulazione)
    router = w3.eth.contract(address=Web3.to_checksum_address(c["router"]), abi=ROUTER_ABI)
    chosen = None
    for fee in FEE_TIERS:
        params = {
            "tokenIn": Web3.to_checksum_address(c["weth"]),
            "tokenOut": Web3.to_checksum_address(c["usdc"]),
            "fee": fee,
            "recipient": ADDR,
            "amountIn": amt,
            "amountOutMinimum": 0,
            "sqrtPriceLimitX96": 0,
        }
        try:
            out = router.functions.exactInputSingle(params).call({"from": ADDR, "value": 0})
            if out > 0:
                print(f"[3] fee tier {fee}: {out/1e6:.6f} USDC")
                if chosen is None or out > chosen[1]:
                    chosen = (fee, out)
        except Exception as exc:
            print(f"[3] fee tier {fee}: no route ({str(exc)[:60]})")

    if not chosen:
        print("ERR: nessuna rotta con liquidità")
        return 1

    fee, expected = chosen
    min_out = int(expected * 0.97)  # 3% slippage
    print(f"[4] swap {a.amount} ETH -> USDC (fee {fee}, min {min_out/1e6:.6f})")

    params = {
        "tokenIn": Web3.to_checksum_address(c["weth"]),
        "tokenOut": Web3.to_checksum_address(c["usdc"]),
        "fee": fee,
        "recipient": ADDR,
        "amountIn": amt,
        "amountOutMinimum": min_out,
        "sqrtPriceLimitX96": 0,
    }

    if not a.live:
        print("[DRY-RUN] nessuna tx inviata (aggiungi --live)")
        return 0

    print("[5] invio swap...")
    txh = send(w3, router.functions.exactInputSingle(params), gas=350_000, chain_id=c["chain_id"])
    explorer = {"base": "https://basescan.org", "optimism": "https://optimistic.etherscan.io"}[a.chain]
    print(f"\nSwap: {explorer}/tx/{txh}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
