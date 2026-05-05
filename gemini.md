# GEMINI.md — Grid Bot v4 Specification
## Denaro Trading Infrastructure — Definitive Source of Truth

> "gemini.md is law." — Project Constitution

---

## 1. NORTH STAR

**Goal:** Generare profitto discrezionale tramite grid trading automatizzato su Binance Spot (SOL/EUR), con accounting rigoroso e kill switch che previene perdite catastrophic.

**Obiettivo secondario:** Trasparenza totale su P&L, drawdown, e stato del sistema — report su Telegram ogni ora.

---

## 2. DATA SCHEMA (Input / Output)

### 2.1 Config (grid_config_v4.json)

```json
{
  "symbol": "SOL/EUR",
  "symbol_ws": "soleur",
  "grid_levels": 3,
  "base_order_eur": 50.0,
  "max_total_invested": 150.0,
  "min_order_eur": 10.0,

  "atr_timeframe": "15m",
  "atr_lookback": 14,
  "atr_spacing_factor": 0.5,
  "atr_min_spacing_pct": 0.003,
  "atr_max_spacing_pct": 0.02,

  "profit_per_grid_pct": 0.003,
  "fee_rate": 0.00075,

  "kill_switch": {
    "max_drawdown_pct": 3.0,
    "out_of_bounds_pct": 0.025,
    "trailing_stop_pct": 1.5,
    "trailing_activation_pct": 2.0
  },

  "rebalance": {
    "enabled": true,
    "check_interval_sec": 300,
    "max_age_without_fill_sec": 1800
  }
}
```

**Nota:** Tutte le soglie sono configurabili. Nessun numero magico nel codice.

### 2.2 State (in-memory, serialized to .state.json)

```json
{
  "bot_name": "GridBotV4",
  "started_at": "2026-05-03T00:00:00Z",

  "grid": {
    "buy_levels": [69.50, 69.00, 68.50],
    "sell_levels": [69.72, 69.22, 68.72],
    "buy_amounts": [0.720, 0.725, 0.730],
    "active": false
  },

  "orders": {
    "open_buy_ids": ["a1b2c3", "d4e5f6"],
    "open_sell_ids": ["g7h8i9"],
    "filled": [
      {
        "order_id": "abc123",
        "side": "buy",
        "price": 69.50,
        "amount": 0.720,
        "cost_eur": 50.03,
        "fee_eur": 0.037,
        "filled_at": "2026-05-03T01:00:00Z"
      }
    ]
  },

  "accounting": {
    "peak_portfolio_eur": 228.50,
    "current_portfolio_eur": 224.30,
    "total_invested_eur": 96.00,
    "total_fees_eur": 0.22,
    "net_pnl_eur": -0.87,
    "drawdown_pct": 1.84,
    "win_count": 8,
    "loss_count": 4,
    "round_trips": 12
  },

  "risk": {
    "kill_switch_triggered": false,
    "kill_switch_reason": "",
    "paused": false,
    "pause_reason": "",
    "last_resume_price": 0.0
  },

  "atr": {
    "current": 0.45,
    "current_pct": 0.0063,
    "grid_spacing_pct": 0.0032,
    "calculated_at": "2026-05-03T02:00:00Z"
  },

  "last_sync": "2026-05-03T02:00:00Z",
  "ticks_processed": 14200
}
```

### 2.3 Trade Record (SQLite — trades.db)

```sql
CREATE TABLE trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_instance    TEXT    NOT NULL,       -- "GridBotV4"
    strategy        TEXT    NOT NULL,       -- "grid"
    symbol          TEXT    NOT NULL,       -- "SOL/EUR"
    side            TEXT    NOT NULL,       -- "buy" | "sell"
    order_id        TEXT,
    price           REAL    NOT NULL,
    amount          REAL    NOT NULL,
    cost_eur        REAL    NOT NULL,
    fee_eur         REAL    NOT NULL,
    fee_currency    TEXT    DEFAULT 'EUR',
    pnl_eur         REAL,
    grid_level      INTEGER,
    round_trip_id   TEXT,
    timestamp       DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE round_trips (
    id              TEXT PRIMARY KEY,       -- UUID
    symbol          TEXT NOT NULL,
    buy_order_id    TEXT,
    buy_price       REAL,
    buy_amount      REAL,
    buy_fee_eur     REAL,
    buy_time        DATETIME,
    sell_order_id   TEXT,
    sell_price      REAL,
    sell_amount     REAL,
    sell_fee_eur    REAL,
    sell_time       DATETIME,
    pnl_eur         REAL,
    duration_sec    INTEGER,
    bot_instance    TEXT
);

CREATE TABLE daily_stats (
    date            DATE PRIMARY KEY,
    bot_instance    TEXT,
    symbol          TEXT,
    opening_price   REAL,
    closing_price   REAL,
    trades_count    INTEGER,
    round_trips     INTEGER,
    volume_eur      REAL,
    fees_eur        REAL,
    pnl_eur         REAL,
    drawdown_pct    REAL,
    peak_portfolio  REAL,
    end_portfolio   REAL
);
```

### 2.4 Telegram Alert Payload

```json
{
  "chat_id": "<TELEGRAM_CHAT_ID>",
  "text": "📊 [GridBotV4] 06:00 Report\n━━━━━━━━━━━━━━━━━━\n💶 Portfolio: €224.30\n📈 P&L: -€0.87 | Trades: 12\n📉 Drawdown: 1.84%\n💾 Investito: €96.00\n🌐 SOL/EUR: €71.29\n⚙️ ATR: 0.45€ (0.63%)\n📏 Grid: 3 livelli × €50\n━━━━━━━━━━━━━━━━━━\n✅ Status: OPERATIVO",
  "parse_mode": "MarkdownV2"
}
```

---

## 3. BEHAVIORAL RULES

### 3.1 Kill Switch (obbligatorio, mai disabilitabile da solo)

| Trigger | Azione |
|---------|--------|
| Drawdown > 3% da peak | PAUSA totale, annulla tutti gli ordini, alert Telegram |
| Prezzo fuori range > 2.5% | PAUSA, non annulla ordini (li tiene per recovery) |
| trailing_stop colpito | EXIT completo, chiude tutto |
| 30 min senza fill su ordine attivo | Riemetti ordine (self-healing) |
| Errore API Binance | Retry 3x con backoff esponenziale, poi pausa e alert |

### 3.2 Grid Logic

- **Buy:** prezzi discendenti sotto prezzo attuale
- **Sell:** ogni buy ha esattamente 1 sell corrispondente (stesso importo)
- **Spacing:** `spacing = max(atr_min, min(atr_current_pct * atr_factor, atr_max))`
- **Recentering:** quando sell viene riempito, nuovo buy viene piazzato al livello originale (ciclo chiuso)
- **NO market orders** — mai, per nessuna ragione
- **NO ordini senza fondi** — verifica balance prima di ogni ordine

### 3.3 Accounting Rules

- **Entry fee:** addebita al momento del buy fill
- **Exit fee:** addebita al momento del sell fill
- **P&L round trip:** `sell_proceeds - buy_cost - entry_fee - exit_fee`
- **Drawdown:** `(peak - current) / peak * 100`
- **Peak aggiornato:** solo quando `current > peak`

### 3.4 Alerting Rules

- **Report orario:** 06:00–23:00, solo se drawdown > 0.5% OPPURE stato non-OPERATIVO
- **Kill switch attivato:** alert immediato
- **Rimbalzo da kill switch:** alert quando prezzo rientra in range
- **Zombie order (>30 min):** alert + auto-replace

---

## 4. ARCHITECTURE (3-Layer A.N.T.)

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1: architecture/                                     │
│  ─────────────────────────────────────────────────────────  │
│  SOPs Markdown che definiscono: GOAL → INPUT → TOOL → EDGE │
│  Non contengono codice eseguibile                            │
├─────────────────────────────────────────────────────────────┤
│  LAYER 2: Navigator (denaro_navigator.py)                   │
│  ─────────────────────────────────────────────────────────  │
│  Reasoning: decide quale tool chiamare, in quale ordine,      │
│  in base allo stato. NON esegue logica di trading.          │
│  Routing: riceve tick → aggiorna state → decide azioni       │
├─────────────────────────────────────────────────────────────┤
│  LAYER 3: tools/                                           │
│  ─────────────────────────────────────────────────────────  │
│  atomic_python_scripts.py — testabili, deterministic        │
│  Non chiamano altri tool. Output = dict.                    │
│  .env per credenziali, .tmp/ per intermedi                  │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. PHILOSOPHY

> "Grid Bot v4 è un sistema deterministico. LLMs are probabilistic; business logic must be deterministic."

Qualsiasi logica che non sia esattamente definita in questa spec NON viene implementata.

---

*Last updated: 2026-05-03*
*Author: Hermes*
*Status: BLUEPRINT APPROVED — Awaiting Sergio's confirmation to proceed to Phase L*
