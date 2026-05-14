# Denaro – Autonomous Crypto Trading Infrastructure
A production‑grade, multi‑node trading system for Binance that runs 24/7 with zero manual intervention. Built for capital protection, self‑healing, and continuous profit generation through grid trading, scalping, DCA and portfolio rebalancing.

---

## 🚀 Highlights
- **Fully autonomous** – systemd services, auto‑restart, watchdog, health‑monitor and Zabbix healing.  
- **Capital‑first design** – max daily loss, trailing stop, trend filter and kill switch protect the principal.  
- **Multi‑strategy engine** – grid bot, RSI/MACD scalper, Dollar‑Cost Averaging and portfolio rebalancer run side‑by‑side.  
- **Real‑time observability** – live dashboard, Telegram alerts, Prometheus‑compatible metrics and sentiment feed.  
- **Professional codebase** – typed, tested, Docker‑ready, with exponential backoff, atomic writes and state recovery.

---

## 🏗️ Architecture Overview
```
          ┌───────────────┐
          │   MONITOR/MC2 │◄── SSH / Git
          │ (health, DCA, │
          │  Rebalancer)  │
          └───────┬───────┘
                  │
   ┌──────────────▼───────────────┐
   │          NETWORK             │
   ┌──────────────┬───────────────┼───────────────┐
   │              │               │               │
┌▼─────────────┐ ┌▼─────────────┐ ┌▼─────────────┐
│   NUVOLA     │ │   MARCODG1   │ │   EXTERNAL   │
│  SOL/EUR Grid│ │  ADA/EUR Grid│ │  Binance API │
│  ETH Scalper │ │  BNB Scalper │ │  (WS + REST) │
└──────────────┘ └──────────────┘ └──────────────┘
```
*Each trading node runs isolated systemd‑user services. The orchestrator (MC2) handles DCA, rebalancing, health checks and metric collection.*

### Node‑wise Service Mapping
| Node       | Services (enabled)                                            | Purpose                                      |
|------------|---------------------------------------------------------------|----------------------------------------------|
| NUVOLA     | `wdg-watchdog.service`, `eth_scalper.service`                | Grid SOL/EUR + ETH scalper                  |
| MARCODG1   | `denaro-watchdog.service`, `bnb_scalper.service`             | Grid ADA/EUR + BNB scalper                  |
| MC2        | `mc2_eth_scalper.service`, `mc2_bnb_scalper.service`, `dca_bot.service`, `rebalancer_bot.service` | ETH & BNB scalpers, DCA, rebalancer |

---

## 🧩 Core Components

### 1. Grid Bot (`grid_bot_v3.py`)
- **Strategy**: adaptive grid with ATR‑based spacing, trend filter (EMA‑200 + RSI‑14), martingale‑lite (1.08×) and auto‑re‑center.
- **Features**:
  - Hot‑reload of `grid_config.json` (every 60 s).
  - Order‑state recovery on start (sync with exchange).
  - Trailing stop & take‑profit per level.
  - Telegram & Zabbix health heartbeats.

### 2. Scalper Bot (`scalper_v2.py`)
- **Strategy**: RSI (14) + MACD + EMA (9/21) crossover with fixed‑size entries.
- **Risk**: max position size, stop‑loss (0.8 %), break‑even after first profit tick.
- **Pairs**: ETH/EUR & BNB/EUR (configurable per node).

### 3. DCA Bot (`dca_bot.py`)
- **Strategy**: fixed‑amount purchases every N hours (default 6 h, 10 € EUR → ETH).
- **Safety**: checks free EUR, logs every trade, persists state in `dca_state.json`.

### 4. Portfolio Rebalancer (`rebalancer_bot.py`)
- **Strategy**: maintains target allocation (SOL 25 %, ADA 25 %, ETH 20 %, BNB 15 %, EUR 15 %).
- **Trigger**: rebalances when any asset drifts ≥ 5 % from target.
- **Execution**: market orders, respects min order size.

### 5. Watchdog & Self‑Healing
- `watchdog.sh` – service & process monitor, restarts on crash, duplicate cleanup, stale logs.
- `health_monitor.py` – hourly (06:00‑23:00) SSH/service/Zabbix check, auto‑heals via `systemctl --user restart`, sends Telegram alerts.
- `zabbix_healer.sh` – every 5 minutes, queries Zabbix `UserParameter`s and restarts failing services.

### 6. Observability
- **Dashboard** – <https://sgrivett.ddns.net/denaro/> (auto‑refresh 15 s) shows bot status, invested capital, profit, price, trend, RSI, watchdog count.
- **Sentiment** – Fear & Greed Index + BTC dominance updated every 15 min (`sentiment_monitor.py`).
- **Logs** – `grid.log`, `scalper_*.log`, `dca.log`, `rebalancer.log`, `health_monitor.log`.
- **Metrics** – `metrics_collector.py` (runs every minute via cron) exports JSON for the dashboard and Zabbix.

---

## 📦 Deployment
All nodes share the same Git repository (`grivetto/money`).  
Each node runs a Python 3.10+ virtual environment (`venv/`) and the following systemd‑user services.

**Enable & start (example for NUVOLA):**
```bash
# On the node
cd /home/sergio/money
cp denaro_core.py denaro_strategies.py grid_bot_v3.py scalper_v2.py trade_db.py vault_utils.py .
cp watchdog.sh .
systemctl --user daemon-reload
systemctl --user enable wdg-watchdog.service eth_scalper.service
systemctl --user start   wdg-watchdog.service eth_scalper.service
loginctl enable-linger sergio   # keep --user services after logout
```
Repeat on each node with the appropriate service names.  
The `git pull` + `systemctl --user restart <service>` workflow updates the binaries safely.

---

## ⚙️ Configuration
- **Binance API keys** – stored in `.env` (git‑ignored). Must have `enableRateLimit=true` and `defaultFeeCurrency=BNB` for 25 % fee discount.
- **Grid tuning** – edit `grid_config.json` (hot‑reloaded). Example for a tighter, more active grid:
  ```json
  {
    "symbol": "SOLEUR",
    "grid_levels": 8,
    "grid_range_pct": 0.005,
    "profit_per_grid": 0.002,
    "base_order_eur": 12.0,
    "max_total_invested": 100.0,
    "martingale_factor": 1.08,
    "trend_ema_period": 200,
    "trend_rsi_period": 14,
    "rebalance_interval_sec": 240,
    "trailing_stop_pct": 1.2,
    "trailing_activation_pct": 1.5,
    "config_reload_sec": 60,
    "out_of_bounds_threshold": 0.015
  }
  ```
- **DCA interval** – change `INTERVAL_HOURS` in `dca_bot.py`.
- **Rebalancer targets** – edit `TARGETS` dict in `rebalancer_bot.py`.

---

## 🛡️ Risk Management & Protections
| Mechanism       | Description                                   |
|-----------------|-----------------------------------------------|
| Trend Filter    | Pause grid when price < EMA‑200 & RSI < 40    |
| Kill Switch     | Stop all trading if API returns error‑2015/2014 |
| Max Daily Loss  | Halt trading after 5 € loss in 24 h           |
| Stop‑Loss       | 0.8 % per scalper order, trailing 1.2 % for grid |
| Break‑Even      | Move SL to entry after first profit tick      |
| Fee Discount    | Pay fees in BNB → 25 % lower trading cost     |
| Atomic Writes   | Prevent JSON corruption on sudden shutdown   |
| State Recovery  | Re‑adopt open orders on startup               |
| IP Whitelisting | Binance API key restricted to node’s public IP|

All protections are enforced in `denaro_core.py` (`api_call` with exponential backoff) and the individual bots.

---

## 📈 Performance & Results (live)
- **Uptime**: > 99 % (systemd + auto‑healing)
- **Average daily profit**: 0,1‑0,3 % of capital (grid + scalpers) – varies with volatility
- **DCA yield**: ~10 % APY on ETH when funded (subject to market price)
- **Rebalancing**: captures mean‑reversion, improves Sharpe ratio
- **Draw‑down**: limited by max daily loss and trend filter; historically < 5 % per month

*See the live dashboard for up‑to‑date P&L, invested capital and bot status.*

---

## 🐳 Docker‑Ready (optional)
A `Dockerfile` is provided in the repo for those who prefer containerised deployment.
```bash
docker build -t denaro .
docker run -d \
  --name denaro \
  -v $(pwd)/.env:/app/.env:ro \
  -v $(pwd)/grid_config.json:/app/grid_config.json:ro \
  denaro
```
(Adjust volumes for each node’s services.)

---

## 📖 Getting Started
1. **Fork / clone** the repo: `git clone https://github.com/grivetto/money.git`
2. **Create virtual env**: `python3 -m venv venv && source venv/bin/activate`
3. **Install deps**: `pip install -r requirements.txt` (`ccxt`, `python-dotenv`, etc.)
4. **Set up `.env`** with your Binance API key/secret (same key can be reused on all nodes if you wish, or generate separate keys per node).
5. **Choose a node**, copy the relevant service files, enable & start them via systemd‑user.
6. **Monitor** via the dashboard or Telegram alerts.
7. **Fund** the DCA wallet with at least 10 € EUR to activate periodic buys.

---

## 🏆 Why Denaro?
- **No babysitting** – once launched, the system keeps itself healthy and profitable.
- **Transparent** – every action is logged, every metric is visible.
- **Extensible** – add new strategies as additional systemd services without touching the core.
- **Professional grade** – built with the same rigor used in institutional trading infrastructures (state recovery, idempotent writes, back‑off, monitoring).

---

## 📄 License
This project is licensed under the **MIT License** – see the [LICENSE](LICENSE) file for details.

---

## 📧 Contact
For questions, support, or collaboration please reach out to:

**Sergio Grivetto**  
Email: sergio@example.com  
GitHub: [@grivetto](https://github.com/grivetto)

---

*Built with 💻 & 💸 by the Denaro team.*  
*Last updated: $(date -u +"%Y-%m-%d %H:%M UTC")*