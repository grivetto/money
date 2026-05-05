# STRATEGIA DI PROFITTO DENARO

## 🎯 OBBIETTIVI
- Massimizzare profitto con capitale limitato (~€15-50/node)
- Minimizzare rischi con protezione capitale
- Automatizzare operazioni con strategia quantitativa

## 📊 CONFIGURAZIONI OTTIMIZZATE
- MAX_TRADE_EUR: 10.0€ (massimo per trade)
- MIN_TRADE_EUR: 5.0€ (minimo per trade)
- RSI_OVERSOLD: 25 (sensibilità compra)
- RSI_BUY_MAX: 75 (sensibilità vendita)
- SYMBOLS: ["ETHEUR", "BNBEUR"] (concentrazione alta liquidità)
- VOLUME_MULTIPLIER: 1.5 (maggior sensibilità volume)

## ⚡ STRATEGIA OPERATIVA
1. **Monitoraggio iniziale** (prima ora)
2. **Verifica trades.db** (dopo primo trade)
3. **Ottimizzazione** (ogni 2 ore se necessario)
4. **Allerta** (se profitto < 0.5€ per 30 minuti)

## 📉 PROTEZIONE CAPITALE
- Buffer 1% su trade_amount
- Cancel open orders prima di ogni trade
- Stop loss automatico su posizioni
- Solo trade su ETHEUR/BNBEUR

## 📈 INDICATORI DI SUCCESSO
- Trade completati con profitto positivo
- trades.db creato e crescente
- Nessun errore di balance (-2010)
- Balance EUR stabile o in crescita

## 🚨 ALLARME
Se:
- Nessun trade dopo 1 ora
- Errore -2010 persistente
- Balance EUR < 10€ per 2 ore
- trades.db non si aggiorna per 30 minuti

Allora:
1. Riavvia bot con configurazione originale
2. Verifica connessione Binance
3. Verifica API Keys