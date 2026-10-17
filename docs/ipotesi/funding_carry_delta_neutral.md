# Ipotesi pre-registrata: Funding/Carry Delta-Neutral su BTC e ETH

**Nome dell’ipotesi**: funding_carry_delta_neutral_BTC_ETH

**Motivazione economica**: 
Il funding rate nei contratti perpetui rappresenta il costo o il premio per mantenere una posizione lunga o corta rispetto al prezzo spot. In condizioni di mercato normale, il funding tende a essere positivo quando il prezzo del perpetuo è sopra lo spot (long pagano short) e negativo quando è sotto. Una posizione delta-neutral lunga spot + corta perpetuo dello stesso asset dovrebbe catturare il funding (se favorevole) nonché eventuali convergenze del basis (mark-price verso index price). L'edge proviene dal premio di funding medio nel tempo, al netto di commissioni, slippage e costi di riequilibrio, assumendo che la posizione rimanga sostanzialmente delta-neutral (cioè il prezzo spot e il perpetuo si muovano insieme).

**Dati richiesti**:
- Funding rate storico per ogni finanziamento (ogni 8 ore su OKX) per i simboli: BTC/USDT:USDT (spot) e BTC/USDT:USDT-PERP (o equivalente perpetual). Analogamente per ETH.
- Prezzo spot e prezzo mark/index del perpetual per calcolare il basis.
- Commissioni maker/taker per l'exchange (OKX EEA) prelevate da `money.costi`.
- Slippage medio stimato dallo spread osservato (usiamo il valore già dichiarato in `funding_scan.py`).
- Dati point-in-time: nessun dato futuro, solo quello che sarebbe stato disponibile al timestamp di ciascun finanziamento.
- Fonte: OKX (via ccxt) archiviato in `data/funding_xperp.jsonl` (append-only, idempotente).

**Regole di entrata**:
- Alla ricezione di un nuovo funding rate (timestamp t), valutare se il basis (mark - index) è dentro una banda di tolleranza (±basis_threshold bps). Se sì, aprire la posizione:
  * Long spot: comprare 1 unità di spot al prezzo ask (simulato con prezzo mark + slippage/2).
  * Short perpetual: vendere 1 unità di perpetual al prezzo bid (simulato con prezzo mark - slippage/2).
- Se il basis è fuori banda, non entrare (rimanere flat) fino al prossimo funding.

**Regole di uscita**:
- Chiudere la posizione al finanziamento successivo (t + 8h) oppure se il basis supera una soglia di emergenza (±basis_exit bps) prima del finanziamento successivo, in cui case chiudiamo immediatamente al prezzo di mercato corrente con slippage.
- Inoltre, chiudere se la deviazione delta (valore spot vs valore perpetuo) supera una certa soglia (delta_threshold % del capitale) per evitare rischio di liquidazione.

**Sizing**:
- Capitale di riferimento: 1.000 EUR.
- Leva massima: 2x (cioè impiegare fino a 500 EUR di margine per ciascuna gamba, mantenendo esposizione netta vicina a zero).
- Size della posizione in spot: capitale_allocato_spot / prezzo_spot.
- Size della posizione in perpetual: stessa notional (in valore USD) della gamba spot, corta.

**Durata massima della posizione**: 8h (intervallo tra funding) + eventuale uscita anticipata per basis exit.

**Regola di riequilibrio**:
- Ad ogni funding, se la posizione è aperta, riequilibriamo al prezzo di mercato corrente (simulato con mark price) per mantenere la stessa notional, pagando commissioni e slippage sul trade di riequilibrio (comprare/vendere la differenza dovuta a movimenti di prezzo).

**Costi assunti**:
- Commissioni: taker per entrambe le gambe (ingresso e uscita) + maker per riequilibri se utilizziamo ordini limit; assumiamo taker conservativo.
- Slippage: 0.04% per lato (come usato in altre scansioni).
- Fee di funding: effettivamente applicato (long paga, short riceve) come da dati storici.
- Costo di apertura/chiusura: commissione + slippage su ciascuna gamba.
- Margine iniziale: richiesto dal contratto perpetuo (usiamo la margin rate di OKX, ma per semplicità assumiamo 5% di notional come margine iniziale, controllando che il capitale impiegato non superi il capitale disponibile).

**Condizioni di invalidazione**:
- Se il basis mostra una divergenza strutturale (es. basis medio significativamente diverso da zero per più di X giorni) che rende la posizione non delta-neutral.
- Se il funding rate cambia segno frequentemente e la media su un periodo lungo è prossima a zero dopo costi.
- Se il massimo drawdown supera il 30% del capitale in una simulazione storica.
- Se il numero di operazioni (aperture/chiusure) è inferiore a 30 nel periodo di training.

**Metriche di successo**:
- Expectancy netta per operazione (in % del capitale impiegato) positiva dopo tutti i costi.
- t-statistico > 1.65 (una coda).
- Profit factor > 1.2.
- Massimo drawdown <= 25% del capitale.
- Expectancy netta media per operazione >= 3 x costo medio per operazione (pedaggio).
- Guadagno annuo atteso (estrapolazione) >= 10 EUR/anno (soglia di rilevanza).
- Dipendenza da un solo blocco temporale < 0.5 (criterio 8 del cancello).
- Passare tutti i criteri del `money.cancello`.

**Periodo train**: 2024-06-01 → 2025-05-31 (12 mesi di dati storici).
**Periodo validation**: 2025-06-01 → 2025-08-31 (3 mesi) – usato per eventuale aggiustamento di soglie (ma non per selezione finale).
**Periodo test OOS**: 2025-09-01 → 2026-08-31 (12 mesi) – usato una sola volta per valutazione finale.

**Note sulla riproducibilità**: 
Tutti i parametri (soglie di basis, delta threshold, ecc.) sono dichiarati in questo documento. Il codice leggerà questi valori da un file di configurazione (JSON) che verrà versionato insieme all'ipotesi. Qualsiasi modifica alle soglie dopo aver visto i risultati OOS richiede una nuova ipotesi e incremento del conteggio dei tentativi.