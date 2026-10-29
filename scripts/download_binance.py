#!/usr/bin/env python3
"""Download Binance 8h funding rates for DOT/ADA/LTC/AVAX/DOGE, 12 months.
Usa ccxt.binanceusdm() endpoint pubblico. Nessuna chiave API necessaria.
Formato output: {venue, simbolo, timeframe, tassi:[[ts_ms, tasso],...]}
"""
import json, time, sys, os
import ccxt

SYMBOLS = ["DOT", "ADA", "LTC", "AVAX", "DOGE"]
VENUE = "binance"
TIMEFRAME = "8h"
STEP_MS = 28800000  # 8h in ms

# Binance funding: 00:00, 08:00, 16:00 UTC. Normalizziamo i timestamp.
def normalize_ts(ts):
    """Round to nearest 8h boundary from Unix epoch."""
    return (ts // STEP_MS) * STEP_MS

def fetch_all_funding(exchange, symbol_usdt, since_ms, limit=1000):
    """Paginazione: Binance restituisce max 1000 record per chiamata."""
    all_records = []
    current_since = since_ms
    max_rounds = 20  # safety
    for _ in range(max_rounds):
        batch = exchange.fetch_funding_rate_history(symbol_usdt, since=current_since, limit=limit)
        if not batch:
            break
        all_records.extend(batch)
        last_ts = batch[-1]["timestamp"]
        if len(batch) < limit:
            break
        current_since = last_ts + 1
    return all_records

def download_symbol(exchange, base):
    symbol_usdt = f"{base}/USDT"
    # Start from 12 months ago, matching Bybit window (2025-10-23 ~ 12 mesi)
    since_ms = int(time.time() * 1000) - (365 * 24 * 3600 * 1000)
    # But we want to match Bybit: 2025-10-23T00:00:00Z = 1761177600000
    since_ms = 1761177600000 - 86400000  # 1 day before to catch the first epoch
    print(f"  Fetching {base}/USDT from {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(since_ms/1000))}...", flush=True)
    records = fetch_all_funding(exchange, symbol_usdt, since_ms)
    print(f"  Raw records: {len(records)}", flush=True)

    # Build tassi list [(ts_ms, rate)]
    tassi = []
    seen_ts = set()
    for r in records:
        ts = normalize_ts(r["timestamp"])
        rate = float(r["fundingRate"])
        if ts in seen_ts:
            continue
        seen_ts.add(ts)
        tassi.append([ts, rate])

    # Sort by timestamp
    tassi.sort(key=lambda x: x[0])

    # Filter to match Bybit window: 1761177600000 to 1792684800000
    bybit_start = 1761177600000
    bybit_end = 1792684800000
    tassi = [[ts, rate] for ts, rate in tassi if ts >= bybit_start and ts <= bybit_end]

    print(f"  Filtered records: {len(tassi)}", flush=True)
    if tassi:
        print(f"  First: {tassi[0][0]} ({time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(tassi[0][0]/1000))}), last: {tassi[-1][0]}", flush=True)

    result = {
        "venue": VENUE,
        "simbolo": base,
        "mercato": f"{base}/USDT:USDT",
        "timeframe": TIMEFRAME,
        "richiesta": {"da": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(since_ms/1000)), "a": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())},
        "n": len(tassi),
        "primo_ts": tassi[0][0] if tassi else None,
        "ultimo_ts": tassi[-1][0] if tassi else None,
        "primo": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(tassi[0][0]/1000)) if tassi else None,
        "ultimo": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(tassi[-1][0]/1000)) if tassi else None,
        "tassi": tassi,
    }
    return result

def main():
    outdir = os.path.expanduser("~/hermes-scratch/e9/dati")
    os.makedirs(outdir, exist_ok=True)
    exchange = ccxt.binanceusdm({"enableRateLimit": True})
    for base in SYMBOLS:
        print(f"Downloading Binance funding for {base}...", flush=True)
        data = download_symbol(exchange, base)
        fname = f"binance_{base}_8h.json"
        path = os.path.join(outdir, fname)
        with open(path, "w") as f:
            json.dump(data, f, indent=None, separators=(",", ":"))
        print(f"  Written: {path} ({data['n']} records)", flush=True)
        # Sleep between symbols to be gentle on rate limits
        time.sleep(1)

    # Write MANIFEST for binance files
    import hashlib
    manifest_path = os.path.join(outdir, "binance_MANIFEST.sha256")
    with open(manifest_path, "w") as f:
        for base in SYMBOLS:
            fname = f"binance_{base}_8h.json"
            path = os.path.join(outdir, fname)
            h = hashlib.sha256(open(path, "rb").read()).hexdigest()
            f.write(f"{h}  {fname}\n")
    print(f"\nMANIFEST: {manifest_path}", flush=True)

if __name__ == "__main__":
    main()
