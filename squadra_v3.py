"""
Denaro Squadra v3 — Orchestratore Principale
Carica e coordina tutti i moduli:
- Grid (esistente)
- Flash Crash Hunter
- Pattern Pro
- Funding Rate Sniper
- Cash Bot Auto-Optimizer

Tutti i moduli girano in parallelo usando asyncio.
Ogni nodo carica solo i moduli adatti alla propria potenza di calcolo.
"""
import asyncio, logging, os, sys, json, time
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))
load_dotenv(BASE_DIR / ".env")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(BASE_DIR / "squadra_v3.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("SquadraV3")

# Determina il nodo in base all'hostname
import socket
HOSTNAME = socket.gethostname().lower()


def get_node_config():
    """Configurazione per nodo: carica moduli appropriati"""
    if "mc2" in HOSTNAME:
        return {
            "name": "MC2",
            "modules": ["grid", "flash_crash", "funding_sniper", "profit_sharing"],
            "grid_symbol": "SOL/USDC",
            "grid_capital_usdc": 18.94,
            "grid_levels": 6,
        }
    elif "nuvola" in HOSTNAME:
        return {
            "name": "Nuvola",
            "modules": ["grid", "pattern_pro", "flash_crash"],
            "grid_symbol": "SOL/USDC",
            "grid_capital_usdc": 18.20,
            "grid_levels": 8,
        }
    elif "marcodg1" in HOSTNAME:
        return {
            "name": "MARCODG1",
            "modules": ["grid", "pattern_pro", "cash_bot"],
            "grid_symbol": "ADA/USDC",
            "grid_capital_usdc": 36.31,
            "grid_levels": 8,
        }
    else:
        return {"name": "UNKNOWN", "modules": ["grid"]}


async def main():
    config = get_node_config()
    log.info(f"🚀 Denaro Squadra v3 — {config['name']}")
    log.info(f"Moduli attivi: {', '.join(config['modules'])}")

    # Importa ccxt e connetti
    import ccxt.async_support as ccxt
    api_key = os.getenv("BINANCE_API_KEY")
    secret = os.getenv("BINANCE_API_SECRET")

    exchange = ccxt.binance({
        "apiKey": api_key,
        "secret": secret,
        "options": {"defaultType": "spot"},
        "enableRateLimit": True,
    })
    await exchange.load_markets()
    log.info(f"Connesso a Binance spot")

    tasks = []

    # Modulo: Grid (sempre presente)
    if "grid" in config["modules"]:
        from strategies.grid import GridTraderStrategy

        class SettingsMock:
            grid_symbol = config["grid_symbol"]
            grid_capital = config["grid_capital_usdc"]
            grid_levels = config["grid_levels"]
            grid_range_pct = 1.5
            grid_step_profit_pct = 0.5
            telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "DISABLED")
            telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "0")

        grid = GridTraderStrategy(exchange, SettingsMock)
        tasks.append(grid.run())
        log.info(f"✅ Grid {config['grid_symbol']} avviata")

    # Modulo: Flash Crash Hunter
    if "flash_crash" in config["modules"]:
        sys.path.insert(0, str(BASE_DIR / "squadra"))
        from squadra.flash_crash_hunter import FlashCrashHunter
        crash = FlashCrashHunter(exchange)
        tasks.append(crash.run())
        log.info(f"✅ Flash Crash Hunter avviato")

    # Modulo: Pattern Pro
    if "pattern_pro" in config["modules"]:
        sys.path.insert(0, str(BASE_DIR / "squadra"))
        from squadra.pattern_pro import PatternPro
        pattern = PatternPro(exchange)
        tasks.append(pattern.scan())
        log.info(f"✅ Pattern Pro avviato")

    # Modulo: Funding Sniper (solo su MC2)
    if "funding_sniper" in config["modules"]:
        sys.path.insert(0, str(BASE_DIR / "squadra"))
        from squadra.funding_sniper import FundingSniper
        funding = FundingSniper(exchange)
        tasks.append(funding.run())
        log.info(f"✅ Funding Sniper avviato")

    # Modulo: Cash Bot Auto-Optimizer (solo su MARCODG1)
    if "cash_bot" in config["modules"]:
        # Cash Bot = auto-optimization che gira ogni 24h
        tasks.append(auto_optimize_loop(exchange, config))
        log.info(f"✅ Cash Bot Auto-Optimizer avviato")

    log.info(f"🟢 Squadra v3 online — {len(tasks)} moduli attivi")
    await asyncio.gather(*tasks)


async def auto_optimize_loop(exchange, config):
    """Ogni 24h analizza performance e ottimizza parametri"""
    while True:
        log.info("🔍 Cash Bot: analisi performance in corso...")
        try:
            # Leggi trade history
            from trade_db import TradeDB
            db = TradeDB("denaro")

            # Analizza trade recenti
            recent_trades = db.get_recent_trades(limit=50)
            if recent_trades:
                wins = sum(1 for t in recent_trades if t.get("net_pnl", 0) > 0)
                total = len(recent_trades)
                win_rate = wins / total * 100 if total > 0 else 0
                log.info(f"   Win rate: {wins}/{total} = {win_rate:.1f}%")

                # Suggerisci ottimizzazioni
                if win_rate < 40:
                    log.warning(f"⚠️ Win rate basso ({win_rate:.0f}%) — " +
                                "suggerito: ridurre grid_spacing a 0.12%")
                elif win_rate > 80:
                    log.info(f"✅ Win rate alto ({win_rate:.0f}%) — " +
                             "suggerito: aumentare grid_levels di 2")

                # Salva report
                report = {
                    "date": time.strftime("%Y-%m-%d"),
                    "win_rate": win_rate,
                    "total_trades": total,
                    "pnl": sum(t.get("net_pnl", 0) for t in recent_trades),
                }
                with open(BASE_DIR / "reports/strategy_evaluation_latest.json", "w") as f:
                    json.dump(report, f, indent=2)

        except Exception as e:
            log.error(f"Cash Bot error: {e}")

        log.info("   Prossima analisi tra 24h")
        await asyncio.sleep(86400)  # 24h


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Squadra v3 arrestata")
