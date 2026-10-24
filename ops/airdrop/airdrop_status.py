#!/usr/bin/env python3
"""airdrop_status.py — stato del wallet airdrop su tutte le catene.

Scrive un JSON consumato da /airdrop (dashboard) via /api/airdrop.json.
Ogni catena è indipendente: un RPC giù non azzera le altre.

Uso:
  airdrop_status.py                 # stampa il JSON
  airdrop_status.py --out FILE      # scrive su file (atomico)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

VAULT = Path.home() / ".denaro_vault"
ADDR_FILE = VAULT / "airdrop_wallet.address"

CHAINS = {
    "arbitrum": {
        "rpc": ["https://arb1.arbitrum.io/rpc", "https://arbitrum-rpc.publicnode.com"],
        "chain_id": 42161,
        "explorer": "https://arbiscan.io",
        "usdc": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        "usdc_decimals": 6,
    },
    "base": {
        "rpc": ["https://base-rpc.publicnode.com", "https://mainnet.base.org"],
        "chain_id": 8453,
        "explorer": "https://basescan.org",
        "usdc": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "usdc_decimals": 6,
    },
    "optimism": {
        "rpc": ["https://mainnet.optimism.io", "https://optimism-rpc.publicnode.com"],
        "chain_id": 10,
        "explorer": "https://optimistic.etherscan.io",
        "usdc": "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85",
        "usdc_decimals": 6,
    },
}

ERC20_ABI = json.loads("""
[{"inputs":[{"name":"o","type":"address"}],"name":"balanceOf",
  "outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"}]
""")


def load_address() -> str:
    if ADDR_FILE.is_file():
        return ADDR_FILE.read_text().strip()
    raise SystemExit("ERR: indirizzo wallet non trovato in %s" % ADDR_FILE)


def chain_state(name: str, cfg: dict, addr: str) -> dict:
    """Legge ETH nativo e saldo USDC; degrada con 'error' senza eccezioni."""
    from web3 import Web3

    out = {"chain": name, "chain_id": cfg["chain_id"], "explorer": cfg["explorer"],
           "eth": None, "usdc": None, "error": ""}
    last_err = ""
    for rpc in cfg["rpc"]:
        try:
            w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 12}))
            if not w3.is_connected():
                last_err = "rpc non connesso"
                continue
            out["eth"] = float(w3.from_wei(w3.eth.get_balance(addr), "ether"))
            c = w3.eth.contract(address=Web3.to_checksum_address(cfg["usdc"]), abi=ERC20_ABI)
            raw = c.functions.balanceOf(addr).call()
            out["usdc"] = raw / (10 ** cfg["usdc_decimals"])
            out["rpc_used"] = rpc
            out["error"] = ""
            return out
        except Exception as exc:
            last_err = "%s: %s" % (type(exc).__name__, str(exc)[:120])
    out["error"] = last_err or "nessun RPC disponibile"
    return out


def build(addr: str | None = None) -> dict:
    addr = addr or load_address()
    chains = [chain_state(n, c, addr) for n, c in CHAINS.items()]
    ok = [c for c in chains if c["error"] == ""]
    payload = {
        "object": "denaro.airdrop.status",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "wallet": addr,
        "chains": chains,
        "totals": {
            "eth": round(sum(c["eth"] or 0 for c in ok), 8),
            "usdc": round(sum(c["usdc"] or 0 for c in ok), 6),
        },
        "health": {"chains_ok": len(ok), "chains_total": len(chains),
                   "ok": len(ok) == len(chains)},
    }
    return payload


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="file di output (scrittura atomica)")
    ap.add_argument("--addr", help="indirizzo wallet (default: vault)")
    a = ap.parse_args()

    data = build(a.addr)
    text = json.dumps(data, indent=2, ensure_ascii=False)

    if a.out:
        p = Path(a.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(text + "\n", encoding="utf-8")
        os.replace(tmp, p)
        print("scritto %s (%d catene ok/%d)" % (p, data["health"]["chains_ok"],
                                                data["health"]["chains_total"]))
    else:
        print(text)
    return 0 if data["health"]["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
