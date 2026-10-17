# Piano dati per ricerca funding/carry delta-neutral

**Obiettivo**: raccogliere e rendere disponibili i dati necessari per testare l'ipotesi di carry delta-neutral su BTC e ETH.

**Fonti primarie**:
- OKX Exchange (via ccxt) per funding rate storico, mark price, index price, e prezzo spot.
- Dati già raccolti dal modulo `raccoglitore_funding.py` e archiviati in `data/funding_xperp.jsonl` (append-only, idempotente).
- Eventuale integrazione con dati OHLCV 1m per calcolare VWAP e slippage realistico (se necessario).

**Schema dei dati** (ogni riga JSONL):
```json
{
  "simbolo": "BTC/USDT:USDT-310404",   // esempio di perpetual future (o perpetual senza scadenza)
  "ts": 1712345678000,                // timestamp ms UTC
  "funding": 0.0001,                  // funding rate per intervallo (8h) come frazione (es. 0.01% = 0.0001)
  "basis_pp": 0.5,                    // basis in punti percentuali: (mark - index)/index * 10000
  "mark_price": 27500.0,              // prezzo mark del perpetual (USD)
  "index_price": 27490.0,             // prezzo index (riferimento spot)
  "fonte": "okx"
}
```
Nota: il simbolo spot è dedotto rimuovendo la parte dopo il secondo ':' o usando un mapping predefinito (BTC/USDT:USDT -> BTC/USDT spot).

**Frequenza**: dati di funding ogni 8 ore (tre volte al giorno). Per mark/index prezzo, assumiamo che siano disponibili ad ogni funding (fetch_funding_rate_history restituisce questi campi).

**Dati mancanti**:
- Se mark_price o index_price mancanti, il basis_pp viene posto a 0 e la strategia non entrerà (richiede basis dentro banda).
- Se funding non finito (NaN/inf) la riga viene scartata durante il caricamento (vedi `raccoglitore_funding.py` e `funding_scan.py`).

**Trasformazioni applicate**:
1. Deduplicazione su (simbolo, ts): se stesso simbolo e ts appare più di una volta, vince l'ultima lettura (append-only idempotente).
2. Ordinamento cronologico crescente per simbolo.
3. Calcolo del basis in frazione: basis = basis_pp / 10000.
4. Conversione del funding rate da frazione per 8h a frazione giornaliera se necessario (ma lo lasciamo per intervallo e gestiamo il conteggio degli intervalli).
5. Allineamento spot/perpetual: per ogni timestamp di funding, prendiamo il prezzo spot più recente disponibile (se non abbiamo spot diretto, usiamo index_price come proxy del spot).

**Archiviazione**:
- File principale: `data/funding_xperp.jsonl` (già esistente, in append-only).
- Backup mensile: `data/archive/funding_xperp_YYYYMM.jsonl` (facoltativo, per reproducibility).
- Log di caricamento: `logs/raccolta_funding.log` (già usato dallo script).

**Accesso nel codice**:
- Funzione `carica_serie_funding(path)` simile a quella in `funding_scan.py` restituisce un dict `{simbolo: SerieFunding}`.
- Per ogni finanziamento, costruiamo un record con timestamp, simbolo, funding, mark, index, basis.

**Qualità e verifica**:
- Ogni caricamento produce un report di copertura (vedi `raccoglitore_funding.report_copertura`) che confronta il range richiesto con le righe presenti.
- Test di unità verificano che dati mancanti vengano gestiti correttamente (ritornano None o salto).
- Nessun dato futuro: tutti i timestamp devono essere <= ora di esecuzione (se usato in backtest, filtriamo per data_fine).

**Nota sulla reproducible ricerca**:
Il piano dati è dichiarato PRIMA di eseguire qualsiasi analisi. Il codice di lettura non deve applicare trasformazioni che utilizzino informazioni future (es. rolling median su dati futuri). Ogni trasformazione deve essere spiegata e versionata.

**File di configurazione dei parametri** (da creare in `src/money/config/`):
- `carry_delta_neutral.json` con soglie: basis_entry_bps, basis_exit_bps, delta_threshold_pct, slippage_per_side, commission_taker, commission_maker, leverage_max, margin_init_pct, min_operazioni_train, ecc.
