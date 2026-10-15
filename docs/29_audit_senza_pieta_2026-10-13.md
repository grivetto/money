# 29 — Audit Senza Pietà del Progetto Money (2026-10-13)

Autore: Hermes (Ingegnere Capo / Quant)
Stato: **Fotografia onesta da zero — Codice, Matematica, Infrastruttura, Economia e Nuovo Piano Edge**

---

## Premessa: la risposta alla tua domanda («non siamo capaci?»)

**No: non è incapacità. È che finora abbiamo cercato nel posto sbagliato con un metro tarato male.**
Analizzando `money` da capo, riga per riga, come un revisore esterno che non ha scritto una sola linea di questo repository, emergono **11 lacune concrete** (4 nel motore matematico/statistico di ricerca, 3 nell'architettura di rischio/esecuzione, 4 nell'operatività/economia).

Due di queste lacune sono **bug matematici nel cuore del giudice statistico** (`scansione.py` / `caccia_continua.py` e `cancello.py`) che avrebbero **bocciato anche una strategia realmente profittevole**.

---

## PARTE 1 — Le 4 Lacune Matematiche e di Ricerca (perché 316.728 tentativi hanno dato 0)

### 1. Cortocircuito matematico del DSR in `scansione.py` e `caccia_continua.py`
- **File**: `src/money/ricerca/scansione.py:388-399` e `src/money/ricerca/caccia_continua.py:249-256`.
- **Cosa fa il codice**:
  1. Seleziona il miglior simbolo in **Addestramento (`train`)**.
  2. Prende il risultato **Out-Of-Sample (`oos`)** di quella singola coppia `(config, simbolo)` (che ha `n_oos ≈ 30–40` operazioni).
  3. Gli applica `sharpe_deflazionato(oos_sharpe, n_oos, n_tentativi=316728, var_sharpe_train)`.
- **Perché è sbagliato (doppio errore)**:
  - **Errore A (Selection Bias applicato alla finestra sbagliata)**: Il Deflated Sharpe Ratio di Bailey & López de Prado (2014) corregge lo Sharpe **in-sample** del vincitore scelto fra $N$ prove fatte sullo stesso campione. Se selezioni in Train e verifichi una volta sola in OOS senza scegliere sull'OOS, penalizzare i 35 trade OOS con $N = 316.728$ tentativi di Train (o con $N = 1.888$ in `scansione`) significa pretendere uno **Sharpe per operazione in OOS $\ge 0,752$** ($t\text{-stat OOS} \ge 4,76$ su 40 trade!).
  - **Errore B (Sharpe per operazione a durata variabile invece che Sharpe annualizzato)**: `scansione.py:323` calcola `sharpe(netti)` per trade, non per unità di tempo. Mescolare nella varianza degli Sharpe strategie da 200 trade/anno (`weekday`) e strategie da 8 trade/anno (`sma_cross(50,200)`) distorce `var_sharpe`. E soprattutto: uno Sharpe **per trade** di $0,752$ su 40 operazioni/anno equivale a uno **Sharpe annualizzato di $0,752 \times \sqrt{40} = 4,76$**. Nessun fondo quant al mondo ha Sharpe 4,76 out-of-sample. Il filtro attuale non è «rigoroso»: è **matematicamente impossibile da superare**.

### 2. Doppia sottrazione del pedaggio nel Criterio 8 di `src/money/cancello.py`
- **File**: `src/money/cancello.py:398-403` (`_blocchi_netti`).
- **Cosa fa il codice**: Per contratto (`cancello.py:168, 952`), `esito.ritorni_netti` contiene ritorni **già al netto di fee e slippage**. Ma `_blocchi_netti()`, che decide il Criterio 8 (*indipendenza dai blocchi*), esegue:
  ```python
  pedaggio = esito.pedaggio_per_operazione
  exp_netta = [math.fsum(b) / len(b) - pedaggio for b in blocchi]
  senza = (math.fsum(restanti) / len(restanti) - pedaggio) if restanti else None
  ```
- **Effetto**: **Sottrae il pedaggio una seconda volta**! Qualsiasi strategia che nei blocchi non-migliori abbia un'expectancy netta positiva ma inferiore a $1\times$ il pedaggio viene dichiarata «negativa senza il blocco migliore» e **archiviata per errore**.

### 3. Il motore di backtest (`scansione.simula`) simula un oggetto diverso da quello che va live
- **File**: `src/money/ricerca/scansione.py:108-150`.
- **Cosa fa il codice**: Calcola solo `apertura[i_out] / apertura[i_in] - 1.0`.
  - **Non applica lo stop ATR ($2,5\times$)** che invece `gate_pre_trade` rende **obbligatorio** in produzione.
  - **Non guarda `minimo`/`massimo` intra-barra** né il drawdown mark-to-market intra-trade.
  - Assume la tariffa dei derivati (`okx_eea_con_perp`), ma **non addebita/accredita il funding rate** sui giorni in cui la posizione resta aperta.
  - Risultato: il backtest valuta strategie senza stop e a size fissa, mentre l'esecutore live impone stop ATR a $2,5\times$ e sizing sul rischio.

### 4. Bug di turnover al 100% nello screener `scripts/crosssec_neutral.py` e paradigma di ricerca esaurito
- **File**: `scripts/crosssec_neutral.py:155`.
- **Cosa fa il codice**: Addebita `ribilanci * (2 * costo_giro)` a ogni singolo ribilanciamento, assumendo che a ogni scadenza il **100% del portafoglio long e il 100% del portafoglio short vengano venduti e ricomprati da zero**, anche quando gli stessi simboli restano in top-$k$/bottom-$k$! Con ribilanciamento a 7 giorni e `costo_giro = 0,26%`, addebita **27%/anno** (o 54% su due gambe) di costi fittizi su posizioni che non si sono mosse.
- **Paradigma S1/S3/S4**: Testare 316.728 varianti di incroci di medie mobili (`fast=14, slow=18` vs `fast=15, slow=17`) long-only su singolo simbolo significa cercare autocorrelazione lineare dove il mercato è dominato da regimi.

---

## PARTE 2 — Le 3 Lacune Architetturali (Rischio, Esecuzione, Contabilità)

### 5. Schizofrenia del Rischio: DUE moduli `rischio.py` incompatibili dentro `Esecutore`
- **File**: `src/money/esecuzione/rischio.py` vs `src/money/rischio.py`, chiamati entrambi da `src/money/esecuzione/esecutore.py:175-203`.
- **Il conflitto**:
  1. `Esecutore._controlli_rischio()` chiama `esecuzione/rischio.py:rischio_per_trade()`, che impone **`nozionale <= 2% dell'equity`** (confondendo il *nozionale* della posizione con il *rischio*!). Su 1.100 € di equity, **blocca qualsiasi ordine di nozionale superiore a 22 €**.
  2. Un istante dopo, `Esecutore._gate_pre_trade()` chiama `money/rischio.py:verifica_pre_trade()`, che invece impone **`rischio_su_stop <= 0,25% dell'equity`** e **`nozionale <= 25% dell'equity`** (275 €).
- **Effetto**: Con le regole attuali cablate insieme, `Esecutore` non può mai aprire un ordine da 100 € (né tantomeno da 500 €) perché `esecuzione/rischio.py` taglia il nozionale al 2% dell'equity (22 €).

### 6. Tre percorsi di invio ordini non unificati (`Esecutore`, `Coordinatore`, `canary_carry.py`)
- **File**: `src/money/esecuzione/coordinatore.py`, `src/money/esecuzione/esecutore.py`, `scripts/canary_carry.py`.
- **Il problema**:
  - `Coordinatore` dichiara nel docstring di essere *«l'UNICO componente che invia ordini»* e di verificare l'assenza del kill-switch (Invariante 6), ma nel codice **non controlla mai `MONEY_KILL_SWITCH`**, **non chiama `gate_pre_trade`** e **non chiama `preflight`**.
  - `scripts/canary_carry.py` (ora protetto da `gate_pre_trade`) non usa `Coordinatore`, mantenendo una propria macchina di esecuzione separata.

### 7. `src/money/contabilita.py` è un'isola morta (Dead Wire)
- **File**: `src/money/contabilita.py` (458 righe).
- **Il problema**: È il ledger ufficiale append-only con match FIFO e riconciliazione, ma **nessuno tra `Esecutore`, `Coordinatore` e `canary_carry.py` lo importa o ci scrive dentro**. È testato solo da `tests/test_contabilita.py`.

---

## PARTE 3 — Le 4 Lacune Operative ed Economiche (Live in questo momento)

### 8. `money-banco-secco.service` su MARCODG1 fallisce ogni 5 minuti (`rc=2 NON_FINANZIATO`)
- **Causa misurata**: `deploy/banco/money_banco_secco.py` legge solo i saldi `trading + funding` (= 22,13 €) e **non legge `savings` (Simple Earn)** dove ora risiedono i 1.206,99 USDC. Di conseguenza vede 22,13 € < 100 € dichiarati ed esce con codice di errore `2` ogni 5 minuti.

### 9. Aggregatore locale su `mc2` (`127.0.0.1:8912`) cieco sul Canary
- **Causa misurata**: `ops/aggregator/infra_aggregator.py:849` cerca `/home/marco/canary/canary_state.json` (path di MARCODG1). Su `mc2` (utente `sergio`) restituisce `FileNotFoundError` e vede solo 6 bot paper invece dei 20 visti dal tunnel `[::1]:8912`.

### 10. Processi che girano a vuoto e albero git sporco
- **`caccia_continua.py`**: Lo spazio è `esaurito: True` (run 1070, 316.728 tentativi), ma il cron `*/5` continua a svegliarsi ogni 5 minuti per stampare `spazio esaurito — niente da fare`.
- **`fabbrica-tick.timer`**: Gira ogni **3 secondi** (343.064 tiri!) con la coda ferma e 1 job `spec_fix` bloccato da 4 giorni perché `coda_catena/MOSAICO4_v1.md` ha solo 2/7 sezioni richieste da `spec_lint.py`.
- **`scansione_giornaliera.py`**: Rilancia ogni notte S1 e S3 sugli stessi dati aggiungendo righe duplicate a `prove/REGISTRO_ESPERIMENTI.md`.
- **Git working tree sporco su `mc2`**: 5 file modificati non committati e 5 file untracked in `prove/`.

### 11. L'equazione economica del progetto (`docs/22_costi_progetto.md`)
- **Spese fisse**: 9 €/mese VPS (108 €/anno) + ~22 €/mese AI Pro = ~372 €/anno.
- **Rendita base attuale**: 1.207 USDC in Simple Earn (~5%/anno ≈ **55 €/anno**).
- **Implicazione**: Tenere il capitale base in Earn (Scelta 1) copre già metà del costo delle VPS a **rischio zero**. Per coprire i restanti ~53 €/anno di VPS con i **500 €** di tetto operativo dedicati agli edge, serve un rendimento netto di circa **+11%/anno** sui 500 € (o +5% sull'intero capitale oltre l'Earn). È un obiettivo **realistico e raggiungibile** — non serve il +500% dei sogni da backtest overfittato, serve un +10/+20% annuo pulito e a basso drawdown.

---

## PARTE 4 — Il Nuovo Paradigma di Ricerca Edge (Cosa facciamo adesso)

Smettiamo di cercare incroci di medie mobili su singola candela. Con 500 € di budget massimo per l'edge (e il resto in Earn al 5%), le **4 piste strutturali** dove un retail ben ingegnerizzato può estrarre +10%/+25% annuo netto sono:

1. **Pista E1 — Rotazione Dinamica di Carry / Basis con Pavimento Earn (`Earn + Opportunistic Carry`)**:
   - *Meccanismo*: Il carry *always-on* rende ~5–8%/anno (pari all'Earn, quindi non vale il rischio). Ma il funding sulle altcoin (DOGE, ADA, LINK, XRP, SUI, AVAX) è **fortemente episodico**: durante le fasi di euforia long paga il **20–60% annuo** per settimane.
   - *Regola*: Capitale di default in **Simple Earn (5%)**. Si apre il carry delta-neutral (Spot + Short Perp) **solo** quando il funding persistente (media 3–7 giorni) supera una soglia netta che ripaga i costi di ingresso/uscita in $\le 7$ giorni (es. $> 18\%$ annuo lordo), e si chiude tornando in Earn solo quando il funding medio a 7 giorni scende sotto il tasso Earn. Zero predizione direzionale, pavimento al 5% annuo.

2. **Pista E2 — Cascate di Liquidazione / Capitulation Reversion su Perp (Event-Driven, Bassa Frequenza)**:
   - *Meccanismo*: Quando un perp subisce un crollo violento in poche ore accompagnato da un'esplosione di volume aggressore Sell (liquidazioni forzate price-insensitive) e allargamento estremo rispetto alla media, gli ordini forzati creano un disallineamento temporaneo che rimbalza nelle 4–24 ore successive.
   - *Perché batte le fee*: Fa pochissime operazioni (solo sulle code estreme, $< 2\%$ delle barre), dove il movimento medio atteso è dell'ordine dell'**1,5%–3,0%** contro **0,07%–0,11%** di costo perp. Abbiamo già 59 simboli $\times$ 5 anni a 1h/4h e 30M di tick Bybit per misurarla con stop ATR reale.

3. **Pista E3 — Cross-Sectional Relative Value con Rebalance Pigro (Buffered Rank)**:
   - *Meccanismo*: Correggere il bug del 100% turnover in `crosssec_neutral.py` introducendo **bande di isteresi** (entri se sei nella top-$k$, esci solo se scendi sotto la top-$2k$), abbattendo i costi di transazione del 70–80%, e testare sia **Momentum cross-sectional lento** sia **Short-term Reversal cross-sectional** (comprare i perdenti estremi a 3–7gg contro i vincitori estremi, filtrati per liquidità) in neutralità di dollaro/beta.

4. **Pista E4 — Arbitraggio Statistico di Funding / Basis Cross-Venue (OKX EEA vs Bybit EU)**:
   - *Meccanismo*: Quando l'IP di `mc2` sarà in whitelist su `api.bybit.eu`, misurare i differenziali di funding e di prezzo perp/spot tra OKX EEA e Bybit EU + Bitvavo USDC (0,05% maker).

---

## PARTE 5 — Piano d'Azione Dettagliato (Ordine di Esecuzione)

### Fase 1 — Igiene Immediata e Riparazione dei Bug Strutturali (Subito, in autonomia)
1. **Fix `money-banco-secco` (`deploy/banco/money_banco_secco.py`)**: Includere il saldo **Simple Earn (`savings`)** nel calcolo dell'equity del banco a secco su MARCODG1, così il servizio torna `PASS` (`rc=0`) invece di fallire ogni 5 minuti con `NON_FINANZIATO`.
2. **Fix Bug Criterio 8 in `src/money/cancello.py`**: Rimuovere la doppia sottrazione di `pedaggio` in `_blocchi_netti()` (poiché `ritorni_netti` è già netto) e aggiornare i relativi test.
3. **Fix DSR in `src/money/ricerca/scansione.py`**: Separare chiaramente il DSR in-sample (calcolato su `train` con $N = \text{tentativi train}$) dalla valutazione out-of-sample (dove il numero di prove è solo quello delle selezioni effettivamente portate in verifica, e lo Sharpe è coerente), senza distruggere i test esistenti.
4. **Unificazione Rischio (`src/money/rischio.py` vs `src/money/esecuzione/rischio.py`)**: Allineare `esecuzione/rischio.py` al mandato reale (rischio calcolato sullo stop ATR = 0,25%–2%, tetto nozionale = 25% equity / 500 € max) eliminando il blocco fittizio a 22 € di nozionale.
5. **Spegnimento del rumore a vuoto**: Fermare il cron `*/5` di `caccia_continua` quando `esaurito == True`, sistemare i 5 blocchi mancanti di `coda_catena/MOSAICO4_v1.md` per sbloccare il job in `fabbrica`, e pulire il working tree git.

### Fase 2 — Ricerca Edge di Nuova Generazione (Subito dopo i fix, sui 3 nodi)
6. **Backtest Pista E1 (`scripts/ricerca_carry_dinamico.py`)**: Simulare la rotazione dinamica `Simple Earn <-> Carry Delta-Neutral` sui dati storici di funding + perp, con costi reali di switch (0,30% round-trip spot+perp) e isteresi.
7. **Backtest Pista E2 (`scripts/ricerca_cascate_vol.py`)**: Simulare sui 59 simboli Bybit 1h/4h (5 anni) gli eventi estremi di capitolazione/liquidazione con **stop ATR reale a $2,5\times$** e verifica intra-barra su `minimo`/`massimo`.
8. **Backtest Pista E3 (`scripts/crosssec_neutral.py` v2)**: Correggere la contabilità del turnover (addebitare solo i cambi reali di portafoglio + buffer di isteresi) e rimisurare Momentum e Reversal dollar-neutral su 5 anni.

---

## PARTE 6 — Stato dei Fix (aggiornato 2026-10-15)

- ✅ **Fix 1 — banco a secco** (`deploy/banco/money_banco_secco.py`, commit `9793c13`): legge trading + funding + Simple Earn; un comparto illeggibile = `rc=1` (errore di misura), mai un giudizio su numeri incompleti. Verificato live su MARCODG1: `PASS equity 1099.99 EUR >= 100`, `rc=0` (prima: `rc=2 NON_FINANZIATO` ogni 5 minuti). Nuovo campo `equity_savings_eur` nella riga METRICA e nel JSONL.
- ✅ **Fix 2 — doppia sottrazione del pedaggio** (`src/money/cancello.py`, commit `4915cb7`): `_blocchi_netti` non ri-sottrae il pedaggio (la serie è già netta per contratto `Esito`): il criterio 8 non archivia più strategie positive senza il blocco migliore. +1 test di regressione; i 2 test che cristallizzavano l'aritmetica vecchia sono stati riscritti.
- ✅ **Fix 3 — DSR sulla finestra sbagliata** (`src/money/ricerca/scansione.py` + `caccia_continua.py`, commit `bdc44bb`): la deflazione si applica al track record di **addestramento** (dove avviene la selezione), non alla verifica: Sharpe, numerosità e varianza dei tentativi sulla stessa finestra. Chiave rinominata `dsr_selezione` (gli artefatti pre-fix con `dsr_oos` restano leggibili solo per cronologia). La verifica resta un cancello separato non deflazionato (n, expectancy, t). 691 test verdi anche sotto `python -O`, ruff pulito.
- ✅ **Fix 4 — unificazione rischio** (`src/money/esecuzione/rischio.py` + `esecutore.py`): il rischio per operazione si misura **sullo stop** (`nozionale × distanza_stop`), col tetto del mandato (2%); eliminato il blocco fittizio che rifiutava ogni spot oltre ~22 EUR su un conto da ~1.100 (era il 2% confrontato col NOZIONALE). La presenza dello stop resta di pertinenza del cancello unico; qui il merito (rischio ≤ tetto). Sizing operativo di default invariato (0,25%, `ParametriRischio`). +2 regressioni; 695 test verdi anche sotto `python -O`, ruff pulito.
- ✅ **Fix 5 — spegnimento rumore** (15/10): S4 caccia **fermata** (cron `*/5` commentato su mc2 — esaurita dal 12/10, niente più tick a vuoto; si riattiva solo con una nuova dichiarazione); `MOSAICO4_v1.md` **retrofit formato-contratto** (lint **7/7** → job `spec_fix` chiuso dal tick); **working tree ripuliti** (`ops/dashboard/scommessa.json` fuori dal versionamento come `agenti.json`; residui archiviati su MARCODG1).
- 🔄 **Fase 2 — ricerca E1–E4** (giudice riparato): E1 **NO** (carry dinamico 1,72%/anno vs pavimento Earn 5%), E2 **archiviata** (4/4 alla chiusura spietata), E3 **NO** (0/108 cross-sectional); resta **E4** (whitelist `api.bybit.eu`). Verdetti in `prove/REGISTRO_ESPERIMENTI.md`.
