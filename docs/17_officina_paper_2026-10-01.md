# Officina paper & ruoli delle 3 macchine — 01/10/2026

## Foto rapida (chi fa cosa)
- **MARCODG1** = LIVE + infra: canary C1 (DOGE carry su OKX main), dashboard/grafana/zabbix/tunnel,
  + officina paper (ADA/ARB/XLM/ALGO trend, simulato).
- **mc2** = ricerca & dati: fabbrica ×20 (tick 15s), raccolta funding P8 (4h), quality shadow JEV (15'),
  TradingAgents advisory (06:10), DSH bridge, A0-MC2, + officina paper (BTC/ETH/SOL/XRP/DOGE/TRX/CRV).
- **nuvola** = officina paper (LINK/AVAX/DOT/UNI/SUI/MINA trend, simulato) + zabbix healer/agent.

## Officina paper (nuova, 01/10) — "le macchine testano, non stanno ferme"
- **Cosa**: gli stessi bot trend della flotta storica, riconvertiti da "live bloccato (fondi 0)" a
  **paper forward-test**: fill SIMULATI (PaperExchange: fee configurabile 0,35%/lato, slippage 0,1%,
  min_notional), prezzi LIVE dal MarketDataHub, candele 1d da REST **pubblico** OKX EEA
  (`PaperExchange.fetch_ohlcv_raw`, nessuna chiave). 17 bot (7 mc2 + 6 nuvola + 4 marcodg1);
  in più resta il paper storico di MARCODG1 (ADA/SOL/XRP).
- **Perché**: i bot erano tutti bloccati dalla guardia equity (conti sub a secco) = zombie che
  tickavano a vuoto. Il paper esercita il codice strategia 24/7 sui prezzi live, senza capitale,
  senza chiavi, senza ordini — ed è il banco di prova forward per i candidati futuri.
- **Dove**: unit systemd con **stessi nomi** (`denaro-node-mc2`, `denaro-node-nuvola-trade`,
  `denaro-node-marcodg1-xrp`) ma ExecStart → `config/node_*_paper.yaml` (capital 25 simulato).
  Backup unit: `/tmp/*.bak-20261001` (mc2/marcodg1) e `~/backup-unit-nuvola-trade-20261001.service`.
- **Health**: `<sym>_<nodo>_live_paper.json` in `denaro/health/` (scrittura a ogni tick).
- **Dashboard flotta (wired 01/10)**: le chip della card «OFFICINA PAPER» leggono le chiavi
  `<nodo>:paper:<SYM>` del payload (17/17 attivi); `node_totals` separa live/paper (equity e
  pnl contano SOLO il live). Aggregator: `PAPER_SOURCES` / `LOCAL_PAPER`. Screenshot: `dash_flotta.png`.
- **Zabbix heartbeat (01/10)**: item `flotta.paper_n` (bot freschi <5m) + `flotta.paper_age_s`
  (età del file più vecchio) su MARCODG1/mc2/nuvola, trigger «bot muti» e «flotta ferma»;
  push dal cron `push_metrics.py` (ogni minuto). Unit: `Restart=always` + `StartLimitIntervalSec=0`.
- **Verifica**: `journalctl -u <unit> | grep precaricate` → "299 barre 1d" per bot; health freschi;
  tick con equity simulata 25.
- **Ritorno al live**: ripuntare ExecStart alla config live (backup) — solo con capitale dedicato
  e autorizzazione owner (regola invariata).

## Zabbix — pulizia (richiesta owner, 01/10)
- **Rimossi**: 17 host `alpha-omega-bot-*` (item+trigger in cascata; problemi attivi 42→8),
  4 item aggregati di flotta morta su `alpha-omega-project` (bot_equity, pnl_total, trades_total,
  win_rate), 2 dashboard vecchie (402/404) → ricostruita una sola **"Denaro"** con problemi +
  capitale + canary C1 + ricerca (raccolta/fabbrica).
- **Tenuti**: 3 host nodo, alpha-omega-project (equity + price.*), canary/raccolta/fabbrica/svc.*,
  Zabbix Server. Trigger "equity < 50€" verificato valido (project.equity).
- **Codice allineato**: `zabbix/push_metrics.py` (MARCODG1) senza push verso target storici;
  cron `zabbix_bots.py` (mc2) disattivato con nota. Backup pre-stato: `/tmp/zabbix_dump.json`.
