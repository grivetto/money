# Denaro — brief del progetto (per analisi esterna)

## TL;DR
Progetto personale (1 proprietario + agenti AI) per costruire un sistema di trading crypto
**autonomo** che faccia crescere il capitale con rendimento composto sotto vincoli di rischio
duri, partito da capitale piccolissimo (oggi ~100 € di prova; 1.000 € previsti quando il
software sarà stabile). Il collo di bottiglia attuale **non è l'infrastruttura**: è trovare
una strategia con un edge reale che superi un cancello statistico molto severo — finora
**tutte le famiglie testate sono state archiviate** (nessuna promossa), ed è una cosa voluta.

## 1) Obiettivo
- Sistema automatico multi-nodo su crypto (exchange: OKX, regione EEA), sub-account separati
  e **una sola strategia per conto**.
- Rendimento giornaliero composto, capitale-agnostico nel design (da ~50 € a 10k €+), ma con
  la realtà di oggi: capitale piccolissimo → fee e ordini minimi dominano tutto.
- Autonomia: deve girare da solo 24/7 con intervento umano minimo; ogni componente critico
  ha heartbeat + auto-recovery + alert ("zero silenzi").
- Mandato di rischio (bozza in formalizzazione): rischio per trade ~2%, stop giornaliero
  ~-3%, drawdown massimo ~-10%. Drawdown di mercato accettati come costo del business;
  perdite operative/ingegneristiche non accettate.

## 2) Come è organizzato (tecnico)
- **3 macchine** (Linux/Windows, reti separate): un nodo di controllo/ops con monitoraggio,
  un nodo di trading "trend", un nodo di appoggio. Servizi systemd, stack di monitoring,
  dashboard web.
- **3 sub-account** separati, 3 stili di trading diversi e complementari per design
  (isolamento di rischio e strategia).
- **Più agenti AI** nel processo: un agente "esecutivo" con accesso a terminale e repository
  (fa da ingegnere capo), un agente ricercatore "peer" su un'altra macchina (revisione
  incrociata), istanze di agenti worker per task isolati con criterio di test.
  Tutta la collaborazione passa da un **repo git privato**: commit piccoli e motivati,
  prefisso per autore, niente force-push, review incrociata.
- **"Fabbrica"**: un cron ogni 5 minuti che avanza UNA azione per tick (scansione risultati,
  verifica consegne, misure, gate, prossima spec). Ritmo continuo ma disciplinato.
- **"Banco a secco"** (dry-run live): ogni 5 minuti, su un nodo di trading, il sistema legge
  i saldi reali (~100 €) con una **chiave API read-only** (strutturalmente incapace di
  inviare ordini — è la prova generale del layer live), calcola cosa farebbe e logga
  metriche PASS/FAIL. Centinaia di esecuzioni finora, zero fallimenti.

## 3) Il metodo di ricerca (il cuore recente)
Pipeline: **spec → implementazione → test → cancello → promozione o archiviazione**.
- **Test prima dei numeri**: i test (niente look-ahead, chiusura di tutte le operazioni,
  costi corretti) si scrivono prima di vedere i risultati; 235 test verdi.
- **Griglia dichiarata prima**: i parametri da provare si dichiarano prima dei risultati;
  niente criteri scelti a posteriori.
- **Dati**: coppie USDT su OKX da gennaio 2019; protocollo addestramento 2019-01 → 2024-06,
  verifica fuori campione 2024-06 → oggi; conferma finale sul campione EUR più corto.
- **Il cancello** — 8 criteri, tutti obbligatori:
  1. ≥ 30 operazioni (sotto: "insufficiente", non "archiviato": mancanza di dati ≠ strategia scartata);
  2. intervallo di confidenza bootstrap al 90% con estremo inferiore > 0 (riproducibile);
  3. t-statistic > 1,65;
  4. profit factor > 1,20;
  5. drawdown massimo ≤ 25%;
  6. **pedaggio**: expectancy netta ≥ 3× il costo per operazione (fee: ~0,55% per operazione
     su spot OKX EEA misto maker/taker; ~0,18% con perp);
  7. rilevanza economica: utile annuo estrapolato ≥ soglia in €;
  8. indipendenza da un singolo blocco contiguo: se togliendo il blocco migliore l'edge
     diventa negativo → archiviata (nessun edge che vive in una sola finestra di mercato).
  Il rifiuto è vincolante **nel codice**: la produzione si scrive come
  `if not giudica(esito): return`.
- **Limiti dichiarati**: il cancello non è una prova out-of-sample se la ricerca ha provato
  molte varianti; t e bootstrap assumono operazioni i.i.d. (autocorrelazione non corretta);
  l'estrapolazione annua è un tetto, non una previsione.

## 4) Stato attuale (onesto)
- **Risultati**: oltre una dozzina di famiglie testate (trend, momentum, mean-reversion RSI,
  breakout, rotazione, effetto weekend, stop "chandelier", filtro 200 giorni, Donchian…).
  **Tutte archiviate o "insufficienti"**: tipicamente t ≈ 1,4–1,6, drawdown 45–99%,
  expectancy che non batte il pedaggio. L'allargamento dell'universo ha diluito l'edge
  invece di consolidarlo.
- **In coda**: P2 = momentum + vol targeting (l'ultima carta: attacco al drawdown via
  sizing, in corso); P6 = livello portafoglio (cap di correlazione, segnali combinati);
  P7 = economia della soglia (a che capitale/leva il DD scende sotto il 25%); P8 =
  raccoglitore funding/basis appena integrato (il funding su EEA ha solo ~96 giorni di
  storia: si accumula dati prima di giudicare).
- **Infrastruttura**: monitoraggio, dry-run live, suite test, guardrail — funzionano.
  **Il trading reale non è attivo**: capitale in attesa (100 € di banco di prova; 1.000 €
  previsti solo a software stabile).
- **Il problema in una frase**: non manca l'impianto — manca una strategia che passi il
  cancello. È l'unica cosa che conta adesso.

## 5) Lezioni dal progetto precedente
49.162 righe di codice e **zero euro di profitto**, per due motivi: (a) promozione di
strategie senza criterio statistico ("il backtest sembrava buono"); (b) tutto il rendimento
concentrato in 1 blocco su 3, scoperto dopo. Da qui: cancello vincolante, costi nel modello
fin dal primo numero, riconciliazione con l'exchange per ogni risultato dichiarato.

## 6) Punti su cui vorremmo suggerimenti
1. **Edge**: con fee retail (~0,18% per operazione nel caso migliore), frequenza
   giornaliera, capitale ~1.000 € e i vincoli sopra — dove guardereste per un edge
   realistico e implementabile senza colocation/HFT? (funding-carry delta-neutral,
   momentum cross-sectional a livello portafoglio, stat-arb su majors correlati, vol risk
   premium, eventi di listing…) Quali famiglie sono realizzabili a questo taglio di
   capitale e con quali aspettative oneste?
2. **Calibrazione del cancello**: critica agli 8 criteri. Troppo severo per campioni da
   30–300 operazioni, o giusto? Cosa aggiungereste (deflated Sharpe, PBO, capacità,
   intervalli bootstrap block-aware per l'autocorrelazione)?
3. **Sizing**: con P2 misureremo vol targeting + cap di rischio. Quale miglioramento
   realistico di max-drawdown aspettarsi su sistemi trend — per fissare l'asticella PRIMA
   della misura, non dopo?
4. **Portafoglio minimo**: 3 sub-account, ~1.000 €, ordini minimi dell'exchange che a
   questo taglio mordono: quale design minimo di diversificazione (numero posizioni, cap di
   correlazione) ha senso senza frammentare troppo?
5. **Funding/basis a 1.000 €**: è praticabile netto fee sul perp EEA? Design minimo robusto
   e rischi principali da monitorare?
6. **Organizzazione multi-agente**: come strutturereste il loop
   spec→implementa→testa→gate→deploy con più agenti AI per massimizzare la velocità di
   scoperta onesta (evitando autoinganno e p-hacking)? Framework o case study da
   raccomandare?
7. **Ops**: quali 5 guardrail costruireste per primi in un sistema che opera da solo
   (kill switch, limiti giornalieri, riconciliazione, idempotenza degli ordini…) e in che
   ordine?

## 7) Vincoli e non-obiettivi
- Fuori tema: martingala, leva estrema, HFT/colocation, strategie che richiedono
  infrastruttura > 10k € o capitale molto più grande per funzionare.
- Dentro il tema: edge piccolo ma onesto, rischio sotto controllo, automazione affidabile,
  misure verificate contro l'exchange (meglio un "insufficiente" vero che un "promosso" falso).
