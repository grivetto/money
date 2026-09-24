#!/usr/bin/env python3
"""
TOOL: telegram_alert
Layer 3 — Send formatted alert to Telegram
Input:  alert_type (report/kill_switch/warning/status)
       text (str)
       parse_mode (str, optional)
Output: dict with send result
Env:    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
import sys
import json
import urllib.request
import urllib.parse
from pathlib import Path

ENV_PATH = Path(__file__).parent.parent / ".env"

def load_env():
    from dotenv import load_dotenv
    load_dotenv(ENV_PATH)
    return __import__('os').getenv('TELEGRAM_BOT_TOKEN'), __import__('os').getenv('TELEGRAM_CHAT_ID')

def send_alert(token, chat_id, text, parse_mode="MarkdownV2"):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())

def format_report(state, market):
    """Format hourly report"""
    acc = state.get('accounting', {})
    grid = state.get('grid', {})
    risk = state.get('risk', {})

    status = "OPERATIVO"
    if risk.get('kill_switch_triggered'):
        status = "KILL SWITCH ATTIVO"
    elif risk.get('paused'):
        status = f"PAUSA: {risk.get('pause_reason', '?')}"

    spacing = state.get('atr', {}).get('grid_spacing_pct', 0)
    levels = len(grid.get('buy_levels', []))

    lines = [
        f"📊 [GridBotV4] Report {market.get('timestamp', '')[:16]}Z",
        "━━━━━━━━━━━━━━━━━━",
        f"💶 Portfolio: €{acc.get('total_eur', 0):.2f}",
        f"📈 P&L: €{acc.get('net_pnl_eur', 0):+.2f} | Trades: {acc.get('round_trips', 0)}",
        f"📉 Drawdown: {acc.get('drawdown_pct', 0):.2f}%",
        f"💾 Investito: €{acc.get('total_invested_eur', 0):.2f}",
        f"🌐 SOL/EUR: €{market.get('last', 0):.2f}",
        f"⚙️ ATR: {market.get('atr', 0):.2f}€ ({market.get('atr_pct', 0):.2%})",
        f"📏 Grid: {levels} livelli × {acc.get('base_order_eur', 0):.0f}€ (spaced {spacing:.2%})",
        "━━━━━━━━━━━━━━━━━━",
        f"✅ Status: {status}",
    ]
    return "\n".join(lines)

def main():
    alert_type = sys.argv[1] if len(sys.argv) > 1 else "status"
    text = sys.argv[2] if len(sys.argv) > 2 else ""

    token, chat_id = load_env()
    if not token or not chat_id:
        print(json.dumps({"error": "Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID"}))
        return

    if alert_type == "report":
        state_str = sys.argv[3] if len(sys.argv) > 3 else "{}"
        market_str = sys.argv[4] if len(sys.argv) > 4 else "{}"
        state = json.loads(state_str)
        market = json.loads(market_str)
        text = format_report(state, market)

    try:
        result = send_alert(token, chat_id, text)
        print(json.dumps({"ok": True, "msg_id": result.get('result', {}).get('message_id')}))
    except Exception as e:
        print(json.dumps({"error": str(e)}))

if __name__ == "__main__":
    main()
