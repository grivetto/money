#!/usr/bin/env python3
"""
DENARO MARKET TECHNICIAN - Multi-Agent Technical Analyst
Inspired by TradingAgents: generates market regime & signals for other bots.
Runs every 5 minutes, writes state to .tmp/market_state.json
"""
import os, sys, json, time, hmac, hashlib, urllib.parse, requests, logging
from datetime import datetime
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))
API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')
TMP_DIR = os.path.join(BASE_DIR, ".tmp")
STATE_FILE = os.path.join(TMP_DIR, "market_state.json")
os.makedirs(TMP_DIR, exist_ok=True)

LOG_FILE = os.path.join(BASE_DIR, "market_technician.log")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - TECHNICIAN - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()])
logger = logging.getLogger("Technician")

BINANCE = 'https://api.binance.com'

def fetch_klines(symbol='SOLEUR', interval='1h', limit=100):
    r = requests.get(f'{BINANCE}/api/v3/klines', params={'symbol': symbol, 'interval': interval, 'limit': limit}, timeout=10)
    if r.status_code == 200:
        return [[float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])] for k in r.json()]
    return None

def ema(prices, period):
    if len(prices) < period: return None
    k = 2 / (period + 1)
    ema_vals = [sum(prices[:period]) / period]
    for p in prices[period:]:
        ema_vals.append((p - ema_vals[-1]) * k + ema_vals[-1])
    return ema_vals

def rsi(prices, period=14):
    if len(prices) < period + 1: return 50
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [max(d, 0) for d in deltas[-period:]]
    losses = [max(-d, 0) for d in deltas[-period:]]
    avg_g = sum(gains) / period
    avg_l = sum(losses) / period
    if avg_l == 0: return 100
    rs = avg_g / avg_l
    return 100 - (100 / (1 + rs))

def macd(prices):
    if len(prices) < 35: return None, None, None
    ema12 = ema(prices, 12)
    ema26 = ema(prices, 26)
    if not ema12 or not ema26: return None, None, None
    macd_line = [ema12[i] - ema26[i] for i in range(min(len(ema12), len(ema26)))]
    signal = ema(macd_line, 9)
    if not signal: return None, None, None
    return macd_line[-1], signal[-1], macd_line[-1] - signal[-1]

def atr(klines, period=14):
    if len(klines) < period + 1: return None
    trs = []
    for i in range(1, len(klines)):
        h, l, pc = klines[i][1], klines[i][2], klines[i-1][3]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs[-period:]) / period if len(trs) >= period else None

def analyze():
    # Fetch data
    klines = fetch_klines()
    if not klines or len(klines) < 50:
        logger.error(f"Failed to fetch klines: {len(klines) if klines else 0} candles")
        return None

    closes = [k[3] for k in klines]
    current_price = closes[-1]
    highs = [k[1] for k in klines]
    lows = [k[2] for k in klines]

    # EMA50 and EMA200
    ema50 = ema(closes, 50)
    ema200 = ema(closes, 200)
    ema50_v = ema50[-1] if ema50 else current_price
    ema200_v = ema200[-1] if ema200 else current_price

    # RSI
    rsi_v = rsi(closes)

    # MACD
    macd_line, signal_line, histogram = macd(closes)

    # ATR
    atr_v = atr(klines)
    atr_pct = (atr_v / current_price * 100) if atr_v else 1.0

    # Volume analysis
    volumes = [k[4] for k in klines]
    avg_vol = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else sum(volumes) / len(volumes)
    recent_vol = sum(volumes[-5:]) / 5
    vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1.0

    # Price position relative to EMAs
    ema50_dist = (current_price - ema50_v) / ema50_v * 100
    ema200_dist = (current_price - ema200_v) / ema200_v * 100

    # Market regime determination
    score = 0
    if rsi_v > 70: score -= 1  # Overbought, potential reversal
    elif rsi_v < 30: score += 1  # Oversold, potential bounce
    if ema50_dist > 2: score += 2  # Strongly above 50 EMA
    elif ema50_dist < -2: score -= 2  # Strongly below
    if ema200_dist > 3: score += 4  # Long-term bullish
    elif ema200_dist < -3: score -= 4  # Long-term bearish
    if histogram and histogram > 0: score += 1  # MACD bullish
    elif histogram and histogram < 0: score -= 1
    if vol_ratio > 1.5: score += 1  # High volume (confirms trend)
    elif vol_ratio < 0.5: score -= 0.5  # Low volume (weak)

    if score >= 5: regime = "STRONG_BULL"
    elif score >= 2: regime = "BULL"
    elif score <= -5: regime = "STRONG_BEAR"
    elif score <= -2: regime = "BEAR"
    else: regime = "NEUTRAL"

    # Volatility classification
    if atr_pct < 0.8: vol_class = "LOW"
    elif atr_pct < 1.8: vol_class = "NORMAL"
    else: vol_class = "HIGH"

    state = {
        'timestamp': time.time(),
        'datetime': datetime.utcnow().isoformat(),
        'symbol': 'SOL/EUR',
        'price': round(current_price, 2),
        'regime': regime,
        'score': round(score, 1),
        'indicators': {
            'rsi_14': round(rsi_v, 1),
            'ema50': round(ema50_v, 2),
            'ema200': round(ema200_v, 2),
            'ema50_dist_pct': round(ema50_dist, 2),
            'ema200_dist_pct': round(ema200_dist, 2),
            'macd': round(macd_line, 4) if macd_line else None,
            'macd_signal': round(signal_line, 4) if signal_line else None,
            'macd_histogram': round(histogram, 4) if histogram else None,
        },
        'volatility': {
            'atr': round(atr_v, 4) if atr_v else None,
            'atr_pct': round(atr_pct, 2),
            'class': vol_class
        },
        'volume': {
            'avg_20h': round(avg_vol, 2),
            'recent_5h': round(recent_vol, 2),
            'ratio': round(vol_ratio, 2)
        },
        'signals': {
            'allow_grid': regime not in ('STRONG_BEAR', 'BEAR'),
            'allow_sell_grid': regime not in ('STRONG_BULL'),
            'suggested_grid_range': 0.008 if vol_class == 'LOW' else (0.012 if vol_class == 'NORMAL' else 0.018),
            'suggested_base_order': 17.0,
            'caution': 'oversold' if rsi_v < 30 else ('overbought' if rsi_v > 70 else 'none')
        }
    }

    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

    logger.info(f"Regime: {regime} | Score: {score} | RSI: {rsi_v:.0f} | "
                f"EMA50: {ema50_dist:+.1f}% | ATR: {atr_pct:.1f}% | Vol: {vol_ratio:.1f}x")
    logger.info(f"Signals: grid={'OK' if state['signals']['allow_grid'] else 'PAUSE'}, "
                f"sell_grid={'OK' if state['signals']['allow_sell_grid'] else 'PAUSE'}, "
                f"range={state['signals']['suggested_grid_range']*100:.1f}%")

    return state

if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("MARKET TECHNICIAN STARTED")
    analyze()
    logger.info("Analysis complete")
