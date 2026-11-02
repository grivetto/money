---
session_id: "20260912_011043_3951bd"
title: "Riassumere contenuto repository alpha omega trading"
source: cli
model: prod
started: 2026-09-12 01:10
ended: 2026-09-12 01:10
end_reason: agent_close
message_count: 4
tool_call_count: 1
estimated_cost_usd: 0.0
cwd: "/home/sergio"
tags: [hermes-history]
---

# Riassumere contenuto repository alpha omega trading
> `20260912_011043_3951bd` · 2026-09-12 01:10 → 2026-09-12 01:10 · source=cli · model=prod

## 🧑 User · 01:10
Guarda qui: https://github.com/grivetto/alpha-omega-trading — riassumi in 3 righe cosa contiene questo repository.

## 🤖 Hermes · 01:10
<details><summary>🧠 Ragionamento</summary>

We need to summarize the repository in 3 lines in Italian. We should fetch repository metadata. Use web_search? Actually we can use terminal to curl GitHub API or clone. Let's fetch README via raw URL. Use terminal with curl.

We'll do: curl -s https://raw.githubusercontent.com/grivetto/alpha-omega-trading/main/README.md

If fails, maybe use GitHub API: https://api.github.com/repos/grivetto/alpha-omega-trading

Let's try both.

We'll need to output three lines.

Proceed with tool calls.



</details>
`tool_calls: terminal`

### 🛠️ tool:terminal · 01:10
```json
{"output": "# Alpha-Omega Trading\n\n<p align=\"center\">\n  <img src=\"assets/banner.svg\" alt=\"Alpha-Omega Trading Banner\" width=\"100%\"/>\n</p>\n\n<h3 align=\"center\">Distributed Algorithmic Trading Fleet & High-Frequency Telemetry</h3>\n\n<p align=\"center\">\n  <i>Multi-node execution engine for OKX and Kraken, backed by strict supervisor throttles, Docker Zabbix monitoring, and staged capital validation.</i>\n</p>\n\n<p align=\"center\">\n  <a href=\"https://www.python.org/\"><img src=\"https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white\" alt=\"Python 3.12\"></a>\n  <a href=\"https://fastapi.tiangolo.com/\"><img src=\"https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white\" alt=\"FastAPI\"></a>\n  <a href=\"https://www.docker.com/\"><img src=\"https://img.shields.io/badge/Docker-Containerized-2496ED?style=flat-square&logo=docker&logoColor=white\" alt=\"Docker\"></a>\n  <a href=\"https://www.zabbix.com/\"><img src=\"https://img.shields.io/badge/Zabbix-7.0_LTS-D40000?style=flat-square&logo=zabbix&logoColor=white\" alt=\"Zabbix 7.0 LTS\"></a>\n  <a href=\"https://ubuntu.com/\"><img src=\"https://img.shields.io/badge/Ubuntu-24.04_LTS-E95420?style=flat-square&logo=ubuntu&logoColor=white\" alt=\"Ubuntu\"></a>\n  <a href=\"https://www.cloudflare.com/\"><img src=\"https://img.shields.io/badge/Cloudflare-Tunnel-F38020?style=flat-square&logo=cloudflare&logoColor=white\" alt=\"Cloudflare\"></a>\n  <a href=\"LICENSE\"><img src=\"https://img.shields.io/badge/License-CC0_1.0-blue.svg?style=flat-square\" alt=\"CC0 License\"></a>\n</p>\n\n<p align=\"center\">\n  <a href=\"README.md\"><b>English</b></a> •\n  <a href=\"README.it.md\"><b>Italiano</b></a> •\n  <a href=\"README.es.md\"><b>Español</b></a> •\n  <a href=\"README.th.md\"><b>ไทย</b></a>\n</p>\n\n---\n\n## 🏛 Architecture & Distributed Fleet Topology\n\nThe system operates across an asymmetric multi-host topology (`nuvola`, `MARCODG1`, and `mc2`). Each machine fills a designated runtime role to maintain continuous operations, resilient data capture, and zero-inbound exposure behind NAT/CGNAT firewalls.\n\n```\n ┌─────────────────────────────────────────────────────────┐\n │                   EXCHANGES LAYER                       │\n │              OKX (EEA)   ·   Kraken REST/WS             │\n └─────────────┬───────────────────────────┬───────────────┘\n               │ CCXT Execution            │ CCXT Execution\n ┌─────────────▼─────────────┐ ┌───────────▼───────────────┐\n │       NODE: mc2           │ │      NODE: MARCODG1       │\n │   (Home Node / CGNAT)     │ │        (Cloud VPS)        │\n │ · denaro-node-mc2         │ │ · denaro-node-trend-live  │\n │ · Docker Zabbix Server    │ │ · Zabbix Push Metrics     │\n │ · Dashboard Web (:8913)   │ │ · Aggregator API (:8912)  │\n └─────────────┬─────────────┘ └───────────┬───────────────┘\n               │                           │\n               └─────────────►◄────────────┘\n                 Reverse SSH Tunnels (autossh)\n                 Zabbix Trapper :10051 / Reverse 2222\n```\n\n### Core Technologies\n| Component | Tech / Framework | Function |\n| :--- | :--- | :--- |\n| **Execution Core** | `Python 3.12`, `AsyncIO`, `CCXT` | Unified node runtime running grid and momentum policies. |\n| **Fleet Network** | `autossh`, `systemd`, `Cloudflare` | Encrypted reverse SSH tunnels (2222/10051/8912) across NATs. |\n| **Telemetry & Alerts** | `Zabbix 7.0 LTS`, `Docker`, `PostgreSQL` | 350+ metric trappers monitoring equity, drawdown, and heartbeats. |\n| **Real-time Dashboard** | `FastAPI` / `HTTP Server`, CSS Neon UI | Live portfolio state and tick health at `web.grivetto.eu`. |\n\n---\n\n## 📖 History & The Reality of Trading (\"La Baracca\")\n\nThis platform was originally christened *\"La Baracca\"* — an honest Italian expression for a makeshift, fragile contraption that always needed something patched or fixed.\n\n### The Lessons of Live Markets\nIn its early days, theoretical backtests suggested easy profits. The reality of live crypto markets quickly taught different lessons:\n- **Fee Drag & Slippage:** Unaccounted exchange fees (maker/taker) and order slippage easily wiped out theoretical grid profits.\n- **API & Regulatory Friction:** EEA regulatory changes, endpoint rate limits, and exchange maintenance spikes caused missed ticks and deadlocks.\n- **Market Asymmetry:** Unchecked buy-ladders during sudden sell-offs resulted in locked capital and structural inventory traps.\n\nRather than abandoning the project, the system was refactored with **rigorous defensive engineering**: anti-deadlock pre-flight filters, sub-account isolation, dynamic supervisor throttles, and automated circuit breakers.\n\n---\n\n## 🚀 Active Work in Progress (Live Stage: 25 + 25 EUR)\n\nWe enforce a strict **data-driven capital progression**. Real funds are kept in small envelopes (~50 EUR total) while statistical criteria are proven:\n\n| Exchange | Target Pair | Mode | Budget | Strategy | Execution Host | Status |\n| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n| **Kraken** | `SOL/EUR` | **Live** | ~12.70 € | Momentum Capture | `MARCODG1` | <img src=\"https://img.shields.io/badge/Active-brightgreen?style=flat-square\" alt=\"Active\"> |\n| **Kraken** | `XRP/EUR` | **Live** | ~12.70 € | Momentum Capture | `MARCODG1` | <img src=\"https://img.shields.io/badge/Active-brightgreen?style=flat-square\" alt=\"Active\"> |\n| **OKX** | `DOGE/EUR` | **Live** | ~12.00 € | Multi-level Grid | `mc2` (`mc2sub1`) | <img src=\"https://img.shields.io/badge/Active-brightgreen?style=flat-square\" alt=\"Active\"> |\n| **OKX** | `SOL/EUR` | **Live** | ~12.00 € | Multi-level Grid | `mc2` (`mc2sub1`) | <img src=\"https://img.shields.io/badge/Active-brightgreen?style=flat-square\" alt=\"Active\"> |\n\n### Staged Scaling Roadmap\n- [x] **Stage 1 (Current):** 4 active live bots (~50 EUR budget). Multi-week observation of real fee drag, fill frequencies, and API stability.\n- [ ] **Stage 2:** Promotion to 100 EUR – 250 EUR total equity upon achieving a sustained Profit Factor > 1.25 and Max Drawdown < 8%.\n- [ ] **Stage 3:** Expansion to 500 EUR with automated dynamic ATR grid spacing and volatility regime detection.\n- [ ] **Stage 4:** Production fleet target (1,000 EUR) across segregated exchange sub-accounts.\n\n---\n\n## 🛡 Risk Management & Defensive Controls\n\n- **Pre-Flight Order Validation:** Anti-deadlock checks inspect free quote equity and order notional before dispatching orders to CCXT.\n- **Supervisor Safe Mode:** Real-time RAM, CPU, and tick-lag monitoring. If resource pressure exceeds thresholds (`caution` -> `safe` -> `emergency`), the supervisor automatically throttles or suspends trading loops.\n- **Sub-Account Isolation:** All live execution runs on dedicated API sub-accounts (`TRENDSUB` on Kraken, `mc2sub1` on OKX), ensuring operational errors can never impact core account assets.\n- **Zero-Secret Commits:** Credentials exist strictly inside server-local `.env` configurations excluded by `.gitignore`.\n\n---\n\n## 🛠 Quick Start\n\n### Installation\n```bash\n# Clone the repository\ngit clone git@github.com:grivetto/alpha-omega-trading.git\ncd alpha-omega-trading\n\n# Create virtual environment & install requirements\npython3 -m venv venv\nsource venv/bin/activate\npip install -r requirements.txt\n\n# Configure environment\ncp .env.example .env\n```\n\n### Running a Node\n```bash\n# Start Kraken trend-following node\npython -m denaro.denaro_node --config config/node_trend_live_kraken.yaml\n\n# Start OKX grid node\npython -m denaro.denaro_node --config config/node_mc2.yaml\n\n# Run test suite\npytest\n```\n\n---\n\n## ⚖️ Disclaimer\n\n**This software is distributed strictly for educational, academic, and research purposes. It is not financial or investment advice.** Cryptocurrency algorithmic trading involves substantial financial risk, including the possible loss of all invested capital. The authors make no representations or warranties regarding system profitability or performance. Never trade with capital you cannot afford to lose.\n\n---\n\n## 📄 License\n\nDedicated to the public domain under Creative Commons Zero (CC0 1.0 Universal). See [LICENSE](LICENSE) for details.", "exit_code": 0, "error": null}
```

## 🤖 Hermes · 01:10
<details><summary>🧠 Ragionamento</summary>

We need to summarize the repository in 3 lines in Italian. We have fetched README content. Need to produce concise 3-line summary.

From README: It's a distributed algorithmic trading fleet, multi-node execution engine for OKX and Kraken, with supervisor throttles, Docker Zabbix monitoring, staged capital validation. Core tech: Python 3.12, AsyncIO, CCXT, autossh, systemd, Cloudflare, Zabbix, FastAPI dashboard. Active live bots with small budgets, risk management, sub-account isolation, etc.

Thus three lines:

1. Alpha-Omega Trading è una piattaforma di trading algoritmico distribuita che opera su più nodi (nuvola, MARCODG1, mc2) per eseguire strategie su exchange OKX e Kraken.
2. Include il core di esecuzione in Python/AsyncIO con CCXT, telemetria tramite Zabbix/Docker, tunnel autossh per comunicazione sicura dietro NAT, e un dashboard FastAPI per il monitoraggio in tempo reale.
3. Attualmente gestisce quattro bot live con piccoli budget (~50 EUR totale) su sottoconti isolati, applicando controlli di pre‑flight, supervisor safe mode e gestione del rischio, con roadmap di scaling basata su performance verificata.

Return that.



</details>
Alpha‑Omega Trading è una piattaforma di trading algoritmico distribuita che opera su più nodi (nuvola, MARCODG1, mc2) per eseguire strategie su exchange OKX e Kraken.  
Include il core di esecuzione in Python/AsyncIO con CCXT, telemetria tramite Zabbix/Docker, tunnel autossh per comunicazione sicura dietro NAT, e un dashboard FastAPI per il monitoraggio in tempo reale.  
Attualmente gestisce quattro bot live con piccoli budget (~50 EUR totale) su sottoconti isolati, applicando controlli di pre‑flight, supervisor safe mode e gestione del rischio, con una roadmap di scaling basata su performance verificata.

