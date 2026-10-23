#!/usr/bin/env python3
"""
raccoglitore_l2_okx.py — Raccoglitore L2 order book OKX (BTC-EUR).
Feed websocket pubblico, ricostruzione book, metriche tick-by-tick.
Append-only JSONL, idempotente. Systemd-ready.

Task: Market Making research — misura densità book BTC/EUR su OKX EEA.
Primo passo (read-only, nessuna chiave): raccolta 1 settimana di dati L2.

Output: data/l2/BTC-EUR_YYYY-MM-DD.jsonl
Una riga JSON al secondo con metriche: spread, depth, imbalance.

Uso:
    .venv/bin/python3 scripts/raccoglitore_l2_okx.py

Env vars:
    L2_DATA_DIR   directory output (default: data/l2)
    L2_SYMBOL     simbolo (default: BTC-EUR)
    L2_LOG_LEVEL  INFO|DEBUG (default: INFO)
"""

import asyncio
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Guard clause: questo script NON invia ordini — solo feed pubblico.
# Se eseguito con chiavi, abortisce.
if any(k in os.environ for k in ("OKX_API_KEY", "OKX_SECRET", "OKX_SECRET_KEY",
                                  "OKX_API_KEY_READ", "API_KEY", "API_SECRET")):
    print("[L2] ERR: chiavi API trovate nell'ambiente. Questo script è SOLO feed pubblico. Abortito.", file=sys.stderr)
    sys.exit(1)

# ---- Config ----
SYMBOL: str = os.environ.get("L2_SYMBOL", "BTC-EUR")
DATA_DIR: Path = Path(os.environ.get("L2_DATA_DIR", "data/l2"))
WS_URL: str = os.environ.get("L2_WS_URL", "wss://wseea.okx.com:8443/ws/v5/public")
# EEA: il book che conta è quello su cui opereremmo (host EEA dedicato).

PING_INTERVAL: float = 20.0       # secondi tra ping keep-alive
SNAPSHOT_INTERVAL: float = 1.0    # secondi tra scritture metriche
MAX_BOOK_LEVELS: int = 100        # livelli tenuti in memoria (su 400 dal feed)
RECONNECT_DELAY: float = 3.0      # secondi tra tentativi di riconnessione
DEPTH_THRESHOLDS_BPS: list[int] = [1, 5, 10, 20, 50, 100]

# ---- Log minimale ----
def _log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    print(f"[{ts}] {msg}", file=sys.stderr, flush=True)


# ---- Order Book locale ----
class OrderBook:
    """Ricostruzione locale del book da snapshot + update incrementali."""

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.bids: dict[float, float] = {}   # px -> sz
        self.asks: dict[float, float] = {}
        self.last_ts: int = 0

    def _apply_levels(self, levels: list, side: dict, op: str):
        """Applica livelli: se sz==0 rimuove, altrimenti setta."""
        for level in levels:
            px = float(level[0])
            sz = float(level[1])
            if sz == 0.0:
                side.pop(px, None)
            else:
                side[px] = sz

    def snapshot(self, data: dict):
        """Snapshot iniziale del book."""
        self.bids.clear()
        self.asks.clear()
        self._apply_levels(data.get("bids", []), self.bids, "snapshot")
        self._apply_levels(data.get("asks", []), self.asks, "snapshot")
        self.last_ts = int(data.get("ts", "0"))

    def update(self, data: dict):
        """Aggiornamento incrementale."""
        self._apply_levels(data.get("bids", []), self.bids, "update")
        self._apply_levels(data.get("asks", []), self.asks, "update")
        if "ts" in data:
            self.last_ts = int(data["ts"])

    def best_bid(self) -> tuple[float, float]:
        if self.bids:
            best = max(self.bids.keys())
            return best, self.bids[best]
        return 0.0, 0.0

    def best_ask(self) -> tuple[float, float]:
        if self.asks:
            best = min(self.asks.keys())
            return best, self.asks[best]
        return 0.0, 0.0

    def mid(self) -> float:
        bb, _ = self.best_bid()
        ba, _ = self.best_ask()
        if bb > 0 and ba > 0:
            return (bb + ba) / 2.0
        return 0.0

    def spread_bps(self) -> float:
        mid = self.mid()
        if mid <= 0:
            return 0.0
        bb, _ = self.best_bid()
        ba, _ = self.best_ask()
        return (ba - bb) / mid * 10_000

    def depth_at(self, side: str, threshold_bps: float) -> float:
        """Volume cumulativo entro threshold_bps dal mid."""
        mid = self.mid()
        if mid <= 0:
            return 0.0
        target_distance = threshold_bps / 10_000 * mid
        total = 0.0
        if side == "bid":
            floor = mid - target_distance
            for px in sorted(self.bids, reverse=True):
                if px >= floor:
                    total += self.bids[px]
                else:
                    break
        elif side == "ask":
            ceiling = mid + target_distance
            for px in sorted(self.asks):
                if px <= ceiling:
                    total += self.asks[px]
                else:
                    break
        return total

    def imbalance(self, threshold_bps: float = 50) -> float:
        """Imbalance normalizzato (-1..1). Positivo = più bid."""
        bv = self.depth_at("bid", threshold_bps)
        av = self.depth_at("ask", threshold_bps)
        total = bv + av
        if total > 0:
            return (bv - av) / total
        return 0.0

    def metrics(self) -> dict:
        """Metriche istantanee in dizionario JSON-ready."""
        bb_px, bb_sz = self.best_bid()
        ba_px, ba_sz = self.best_ask()
        mid = self.mid()
        spread = self.spread_bps()

        m = {
            "ts": int(time.time() * 1000),
            "exchange_ts": self.last_ts,
            "mid": round(mid, 2),
            "best_bid": round(bb_px, 2),
            "best_bid_qty": round(bb_sz, 5),
            "best_ask": round(ba_px, 2),
            "best_ask_qty": round(ba_sz, 5),
            # 3 decimali: a 72k€ un tick da 0,1€ vale 0,0014 bps — 1 decimale lo azzererebbe
            "spread_bps": round(spread, 3),
            "spread_abs_eur": round(ba_px - bb_px, 2) if bb_px > 0 else 0.0,
            "ask_bid_bps": round((ba_px / bb_px - 1) * 10_000, 3) if bb_px > 0 else 0.0,
            "n_bid": len(self.bids),
            "n_ask": len(self.asks),
        }

        for th in DEPTH_THRESHOLDS_BPS:
            m[f"depth_bid_{th}bp"] = round(self.depth_at("bid", float(th)), 5)
            m[f"depth_ask_{th}bp"] = round(self.depth_at("ask", float(th)), 5)

        m["imbalance_50bp"] = round(self.imbalance(50), 4)
        m["imbalance_100bp"] = round(self.imbalance(100), 4)

        return m


# ---- Main async ----
async def raccogli(symbol: str, data_dir: Path):
    data_dir.mkdir(parents=True, exist_ok=True)

    book = OrderBook(symbol)
    stop = asyncio.Event()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            # Windows / alcuni runner non supportano add_signal_handler
            pass

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output_path = data_dir / f"{symbol}_{today}.jsonl"

    # Task scrittura periodica
    async def write_metrics():
        nonlocal today, output_path
        n_ticks = 0
        while not stop.is_set():
            try:
                # Controlla cambio giorno
                new_today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                if new_today != today:
                    today = new_today
                    output_path = data_dir / f"{symbol}_{today}.jsonl"

                m = book.metrics()
                m["iso"] = datetime.now(timezone.utc).isoformat()
                with open(output_path, "a") as fh:
                    fh.write(json.dumps(m) + "\n")

                # Heartbeat per la veglia (ogni 10 s): se il file invecchia, allarme
                n_ticks += 1
                if n_ticks % 10 == 0:
                    stato = {
                        "ultimo_ts": m["ts"],
                        "iso": m["iso"],
                        "mid": m["mid"],
                        "spread_bps": m["spread_bps"],
                        "n_bid": m["n_bid"],
                        "n_ask": m["n_ask"],
                        "symbol": symbol,
                    }
                    tmp = data_dir / "l2_stato.json.tmp"
                    with open(tmp, "w") as sf:
                        sf.write(json.dumps(stato))
                    os.replace(tmp, data_dir / "l2_stato.json")

                await asyncio.sleep(SNAPSHOT_INTERVAL)
            except Exception as e:
                _log(f"write_metrics err: {e}")
                await asyncio.sleep(2)

    writer = asyncio.create_task(write_metrics())

    # Loop websocket con reconnect
    try:
        import websockets as ws
    except ImportError:
        _log("FATAL: 'websockets' non installato. Eseguire: pip install websockets")
        sys.exit(2)

    while not stop.is_set():
        try:
            new_today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if new_today != today:
                today = new_today
                output_path = data_dir / f"{symbol}_{today}.jsonl"

            _log(f"Connessione a {WS_URL} per {symbol}")
            async with ws.connect(WS_URL, ping_interval=None, ping_timeout=None, open_timeout=15) as sock:
                # Sottoscrizione books (400 livelli) + trades (aggressore)
                sub_req = {
                    "op": "subscribe",
                    "args": [
                        {"channel": "books", "instId": symbol},
                        {"channel": "trades", "instId": symbol},
                    ],
                }
                await sock.send(json.dumps(sub_req))
                _log(f"Sottoscritto books+trades:{symbol}")

                last_ping = time.monotonic()

                async for raw in sock:
                    if stop.is_set():
                        break

                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    # Eventi di sistema
                    if "event" in msg:
                        evt = msg["event"]
                        if evt == "subscribe":
                            _log(f"Confirmed: {msg.get('arg', {}).get('channel')} / {msg.get('arg', {}).get('instId')}")
                        elif evt == "error":
                            _log(f"WS error: {msg.get('msg')} code={msg.get('code')}")
                        continue

                    # Dati: book o trades
                    arg = msg.get("arg", {})
                    channel = arg.get("channel")

                    if channel == "trades":
                        for tr in msg.get("data", []):
                            try:
                                rec = {
                                    "ts": int(tr.get("ts", 0)),
                                    "px": float(tr.get("px", 0)),
                                    "sz": float(tr.get("sz", 0)),
                                    "side": tr.get("side", ""),
                                    "tradeId": tr.get("tradeId", ""),
                                }
                                trades_path = data_dir / f"{symbol}_trades_{today}.jsonl"
                                with open(trades_path, "a") as tf:
                                    tf.write(json.dumps(rec) + "\n")
                            except (TypeError, ValueError):
                                continue
                        continue

                    if channel != "books":
                        continue

                    data_list = msg.get("data")
                    if not data_list:
                        continue

                    action = msg.get("action", "")
                    payload = data_list[0]

                    if action == "snapshot":
                        book.snapshot(payload)
                        _log(f"Snapshot: {len(book.bids)} bid x {len(book.asks)} ask "
                             f"spread={book.spread_bps():.1f}bps mid={book.mid():.2f}")
                    elif action == "update":
                        book.update(payload)
                    # Altri tipi ignorati

                    # Keep-alive ping (websockets >=14: ping() attende il pong)
                    t = time.monotonic()
                    if t - last_ping > PING_INTERVAL:
                        try:
                            await asyncio.wait_for(sock.ping(), timeout=10)
                            last_ping = t
                        except Exception:
                            _log("Ping timeout, rompo per reconnect")
                            break

        except asyncio.CancelledError:
            break
        except ws.ConnectionClosed as e:
            _log(f"Connessione chiusa [{e.code}]: {e.reason}, reconnect in {RECONNECT_DELAY}s")
            await asyncio.sleep(RECONNECT_DELAY)
        except (OSError, asyncio.TimeoutError) as e:
            _log(f"Rete/timeout: {e}, reconnect in {RECONNECT_DELAY}s")
            await asyncio.sleep(RECONNECT_DELAY)
        except Exception as e:
            _log(f"Errore inatteso {type(e).__name__}: {e}, reconnect in {RECONNECT_DELAY*2}s")
            await asyncio.sleep(RECONNECT_DELAY * 2)

    writer.cancel()
    try:
        await writer
    except asyncio.CancelledError:
        pass

    _log("Raccoglitore fermato.")


def main():
    _log(f"L2 collector start: symbol={SYMBOL} data_dir={DATA_DIR}")
    asyncio.run(raccogli(SYMBOL, DATA_DIR))


if __name__ == "__main__":
    main()