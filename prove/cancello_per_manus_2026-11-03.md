# IL CANCELLO — progetto del gate di promozione/pre-trade di Denaro
Documento di lavoro per revisione esterna (Manus AI).
Repo: grivetto/money · commit di riferimento: aa8feec8 (2026-11-02) · generato 2026-11-03.
Nota: nessun segreto in questo documento; i path citati sono verificabili nel repo.

---

## 1. SCOPO (in 10 righe)

Denaro è un sistema di bot crypto multi-nodo. Il progetto precedente ha prodotto 49.162
righe di codice e zero euro di profitto perché promuoveva strategie senza criterio
statistico ("il backtest sembrava buono" bastava). Il "cancello" è l'insieme dei gate che
decidono, in serie e in modo non aggirabile, se un'ipotesi ha il diritto di:
  1. essere implementata (gate JEV, advisory);
  2. essere promossa da paper a capitale reale (gate statistico + DSR);
  3. sbloccare capitale (artefatto di promozione firmato e scadibile);
  4. inviare un singolo ordine (gate pre-trade con stop ATR obbligatorio);
  5. sopravvivere a perdite (governatore drawdown, kill switch).

Ogni gate è fail-closed: un input mancante o malformato produce RIFIUTO, mai un default
permissivo, mai un'eccezione che qualcuno possa commentare. Il sospetto attuale (motivo di
questa revisione): il cancello può essere TROPPO chiuso — da E8 a E19, 12 esperienze
chiuse, 0 promozioni; la flotta è 13 bot paper, 0 live, capitale ~1.100 EUR.

## 2. ARCHITETTURA: i gate in serie

spec di ipotesi
  -> [G0] JEV gate (advisory, fail-open)                    src/money/jev.py
  -> [G1] walk-forward + DSR (screener)                     scripts/ipotesi_veloce.py
  -> [G2] gate statistico: 8 criteri                        src/money/cancello.py
  -> [G3] artefatto di promozione (firma+TTL+cap)           src/money/esecuzione/promozione.py
  -> [G4] gate pre-trade (stop, sizing, calore, beta)       src/money/rischio.py + esecuzione/cancello.py
  -> [G4b] governatore drawdown (kill switch)               src/money/rischio.py (StatoRischio)
  -> [G5] gate carry (delta-neutral)                        src/money/esecuzione/cancello_carry.py
  -> invio (unico gateway di ordini)                        src/money/esecuzione/invio.py

Il capitale reale si arma SOLO con MONEY_LIVE_ARMED=1 + un artefatto di promozione valido
(Esecutore rifiuta altrimenti). Non esiste un secondo percorso di invio ordini: il canary
passa dallo stesso gate_pre_trade dell'Esecutore.

---

## 3. G0 — JEV gate (qualità delle spec, advisory)

src/money/jev.py, CLI scripts/jev_gate.py. Interroga un modello esterno (TypeSafe JEV,
api.typesafe.ai) con 4 domande su ogni spec PRIMA del dispatch agli aiutanti:
  self_contained   : la spec è autosufficiente? (noul 0..1)
  test_falsifiable : contiene un test di accettazione eseguibile? (noul 0..1)
  gap              : parte più sottospecificata (choice: goal/io/constraints/test/none)
  non_trading      : è strettamente ricerca/tooling, senza ordini reali? (noul 0..1)

Soglie (scripts/jev_gate.py, flags_of):
  self_contained  < 0.80  -> flag "spec non autosufficiente"
  test_falsifiable< 0.80  -> flag "criterio di accettazione debole"
  non_trading     < 0.50  -> flag "possibile impatto trading"
  gap != none             -> flag "gap principale: <tipo>"

FAIL-OPEN: chiave assente o errore di rete => nessun verdetto, si procede. È advisory:
blocca il dispatch, non muove capitale. Soglie 0.80/0.80/0.50, non calibrate su dati.

## 4. G1+G2 — screener e gate statistico (il cuore)

### 4.1 Lo screener (scripts/ipotesi_veloce.py)

Prende un'ipotesi JSON (famiglia di configurazioni, finestra train/OOS, simboli), gira
sullo stesso motore del rig (decisione alla chiusura barra i, esecuzione all'apertura
i+1, costi money.costi + slippage). Verdetto per selezione (funzione verdetto):

  PROMOSSA = n_oos >= 30  AND  expectancy OOS > 0  AND  t_stat > 0  AND  DSR >= 0.95
  RESPINTA = tutto il resto, col motivo primario.

DSR = Deflated Sharpe Ratio (Bailey & López de Prado), probabilita' che lo Sharpe
osservato NON sia il massimo di N prove a vuoto. Il conteggio N è il punto delicato:
default = tentativi DELL'IPOTESI; con --cumulativi si aggiunge lo storico di tutti i
tentativi fatti dal progetto (i nodi hanno esplorato 8, 144, 378, 18, 4 configurazioni).

Formula (src/money/statistica.py, sharpe_deflazionato):
  SR0 = sqrt(V) * [(1-g)*Z^-1(1-1/N) + g*Z^-1(1-1/(N*e))]    (g = Eulero-Mascheroni)
  z   = (SR_oss - SR0) * sqrt(n-1) / sqrt(1 - skew*SR + ((kurt-1)/4)*SR^2)
  DSR = Phi(z)
Richiede la varianza V degli Sharpe dei tentativi: senza, la funzione SOLLEVA (mai
assunta in silenzio).

In più, consistenza cross-simbolo (per la promozione, non per la sola selezione):
la migliore selezione promuove SOLO se il meccanismo è COERENTE:
  quota di simboli con expectancy OOS positiva >= 60%  E  media OOS > 0.
"Una selezione su un simbolo fortunato non basta."

### 4.2 Il gate statistico (src/money/cancello.py, giudica)

Otto criteri, TUTTI devono passare (nessuna compensazione):

  1. Numerosità   : n >= 30 operazioni E n_effettivo >= 30 (osservazioni indipendenti,
                    stimate con n/durata_media o dal fattore di inflazione varianza).
  2. Expectancy   : IC bootstrap 90% con estremo inferiore > 0 (seme fisso 20260101,
                    10.000 ricampionamenti; riproducibile). Se |rho(1)| > 2/sqrt(n):
                    richiesto ANCHE l'IC a blocchi circolari con estremo inferiore > 0.
  3. t-statistic  : > 1.65 (una coda, 5%). Se autocorrelazione rilevante vale il
                    min(t naive, t Newey-West).
  4. Profit factor: > 1.20 (somma positivi / |somma negativi|).
  5. Drawdown     : massimo <= 25% del capitale.
  6. Pedaggio     : expectancy netta media >= 3 x costo di un giro completo alla tariffa
                    dichiarata ("1x = pareggio, 2x = margine che lo slippage cancella,
                    3x = margine vero").
  7. Rilevanza    : guadagno annuo atteso >= 10 EUR/anno su capitale di riferimento
                    1.000 EUR (estrapolazione DICHIARATA come limite superiore).
  8. Indipendenza : tolto il blocco contiguo migliore (3 blocchi), l'expectancy dei
                    restanti deve restare > 0. Un edge concentrato in 1 blocco su 3 è
                    "una coincidenza con una data".

Verdetti (bool(verdetto) è True solo per "promosso"):
  promosso / archiviato / insufficiente.
"insufficiente" = n < 30 o dati degeneri: non si promuove E non si archivia — "non lo so".
Ogni motivo contiene il NUMERO che lo sostiene; i criteri sono valutati tutti anche se
uno fallisce (per sapere cosa cambierebbe abbassando il pedaggio).

Onestà dichiarata nel modulo stesso (cosa NON dimostra): non è prova out-of-sample
(il numero di tentativi non lo vede); il bootstrap i.i.d. assume operazioni indipendenti
(corretto dal 06/10 con blocchi+HAC); lo slippage vive dentro ritorni_netti.

## 5. G3 — l'artefatto di promozione (la serratura del capitale)

src/money/esecuzione/promozione.py. Il capitale di validazione (~100 EUR) si sblocca SOLO
con un PromotionArtifact: immutabile (sha256 su contenuto canonico), SCADIBILE (TTL 30
giorni: "una promozione vecchia è un'ipotesi che potrebbe non valere più"), con capitale
massimo dichiarato, verdetto "PROMOSSA" e DSR >= 0.95. valida() è fail-closed:

  verdetto != "PROMOSSA"              -> rifiuto
  hash manomesso                      -> rifiuto
  capitale_max_eur <= 0               -> rifiuto
  dsr < 0.95                          -> rifiuto
  n_tentativi_cumulativi < ipotesi    -> rifiuto (contabilità incoerente)
  scaduto                             -> rifiuto

L'Esecutore (live) pretende MONEY_LIVE_ARMED=1 + promozione_path; senza, resta dry-run.

## 6. G4 — gate pre-trade (src/money/rischio.py + esecuzione/cancello.py)

verifica_pre_trade è l'UNICO punto che ammette o rifiuta un'operazione. Soglie
(ParametriRischio, frazioni dell'equity corrente):

  rischio per operazione     0.25% dell'equity
  calore massimo            1.00% (somma rischi aperti contemporanei)
  stop ATR                  OBBLIGATORIO (prezzo_stop dal segnale, 2.5 x ATR); senza stop
                            l'ordine non esiste (gate_pre_trade, fail-closed)
  leva massima              2.0x; distanza liquidazione >= 25%
  nozionale minimo          1.0 EUR; concentrazione max 25% equity per posizione
  concentrazione beta       50% (anti "N bot long sul BTC")
  correlazione media >0.70  -> size dimezzata (x0.5)
  perdita giornaliera       2%  -> stop 24h
  perdita settimanale       5%  -> stop fino a revisione
  drawdown da picco         10% -> KILL SWITCH; 20% -> CHIUSURA progetto (capitale fermo)

Kill switch (azioni in ordine, non estetico): fermare lo scheduler PRIMA dei bot (i
watchdog li riavvierebbero) -> cancellare ordini aperti per simbolo/client_id -> chiudere
le posizioni a mercato -> evento su ledger -> notifica rumorosa -> verifica chiusura
sull'exchange e riconciliazione.

Governatore StatoRischio: fail-closed per costruzione — appena creato è "stato
inattendibile" e non opera finché non riceve un'osservazione di equity ("non si opera
senza sapere quanto vale il conto").

## 7. G5 — gate carry (delta-neutral) — src/money/esecuzione/cancello_carry.py

Il gate direzionale (stop ATR + budget 0.25%) NON si applica al carry: misurato il
16/10, con equity 498 EUR il budget era 1.25 EUR e l'ATR giornaliero di DOT (7.8%)
limitava il nozionale a 16 EUR — un terzo del necessario: "il gate direzionale non
protegge, impedisce l'operazione giusta". Soglie del gate carry:

  leva                      1x, non negoziabile
  distanza liquidazione     >= 50% (a 1x è ~100%, si chiede metà)
  delta relativo tra gambe  <= 0.5%
  costo di ciclo            >= 0.05% (sotto: "fotografia non credibile")
  funding atteso            > 0 (il carry deve incassare)
  payback                   <= 90 periodi di funding (30 giorni)

In corso (P34, pre-registrata 26/10): funding X-Perp = tariffa fissa verificata al gate,
altrimenti rifiuto; USDT-SWAP = p10 della serie rolling (>=30 periodi, altrimenti
rifiuto "campione insufficiente"); chiusura economica con netto >= fee_uscita+basis
(il vecchio "netto >= 0" chiudeva PRIMA del pareggio reale, misurato sul ciclo ADA:
-0.157 USDC realizzati su +0.093 MTM).

---

## 8. TABELLA RIEPILOGATIVA DELLE SOGLIE

  GATE            SOGLIA                              EFFETTO SE FALLISCE
  G0 JEV          spec <0.80 / test <0.80             flag, dispatch fermato (advisory)
  G1 screener     n_oos>=30, exp>0, t>0, DSR>=0.95    RESPINTA
  G2 statistico   n>=30 e n_eff>=30                   INSUFFICIENTE (né sì né no)
                  IC90 inf > 0                        archiviato
                  t > 1.65                            archiviato
                  PF > 1.20                           archiviato
                  maxDD <= 25%                        archiviato
                  exp >= 3x fee                       archiviato
                  >= 10 EUR/anno su 1000 EUR          archiviato
                  edge non concentrato in 1 blocco    archiviato
  G3 promozione   DSR>=0.95, TTL 30gg, cap dichiarato capitale congelato
  G4 pre-trade    0.25%/trade, calore 1%, stop ATR    ordine non esiste
                  leva<=2, liq>=25%, conc 25%, beta   ordine non esiste
                  50%, corr>0.70 -> size/2            ordine ridotto
  G4b governatore giorno 2%, settimana 5%, DD 10/20%  stop / kill switch / chiusura
  G5 carry        1x, liq>=50%, delta<=0.5%, payback  carry non aperto
                  <=90 periodi, funding>0

## 9. DATI REALI (stato al 03/11/2026)

  - Esperienze E8..E19: 12 chiuse, 0 promosse (E19 venue-blocked).
  - Flotta: 13 bot paper, 0 live. Capitale OKX main ~1.100 EUR.
  - Unico capitale operativo reale: carry funding 1x su DOT+LTC+canary DOGE
    (uPL +60,8 MTM riconciliato sull'exchange, cap 40%).
  - Storico esplorazioni dei nodi: 8, 144, 378, 18, 4 configurazioni provate.
    Il dip-DCA passò da +10,315% in campione a -4,03% fuori dopo 144 tentativi:
    firma del massimo di N prove (motivo del DSR).

## 10. PUNTI SOSPETTI DI ECCESSIVA RESTRITTIVITÀ (nostra analisi, da discutere)

  A. DSR >= 0.95 con N cumulativo che cresce per sempre. Con N=400 tentativi, SR0
     (Sharpe atteso del massimo sotto null) è tipicamente 2-3; per avere DSR 0.95 su
     30-60 operazioni OOS serve uno Sharpe OOS di 3-4. Nessuna strategia realistica lo
     raggiunge con capitale piccolo => il gate è di fatto un muro. Domanda: soglia 0.95
     su N cumulativo vs N dell'ipotesi? Alternativa: Holm-Bonferroni sequenziale,
     shrinkage bayesiano, o DSR gerarchico (per famiglia di ipotesi).
  B. n>=30 E n_eff>=30: una strategia lenta (1 operazione/settimana) richiede ~7 mesi di
     dati reali per essere giudicabile; il verdetto "insufficiente" non ha scadenza:
     limbo paper infinito senza un termine che forzi una decisione (paper perpetuo o
     archiviazione per tempo).
  C. expectancy >= 3x pedaggio: a OKX EEA (8/10 bp per lato) il giro misto costa
     ~0,20-0,26% => serve expectancy netta >= ~0,6-0,8% per operazione. Strategie a
     basso edge ma alta frequenza (0,3-0,5%) sono aritmeticamente morte, anche se
     sarebbero redditizie. Il margine 3x è una scelta, non una verità statistica.
  D. Incoerenza interna drawdown: il gate statistico ammette maxDD 25% in backtest, ma
     il governatore kill-switcha a 10% di drawdown da picco. Una strategia promossa con
     DD storico 20% viene fermata in live a 10%: il cancello promuove ciò che il
     kill switch ammazza.
  E. Rischio 0.25% su 1.100 EUR = 2,75 EUR a trade; con stop a 2.5xATR su alt ad alta
     vol il nozionale consentito rasenta il min_notional dell'exchange: bot "vivo" ma
     strutturalmente muto (pitfall già documentato). Calore 1% = max 4 posizioni.
  F. Criterio 8 su n=30 con 3 blocchi da 10: un singolo blocco buono uccide l'edge.
     Il numero di blocchi è arbitrario (il codice stesso lo dichiara) e su campioni
     piccoli il criterio è più severo che su campioni grandi (dipendenza dalla
     granularità della partizione).
  G. Il gate carry (delta <= 0.5%, payback <= 30gg) e il nuovo P34 (p10 funding su >=30
     periodi, rifiuto se campione corto) aggiungono conservatività su un unico fronte
     (carry) che è l'unico a produrre MTM positivo: rischio di bloccare l'unica fonte
     di rendimento mentre il resto non promuove nulla.

## 11. DOMANDE PRECISE PER MANUS AI

  1. DSR >= 0.95 con conteggio tentativi CUMULATIVO (crescente per sempre): è
     statisticamente corretto o sovra-penalizza ogni nuova ipotesi? Quale alternativa
     mantiene il controllo del selection bias senza rendere la promozione impossibile
     con capitale <= 10k EUR?
  2. Coerenza tra maxDD promosso (25%) e kill switch live (10%): come riconciliarli?
  3. Per strategie lente (poche operazioni/anno), esiste un test sequenziale (SPRT,
     A/B bayesiano) che promuova prima con lo stesso controllo di falsi positivi?
     A che condizioni è accettabile promuovere con n < 30?
  4. Il margine 3x sul pedaggio è difendibile come universale, o dovrebbe essere
     funzione della tariffa/venue e della frequenza?
  5. Il criterio 8 (rimozione del blocco migliore) con partizione uniforme in 3 blocchi:
     scelta robusta su n=30? Quale alternativa (bricole per regime, leave-one-block-out
     pesato)?
  6. Il progetto punta a essere capital-agnostic (50 EUR -> 10k EUR). Le soglie in
     frazione di equity (0.25%, 1%, 10%, 20%) reggono a capitale minimo, o servono
     minimi assoluti e regole che cambiano con la scala?
  7. Cosa MANCA al cancello che dovrebbe bloccare di più (non di meno)? Es. test di
     regime out-of-sample oltre i blocchi, survivorship, dipendenza dal funding rate?

## 12. FILE DI RIFERIMENTO (per verifica)

  src/money/cancello.py                gate statistico (8 criteri, giudica)
  src/money/statistica.py              bootstrap a blocchi, Newey-West, DSR
  src/money/rischio.py                 verifica_pre_trade, ParametriRischio, StatoRischio
  src/money/esecuzione/cancello.py     gate_pre_trade unico (stop ATR obbligatorio)
  src/money/esecuzione/cancello_carry.py  gate carry
  src/money/esecuzione/promozione.py   PromotionArtifact (firma, TTL, cap)
  src/money/jev.py + scripts/jev_gate.py  gate JEV advisory
  scripts/ipotesi_veloce.py            screener walk-forward + DSR + consistenza
  tests/esecuzione/test_promozione.py, tests/test_cancello_carry.py  test fail-closed
  .hermes/skills/denaro-trading-infra/references/pre-live-validation.md  processo
