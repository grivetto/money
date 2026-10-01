# P12 — Funding: regime e timing (decision-support per il carry)
STATO: MISURATA 2026-10-01 (hermes) — esito DESCRITTIVA SOLIDA; artefatti `prove/P12_funding_regime.{txt,json}`; misura `scripts/misura_p12.py`; test 17/17. **Addendum contabile 01/10: «uscita al primo negativo» NON adottata (netta 0/10 sui costi di ciclo); baseline carry = always-on.** Nessuna promozione (un solo regime).
DATI: archivio P8 `data/funding_xperp.jsonl` (10 X-Perp OKX EEA, dal 2026-06-29; raccolta
attiva ogni 4h). Candele perp pubbliche disponibili (`market/candles` EEA), NON usate in
questa misura (vedi M5).
NOTA DI NUMERAZIONE: la "(4h + regime)" ipotizzata il 30/09 come P12 (coda dsh) slitta a
P13 quando materializza; il numero P12 va a questa spec, scelta dal proprietario come primo
attacco del filone funding.

## Ipotesi
Il filone carry (P4 parcheggiata, C1 canary in corso) non ha ancora regole di ingresso/uscita
validate sui dati reali. Il triage del 30/09 era a regime singolo e a tariffe pre-X-Perp.
P12 produce, sull'archivio P8:
- H1 (persistenza): il funding X-Perp ha memoria breve — P(next>0 | media3>0) > base rate e
  autocorrelazione lag-1 > 0 sui simboli principali.
- H2 (netto a costi reali): con fee X-Perp (spot 0,10%×2 + perp 0,05%×2 + slippage 0,10%
  dichiarato = C 0,40%), almeno 6/10 strumenti hanno netto positivo a 30 giorni al funding
  medio osservato, con rientro costi ≤ 45 giorni.
- H3 (stabilità): la classifica di carryabilità tra strumenti è stabile tra le due metà del
  campione (rho di Spearman ≥ 0,5), senza inversioni di segno diffuse.
Nessuna promozione: con ~95 giorni = UN regime, il verdetto massimo è "descrittiva solida".
Output operativi: scorecard per strumento (per l'estensione di C1) + regola di regime
(per la futura P4 formale).

## Meccanica (dichiarata prima dei numeri)
- M1 persistenza (per simbolo): p0 = P(next>0); p1 = P(next>0 | corrente>0);
  p1b = P(next>0 | media3>0); autocorr lag-1. Bootstrap a blocchi (blocco = 21 eventi = 7
  giorni, 2000 ricampionamenti, seme fisso 20261001) per IC90 di mu e di p1b.
- M2 economia: C = 0,40% (primario, tariffe X-Perp reali del canary) e 0,62% (stress, tariffa
  del triage pre-X-Perp). netto(H) = mu_giornaliera × H − C, riportato per H ∈ {7,14,30,60,90}.
  TUTTI gli orizzonti riportati, nessuna selezione.
- M3 stabilità: campione diviso in due metà temporali (per data, non per convenienza); per ogni
  simbolo mu e %pos nelle due metà; Spearman tra i mu delle due metà (stabilità del ranking);
  conteggio inversioni di segno. Soglia dichiarata: rho ≥ 0,5 = stabile.
- M4 RULE (funding-only, NESSUN P&L di prezzo — dichiarato): confronto tra
  · ALWAYS-ON: cattura il funding di tutti gli eventi;
  · RULE: entra all'evento t se non in posizione e media3(t−1) > 0; esce prima dell'evento t
    se in posizione e l'evento t−1 è negativo ("primo negativo"; variante più protettiva della
    "2 negativi" di P4 — se vince, P4 adotta questa).
  Metriche: flusso catturato, quota vs always-on, giorni in posizione, max drawdown del flusso
  cumulato, episodi negativi catturati/evitati.
  Successo dichiarato: RULE cattura ≥ 85% del flusso di always-on E riduce il max drawdown del
  flusso ≥ 50%; altrimenti "sempre-on" è la regola (nessuna decisione in più).
- M5 timing intraday: NON misurato, per aritmetica dichiarata: un ciclo extra di entrata/uscita
  costa C = 0,40% mentre il funding medio per evento è ~0,005% (8h) → qualsiasi tattica che
  richieda un giro extra attorno al singolo settlement costa ~80× il ricavo. Morto per
  costruzione; l'unico timing ammesso è M4 (a bassa frequenza). Nessun grado di libertà speso.

## Griglia dichiarata (minima — niente ottimizzazione)
- ingresso: media3 > 0 (lo zero è la soglia naturale; UNICA variante);
- uscita: primo negativo (UNICA variante);
- orizzonti: {7, 14, 30, 60, 90} giorni (riportati tutti);
- costi: {0,40%, 0,62%}.
NIENT'ALTRO. Ogni variante ulteriore = nuova voce nel registro (regola del contatore varianti).

## Universo e campionamento
10 X-Perp con archivio P8: BTC, ETH, SOL, DOGE, XRP, ADA, AVAX, LINK, LTC (dal 29/06/2026),
DOT (dal 07/08/2026 — campione corto, riportato a parte). Evento = settlement funding /8h
(00/08/16 UTC). Simboli delistati assenti dall'archivio (survivorship dichiarato). Nota
prodotto: su OKX EEA gli X-Perp sono classificati `instType=FUTURES` (227 strumenti).

## Criteri di stop / esiti ammessi
- H2 negativo (netto@30g ≤ 0 per ≥ 6/10 simboli a C = 0,40%) → "archiviata al netto": carry
  multi-simbolo EEA fermo; C1 resta solo come validazione esecutiva del singolo simbolo.
- H1 negativo (p1b ≈ p0, autocorr ≈ 0) → nessuna regola di regime: la scelta always-on/off si
  fa su M2/M3 soli; P4 formale riparte solo con storia ≥ 1 anno (nuova voce).
- Esiti ammessi: {descrittiva solida, insufficiente, archiviata-al-netto}. MAI "promossa"
  (un solo regime non promuove nulla).

## Anti-bias
- Ritardo decisionale: media3 usa solo eventi ≤ t−1; l'applicazione della decisione avviene
  dall'evento t in avanti. Verificato nei test.
- Doppia metà di M3 fissa (metà del calendario), non scelta a posteriori.
- Nessun P&L di prezzo: fuori scope per dichiarazione (delta residuo, mark, liquidazione sono
  rischio del canary/P4, non di P12).
- Copertura e buchi: controllati da `report_funding.py`; righe malformate contate, mai crash.
- Campione corto dichiarato in OGNI output: la generalizzazione temporale è il rischio principe.

## Riferimenti
P4 (funding carry, parcheggiata) · P8 (raccolta) · C1 (docs/16) · triage 30/09
(`prove/P4_triage_carry_2026-09-30.*`) · protocollo referee: `docs/18_programma_ricerca_quant.md`.

## Addendum 2026-10-01 (dopo la misura — correzione di contabilità)
Il risultato LORDO di M4 è nei numeri, ma era contabilmente incompleto: la regola impone un
giro di entrata/uscita per OGNI episodio (8–39 per simbolo in 95 giorni) e il confronto
funding-only non pagava quei costi. Ricalcolo netto (C = 0,40% × episodi; always-on paga
1 ciclo): la regola batte always-on su **0/10** simboli (esempi: ADA −0,80% vs +2,03%;
SOL −14,60% vs +0,31%). → Verdetto operativo: **«uscita al primo negativo» NON si adotta**;
per i simboli carryabili la baseline è always-on; una regola di uscita ha senso solo su
segnali rari (es. regime negativo persistente) = NUOVA variante, nuova voce di registro.
Il modulo ora riporta SEMPRE entrambe le letture (lorda e netta); test dedicati in
`tests/ricerca/test_funding_regime.py`.
