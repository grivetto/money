# 🚨 RAPPORTO TECNICO - MONEY Trading Bot Analysis
## Per il Team di Sviluppo

**Data:** 2026-05-02  
**Analista:** System Pilot (Stella)  
**Stato:** CRITICO - Azione immediata richiesta  
**Ambiente:** NUVOLA & MARCODG1 (Production)

---

## 🎯 EXECUTIVE SUMMARY

Il sistema di trading **MONEY** è in esecuzione ma **NON STA GENERANDO PROFITTI** perché il bot principale `sniper_squad.py` manca completamente della logica di esecuzione ordini. Il bot riceve dati di mercato in tempo reale ma non effettua operazioni di trading.

### Impatto Finanziario
- Capitale impiegato: ~49 EUR
- Profitto attuale: 0 EUR
- Stato: Fermo funzionale (idle)

---

## 🔴 CRITICAL ISSUES (Bloccanti)

### Issue #1: MISSING TRADING LOGIC IN SNIPER_SQUAD.PY
**Severità:** CRITICAL  
**File:** `sniper_squad.py` (linee 187-203)  
**Stato:** Attivo in produzione

#### Problema
La funzione `process_socket_msg()` riceve dati dal websocket Binance ma **NON ESEGUE NESSUNA OPERAZIONE DI TRADING**:

```python
# ATTUALE (Righe 187-203 in sniper_squad.py)
def process_socket_msg(msg):
    if 'data' not in msg or 'e' not in msg['data']: return
    event = msg['data']
    if event['e'] == 'kline':
        symbol = event['s']
        price = float(event['k']['c'])
        is_closed = event['k']['x']
        volume = float(event['k']['v'])
        
        # Aggiorna klines e volumes
        if symbol in klines:
            klines[symbol].append(price)
        if symbol in volumes:
            volumes[symbol].append(volume)
        
        if is_closed:
            logger.debug(f"[{symbol}] Price: {price}, Vol: {volume}")
        # ❌ MANCA: Logica di entry, risk management, exit, ordini!
```

#### Cosa Manca
1. ❌ Chiamata a `EntryFilters.should_enter()`
2. ❌ Chiamata a `RiskManager.calculate_size()`
3. ❌ Chiamata a `ExitManager.update_position()`
4. ❌ Chiamata a `client.create_order()` per BUY
5. ❌ Chiamata a `client.create_order()` per SELL
6. ❌ Gestione posizioni attive

#### Soluzione Richiesta
Aggiungere nel `process_socket_msg()`:
```python
# PSEUDOCODICE - DA IMPLEMENTARE
if is_closed and symbol not in positions:
    should_enter, reason = EntryFilters.should_enter(symbol, price, klines[symbol], volumes[symbol])
    if should_enter:
        size = risk_manager.calculate_size(balance_cache['EUR'])
        if size > 0:
            order = client.create_order(symbol=symbol, side='BUY', type='MARKET', quoteOrderQty=size)
            positions[symbol] = {'entry': price, 'qty': qty, 'time': datetime.now()}
            save_positions()

if symbol in positions:
    exit_signal = exit_manager.update_position(symbol, positions[symbol]['entry'], price)
    if exit_signal['action'] in ['FULL_EXIT', 'PARTIAL_EXIT']:
        qty = positions[symbol]['qty']
        order = client.create_order(symbol=symbol, side='SELL', type='MARKET', quantity=qty)
        del positions[symbol]
        save_positions()
```

---

### Issue #2: SYNTAX ERROR IN TRIANGULAR_ARBITRAGE_V2.PY
**Severità:** HIGH  
**File:** `triangular_arbitrage_v2.py` (linee 118-147)  

#### Problema
Codice orfano tra due definizioni della stessa funzione:

```python
# RIGA 118 - 121
async def get_order_book(self, symbol: str) -> Tuple[float, float, float]:
    """Fetch best bid, ask, and last price from local memory."""
    data = self.order_book.get(symbol, {"bid": 0.0, "ask": 0.0, "last": 0.0})
    return data["bid"], data["ask"], data["last"]
        if market.get('quoteVolumeBTC', 0) > self.min_volume_btc:  # ❌ ORFANO!
            liquid_pairs.append(sym)                               # ❌ ORFANO!
    # ... altre 15 righe ORFANE!

# RIGA 140 - 147 (DEFINIZIONE DUPLICATA!)
async def get_order_book(self, symbol: str) -> Tuple[float, float, float]:
    """Fetch best bid, ask, and last price."""
    try:
        ticker = await self.client.fetch_ticker(symbol)
        return ticker['bid'], ticker['ask'], ticker['last']
```

#### Effetto
- Il file probabilmente genera `IndentationError` o comportamento indefinito
- Strategia di arbitraggio triangolare non funzionante

#### Soluzione
1. Rimuovere la definizione duplicata
2. Spostare il codice orfano nella funzione corretta (`find_liquid_triangles`)
3. Testare prima del deploy

---

### Issue #3: ENTRY FILTERS TROPPO RIGIDI
**Severità:** MEDIUM  
**File:** `utils/entry_filters.py` (linee 14-38)

#### Problema
I filtri di ingresso sono estremamente restrittivi:

```python
# ATTUALE - Troppo rigido
rsi_ok = 30 < rsi < 70  # Esclude quasi tutto
vol_ok = current_vol > (ma20_vol * 1.5)  # Richiede +50% volume
trend_up = ema50 > ema200  # Richiede 200+ dati storici

if rsi_ok and vol_ok and trend_up:  # AND = tutti devono essere veri
    return True, "STRONG_BUY"
```

#### Effetto
- Sequenza di filtri in AND riduce drasticamente i segnali
- Richiesta di 200+ dati storici per EMA200 (circa 3+ ore di dati 1m)
- Volume 1.5x superiore alla media è raro

#### Soluzione Suggerita
```python
# OPZIONE A: Punteggio ponderato
score = 0
if 30 < rsi < 70: score += 1
if current_vol > ma20_vol * 1.5: score += 1
if ema50 > ema200: score += 1

if score >= 2:  # Almeno 2/3 condizioni
    return True, f"SCORE_{score}"

# OPZIONE B: OR condizionale
if (rsi_ok and vol_ok) or (rsi_ok and trend_up) or (vol_ok and trend_up):
    return True, "CONDITIONAL_BUY"
```

---

## 🟡 HIGH PRIORITY ISSUES

### Issue #4: RISK ENGINE ATR CALCULATION BUG
**Severità:** HIGH  
**File:** `utils/risk_engine.py` (linee 44-48)

#### Problema
```python
if atr_price and atr_price > 0:
    atr_pct = atr_price / total_balance  # ❌ BUG: ATR / Balance ???
    atr_adj = max(0.5, min(2.0, 0.01 / atr_pct))
```

L'ATR dovrebbe essere calcolato come percentuale del prezzo, non del balance:
```python
# CORRETTO
atr_pct = atr_price / current_price  # ATR come % del prezzo
```

#### Effetto
- Position sizing erratico
- Possibile sovrallocazione o sottoallocazione

---

### Issue #5: NO ACTIVE POSITION MONITORING
**Severità:** HIGH  
**File:** `sniper_squad.py`

#### Problema
Il `main()` loop (righe 205-224) non controlla le posizioni:
```python
try:
    while True:
        time.sleep(60)  # ❌ Solo sleep, nessun check!
        gc.collect()
```

#### Effetto
- Posizioni aperte non monitorate per take-profit/stop-loss
- Dipendenza esclusiva dal callback websocket (che non esegue ordini)

---

## 📊 ARCHITECTURE ANALYSIS

### 3-Layer Architecture Review

```
┌─────────────────────────────────────────────────────────────┐
│ LAYER 1: ARCHITECTURE (SOPs)                                │
│ ✅ Risk Management (risk_engine.py)                         │
│ ✅ Exit Strategy (exit_strategy.py)                         │
│ ✅ Entry Filters (entry_filters.py)                         │
│ ❌ NO SOP for Order Execution                               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ LAYER 2: NAVIGATION (Decision)                              │
│ ⚠️ EntryFilters.should_enter() - Presente ma non usata      │
│ ⚠️ RiskManager.calculate_size() - Presente ma non usata     │
│ ⚠️ ExitManager.update_position() - Presente ma non usata    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ LAYER 3: TOOLS (Execution)                                  │
│ ❌ MISSING: Order execution logic                           │
│ ❌ MISSING: Position management loop                        │
│ ✅ Client connection (ma non utilizzato per trading)        │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔧 CORRECTIVE ACTIONS REQUIRED

### Immediate Actions (Oggi)
1. **Fix sniper_squad.py** - Aggiungere logica di trading completa
2. **Fix triangular_arbitrage_v2.py** - Correggere syntax error
3. **Test in paper trading** prima del deploy

### Short-term (Questa settimana)
4. Review entry filter thresholds
5. Fix ATR calculation bug
6. Add position monitoring loop
7. Implementare logging dettagliato dei trade

### Long-term (Prossimo mese)
8. Refactor architettura 3-layer completa
9. Aggiungere test unitari
10. Implementare circuit breakers

---

## 📝 RECOMMENDED CODE FIX

### File: `sniper_squad.py` (Aggiungere dopo linea 203)

```python
def check_and_execute_trades(symbol, price):
    """Controlla se entrare/uscire da una posizione."""
    global positions
    
    # CHECK EXIT per posizioni esistenti
    if symbol in positions:
        entry_price = positions[symbol]['entry']
        exit_signal = exit_manager.update_position(symbol, entry_price, price)
        
        if exit_signal['action'] == 'FULL_EXIT':
            try:
                asset = symbol.replace('EUR', '')
                balance = client.get_asset_balance(asset=asset)
                qty = float(balance['free'])
                
                if qty > 0:
                    order = client.create_order(
                        symbol=symbol,
                        side='SELL',
                        type='MARKET',
                        quantity=round_step(qty, get_step_size(symbol))
                    )
                    pnl = (price - entry_price) / entry_price * 100
                    logger.info(f"🔴 EXIT {symbol} @ {price} | PnL: {pnl:.2f}% | {exit_signal['reason']}")
                    update_daily_mission((price - entry_price) * positions[symbol]['qty'])
                    del positions[symbol]
                    save_positions()
            except Exception as e:
                logger.error(f"Exit error for {symbol}: {e}")
        return
    
    # CHECK ENTRY per nuove posizioni
    if len(positions) >= CONFIG["MAX_CONCURRENT_TRADES"]:
        return
    
    if len(klines[symbol]) < 200:
        return
    
    should_enter, reason = EntryFilters.should_enter(
        symbol, price, list(klines[symbol]), list(volumes[symbol])
    )
    
    if should_enter:
        # Check BTC trend correlation
        btc_trend = get_btc_trend()
        if btc_trend == 'BEARISH':
            logger.debug(f"Skipping {symbol}: BTC trend is bearish")
            return
        
        # Calculate position size
        available = balance_cache['EUR'] - get_vault_locked()
        size = risk_manager.calculate_size(available)
        
        if size < CONFIG["MIN_TRADE_EUR"]:
            logger.debug(f"Skipping {symbol}: Size {size} < min {CONFIG['MIN_TRADE_EUR']}")
            return
        
        try:
            order = client.create_order(
                symbol=symbol,
                side='BUY',
                type='MARKET',
                quoteOrderQty=round(size, 2)
            )
            qty = float(order['executedQty'])
            entry_price = float(order['fills'][0]['price'])
            
            positions[symbol] = {
                'entry': entry_price,
                'qty': qty,
                'time': datetime.now().isoformat(),
                'reason': reason
            }
            
            logger.info(f"🟢 ENTRY {symbol} @ {entry_price} | Qty: {qty} | Reason: {reason}")
            save_positions()
            
        except Exception as e:
            logger.error(f"Entry error for {symbol}: {e}")

# MODIFICARE process_socket_msg():
def process_socket_msg(msg):
    if 'data' not in msg or 'e' not in msg['data']: 
        return
    event = msg['data']
    if event['e'] == 'kline':
        symbol = event['s']
        price = float(event['k']['c'])
        is_closed = event['k']['x']
        volume = float(event['k']['v'])
        
        if symbol in klines:
            klines[symbol].append(price)
        if symbol in volumes:
            volumes[symbol].append(volume)
        
        # ✅ AGGIUNGERE: Esegui trading logic
        if is_closed:
            check_and_execute_trades(symbol, price)
            logger.debug(f"[{symbol}] Price: {price}, Vol: {volume}")
```

---

## 📈 EXPECTED OUTCOME

Dopo l'implementazione delle correzioni:
- **Sniper Squad** inizierà a generare segnali di trading
- **Risk Management** funzionerà correttamente
- **Exit Strategy** gestirà TP/SL automaticamente
- Profitto atteso: 0.5-2% al giorno (basato su configurazione)

---

## 👥 TEAM ACTIONS

| Ruolo | Azione | Priorità |
|-------|--------|----------|
| Senior Dev | Fix sniper_squad.py trading logic | CRITICAL |
| Senior Dev | Fix triangular_arbitrage_v2.py | HIGH |
| QA | Test in paper trading | HIGH |
| DevOps | Deploy su NUVOLA/MARCODG1 | HIGH |
| Risk Manager | Review entry filter thresholds | MEDIUM |

---

**Report Generated:** 2026-05-02 18:45  
**Protocol:** B.L.A.S.T.  
**Analyst:** System Pilot

*"Il codice è come l'umore: può funzionare anche se è rotto, ma prima o poi esplode."* 💥
