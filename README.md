# Denaro — Autonomous Crypto Trading Infrastructure

Multi-node grid trading bot system for Binance, with automated monitoring, self-healing, and capital protection.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│   MC2       │────▶│   NUVOLA     │     │  MARCODG1    │
│  (host)     │     │  SOL/EUR     │     │  ADA/EUR     │
│  monitor+   │     │  watchdog.sh │     │  watchdog.sh │
│  git+ssh    │     │  bot v3      │     │  bot v3      │
└─────────────┘     └──────────────┘     └──────────────┘
```

## Nodes

| Node | Host | User | Pair | Config |
|------|------|------|------|--------|
| NUVOLA | 87.106.3.15 | sergio | SOL/EUR | 5 levels × 20€ = 100€ max |
| MARCODG1 | 87.106.222.123 | marco | ADA/EUR | 6 levels × 20€ = 120€ max |
| MC2 | local | sergio | — | Orchestrator / git / SSH |

## Core Components

### `grid_bot_v3.py`
Main trading bot using grid strategy. Connects to Binance WebSocket for real-time price feeds, maintains buy orders at configurable grid levels, and automatically replaces filled orders. Features:
- Dynamic config reload (hot-reloads `grid_config.json`)
- ATR-based or percentage-based grid spacing
- Trailing stop & take-profit
- Order sync with exchange state

### `watchdog.sh`
Process supervisor running on each trading node. Monitors bot health and restarts on:
- Zero bot processes (crash recovery)
- Multiple bot instances (duplicate cleanup)
- Stale log files (>5 min without updates)
- Self-protection via PID exclusion (`$$`)

### `health_monitor.py`
Centralized health monitoring system running hourly via cron (06:00–23:00):
- Checks SSH connectivity, service status, process counts
- Verifies Zabbix monitoring agent responses
- Auto-heals: restarts dead services, cleans duplicates
- Sends Telegram alerts on critical failures
- Logs to `health_monitor.log`

### `host_guardian.py`
Lightweight sentry that monitors the grid bot process and restarts it if missing. Designed as a safety layer alongside `watchdog.sh`.

## Configuration

Grid parameters are in `grid_config.json` (hot-reloaded every 60s):

```json
{
  "symbol": "SOLEUR",
  "grid_levels": 5,
  "base_order_eur": 20.0,
  "max_total_invested": 100.0,
  "grid_range_pct": 0.008,
  "profit_per_grid": 0.003,
  "trailing_stop_pct": 1.5
}
```

## System Requirements

- Linux server with systemd --user
- Binance API key (stored in `.env`, excluded from git)
- Python 3.10+ virtual environment (`venv/`)
- Zabbix agent for monitoring (optional)
- SSH access between nodes

## Monitoring

- **Cron**: Every hour 06:00–23:00 via `health_monitor.py`
- **Zabbix**: Custom `UserParameter` for `denaro.gridproc` and `denaro.watchdog`
- **Telegram**: Alerts on failures and auto-healing events
- **Logs**:
  - `grid.log` — trading activity
  - `monitor/monitor.log` — watchdog activity
  - `health_monitor.log` — system health checks

## Key Fixes

- **Process persistence**: `systemd --user` services with `Restart=always` masked via `/dev/null` symlink
- **Watchdog self-kill**: PID exclusion with `$$` and `[w]atchdog.sh` bracket pattern
- **Service death on SSH logout**: `loginctl enable-linger` prevents `--user` services from stopping when user sessions end
- **Duplicate bots**: `kill_procs()` in watchdog cleans before starting

## Branch Strategy

Single `main` branch. All development is pushed directly.

## License

Private — Denaro Autonomous Trading Infrastructure
