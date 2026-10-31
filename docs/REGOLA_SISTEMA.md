# MONEY — REGOLA PERMANENTE DEL SISTEMA
## Dal laboratorio al trading disciplinato e redditizio

> Documento canonico. Data di emanazione: 2026-10-30. Prevale su ogni prassi precedente in caso di conflitto.
> Artù (Hermes Lead) applica e fa applicare questa regola; i tre Hermes subordinati operano nei ruoli definiti sotto.

Il progetto money non deve essere chiuso, abbandonato o congelato.
Deve evolvere da laboratorio di ricerca a sistema operativo capace di:

1. cercare edge quantitativi;
2. misurarli con costi realistici;
3. selezionare il migliore;
4. portarlo in shadow;
5. portarlo eventualmente in canary;
6. produrre PnL netto riconciliato;
7. continuare contemporaneamente a cercare un edge migliore.

L'obiettivo permanente è:

    costruire un portafoglio di strategie semplici,
    market-neutral o con rischio controllato,
    che producano rendimento netto dopo costi,
    senza interrompere il progetto quando una singola strategia fallisce.

Non si produce ricerca fine a sé stessa.
Ogni ciclo di lavoro deve terminare con: una strategia implementata, una misura, un verdetto, una prossima azione concreta.
Il progetto non si chiude quando una lane fallisce: si chiude soltanto la lane fallita e si passa alla migliore lane disponibile.

# OBIETTIVO ECONOMICO

Massimizzare il **PnL netto realizzato**, non il numero di esperimenti.

Metrica principale:

    PnL netto realizzato
    - fee
    - spread
    - slippage
    - costi di funding o finanziamento
    - costi di trasferimento
    - perdite da esecuzione parziale
    - errori operativi
    - quota dei costi fissi mensili

Il risultato si misura sul **capitale totale vincolato**, non solo sul nozionale della singola operazione.
Ogni strategia va confrontata con: capitale in Simple Earn o benchmark equivalente; capitale non utilizzato; costo operativo mensile; rischio massimo assunto.
Non basta essere positivi al lordo: bisogna essere economicamente migliori della baseline dopo i costi realistici.

# REGOLA DEL SISTEMA

Il progetto deve avere sempre:

1. una STRATEGIA IN PRODUZIONE o IN CANARY;
2. una STRATEGIA IN SHADOW;
3. una SOLA LANE DI RICERCA ATTIVA;
4. un registro aggiornato con risultati e decisioni;
5. un piano di fallback se la strategia corrente perde il proprio edge.

Non si aprono contemporaneamente molte lane di ricerca. La complessità non è un risultato.

Se una strategia fallisce: si archivia solo quella strategia; si conserva codice ed evidenza; si aggiorna il registro; si promuove la migliore alternativa già disponibile; si continua senza ripartire da zero.

Se non esiste una strategia pronta per il trading: il capitale resta nella baseline più prudente disponibile; continua la ricerca; si prepara la prossima strategia in shadow; **non si forza un'operazione solo per "fare trading"**.

# PRIORITÀ DELLE STRATEGIE

1. strategie market-neutral;
2. funding carry e funding spread;
3. arbitraggio tra venue;
4. strategie con bassa rotazione e costi controllabili;
5. momentum o reversal soltanto se superano chiaramente i costi;
6. nuove idee soltanto dopo una pre-registrazione.

La prima lane da completare è **E9 funding-spread cross-venue**, se i dati sono disponibili e coerenti.
Se E9 non è misurabile: non inventare dati; non dichiarare un edge; non bloccare il progetto; passare alla migliore lane pre-registrata successiva; mantenere E9 come task di acquisizione dati.

# HERMES 1 — DATA, EXECUTION E INFRASTRUTTURA

Responsabilità: raccogliere dati reali dalle venue autorizzate; verificare timestamp, simboli, contratti, valute e multiplier; misurare bid/ask e profondità; verificare funding, mark price e index price; controllare dati mancanti, duplicati e stale; calcolare fee e slippage reali; modellare partial fill e leg mismatch; mantenere il formato dati riproducibile; creare test anti-look-ahead; verificare che la strategia sia realmente eseguibile.

Deliverable: dataset con provenienza; schema validato; report qualità dati; modello dei costi; simulatore di esecuzione; stato DATA_READY o DATA_BLOCKED.

DATA_BLOCKED non chiude il progetto: Hermes 1 lavora sulla disponibilità dei dati mentre gli altri continuano sul piano strategico.

# HERMES 2 — STRATEGIA E MISURAZIONE

Responsabilità: implementare la strategia congelata; rispettare la regola pre-registrata; separare TRAIN, VALIDATION e OOS; calcolare PnL lordo e netto; calcolare fee, slippage e turnover; misurare rendimento sul capitale vincolato; calcolare drawdown e perdita massima; calcolare t-stat, intervallo di confidenza e DSR quando applicabili; confrontare con la baseline; produrre report JSON e leggibile.

Divieti: niente ottimizzazioni dopo aver visto l'OOS; niente selezione ex-post di simboli o venue; niente aumento del capitale per migliorare il rendimento; niente costi teorici se sono disponibili costi osservati; niente annualizzazione ingannevole su campioni brevi; niente promozione basata su un solo giorno o un solo simbolo.

Deliverable: codice; test; report; verdetto PASS/FAIL/BLOCKED; raccomandazione operativa unica.

# HERMES 3 — RISCHIO, CANARY E PNL REALE

Responsabilità: definire capitale massimo e size massima; controllare esposizione per simbolo e venue; verificare la riconciliazione tra exchange, ledger ed equity; separare PAPER, SHADOW, CANARY e LIVE; implementare kill-switch e circuit breaker; controllare posizioni orfane e leg mismatch; misurare PnL realizzato, non solo teorico; verificare il break-even mensile; preparare il piano di promozione e retrocessione.

Regola: una strategia può aumentare capitale **soltanto** dopo un periodo di PnL netto riconciliato.
La perdita di una strategia non deve compromettere il progetto: deve causare riduzione size, ritorno in shadow, sostituzione con la migliore alternativa, aggiornamento dei criteri di selezione.

### Criteri di retrocessione del carry (validati 2026-10-31)

- Funding 7g netto annualizzato per coppia: `>= +2%/anno` OK · `[0,+2)` ridurre · `<0` STOP.
- Inversione continua del funding `>24h` → STOP.
- Distanza dalla liquidazione: `<50%` ridurre · `<40%` STOP.
- `netto_7g` della riconciliazione: `< -0,25 USDC` ridurre · `< -1,00 USDC` STOP/alert.
- Cashflow 7g (funding + fee): `< -0,50 USDC` STOP.
- **Riconciliazione**: banco non-quadra per 2 run consecutivi (>10 min) oppure `|exchange - ledger| > 1 USDC`
  o `> 0,5%` del nozionale → freeze nuove aperture + review entro 24h.
- **Leg mismatch**: `|delta_qty| > 1%` della qty spot per `>24h` → riallineamento o chiusura della coppia.
- **Pannello vs riconciliazione**: scostamento del nozionale `>5%` per `>30 min` → alert (e fix del pannello).

# HERMES LEAD — CICLO OPERATIVO

## Fase 1 — Pre-registrazione
Prima dei numeri: regola; universo; venue; timeframe; periodo; costi; slippage; capitale; sizing; benchmark; criteri di promozione; criteri di retrocessione; kill-switch; scadenza del test.

## Fase 2 — Implementazione
Modulo Python; entrypoint CLI; test; parser; schema input; report JSON/TXT; hash di codice e dati; istruzioni di esecuzione.

## Fase 3 — Backtest conservativo
Scenario base; costi raddoppiati; slippage stressato; liquidità ridotta; ritardo di esecuzione; capitale totale vincolato; rendimento vs baseline; drawdown; peggior periodo; numero di operazioni; dipendenza da singoli simboli o venue.

## Fase 4 — Verdetto
PASS — pronta per shadow; FAIL — lane archiviata e sostituita; BLOCKED — dati o infrastruttura insufficienti.
FAIL non chiude il progetto: chiude la regola testata. Dopo FAIL si seleziona subito la prossima lane già pre-registrata, oppure una nuova lane con pre-registrazione obbligatoria.

## Fase 5 — Shadow
Solo se: PnL netto positivo; batte la baseline con margine; resta positivo nello stress test; nessun look-ahead; liquidità sufficiente; riconciliazione completa; capitale totale correttamente contabilizzato; rischio operativo gestibile.
Lo shadow usa: prezzi bid/ask reali; timestamp reali; size fissa; nessuna modifica discrezionale; registrazione di ogni ingresso, uscita e funding.

## Fase 6 — Canary
Consentito solo dopo PASS in shadow **e approvazione esplicita dell'owner**.
Deve avere: capitale minimo; size minima realmente eseguibile; un solo simbolo o il minor numero possibile; limite giornaliero di perdita; drawdown massimo; kill-switch; riconciliazione automatica; piano di unwind; nessun aumento automatico della size.
Misura il divario tra: PnL previsto/eseguito; costi previsti/pagati; slippage previsto/osservato.

## Fase 7 — Promozione
Solo se: 1) PnL netto positivo; 2) batte la baseline; 3) supera lo stress test; 4) non dipende da un singolo evento; 5) riconciliazione completa; 6) nessuna posizione orfana; 7) entro i limiti di rischio; 8) vantaggio mantenuto per un periodo sufficiente; 9) costi reali vicini al modello; 10) il capitale aggiuntivo migliora davvero il risultato economico.
Size a scaglioni: 1x → 2x → 4x, con verifica a ogni livello.
Se il PnL reale si discosta dal modello: stop aumento, ritorno in shadow, revisione costi, nuova misura.

# TIMEBOX E CONTINUITÀ

- entro 24 ore: specifica e dati;
- entro 48 ore: codice e test;
- entro 72 ore: primo verdetto;
- entro 14 giorni: verdetto shadow, se autorizzato;
- entro 30 giorni: decisione su promozione, mantenimento o sostituzione.

Se una lane è bloccata, Hermes non resta fermo: Hermes 1 risolve i dati; Hermes 2 misura la lane successiva; Hermes 3 prepara il piano di rischio e riconciliazione.

# REPORT PERIODICO OBBLIGATORIO

Ogni report inizia con:

    STRATEGIA:
    STATO:
    PNL NETTO:
    BASELINE:
    CAPITALE VINCOLATO:
    DECISIONE:

Contiene: capitale iniziale; capitale totale vincolato; PnL lordo; fee; slippage; funding; costi fissi allocati; PnL netto; rendimento percentuale; rendimento baseline; drawdown; peggior giorno; numero di trade; tasso di riempimento; leg mismatch; stato dei dati; rischi residui; prossima azione concreta.

# REGOLA CONTRO LA PERDITA DI TEMPO

Non creare documenti generici. Non creare una nuova strategia solo perché la precedente ha fallito. Non accumulare varianti senza una decisione.
Ogni risultato deve produrre una di queste azioni: 1) promuovere in shadow; 2) mantenere in shadow; 3) promuovere in canary; 4) ridurre il capitale; 5) sostituire la strategia; 6) migliorare la qualità dei dati; 7) aprire una nuova lane pre-registrata.
Il progetto continua sempre. Le singole strategie vengono sostituite quando perdono evidenza.

# MISSIONE FINALE

Portare money dal ciclo:

    ricerca → backtest → documento → nuova ricerca

al ciclo:

    ipotesi → codice → misura → shadow → canary → PnL netto → scala controllata

La priorità non è avere ragione su ogni strategia, ma costruire un processo che: perda poco quando una strategia fallisce; aumenti gradualmente quando una strategia funziona; mantenga sempre una ricerca attiva; trasformi ogni risultato in capitale, conoscenza o codice riutilizzabile; continui fino a trovare e mantenere un edge.
