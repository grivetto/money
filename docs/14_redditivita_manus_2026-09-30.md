# Redditività — adozione dei suggerimenti Manus (30/09/2026)

Fonte: "Ulteriori suggerimenti per arrivare alla redditività" (Manus AI, docx in ~).
Verdetto Hermes: solido — si adotta come "livello economico" del metodo, senza gonfiare il carico.
Nessuna promessa di rendimento: le proposte aumentano la probabilità di trovare e conservare
un edge; non trasformano un backtest in una promessa.

Tesi centrale del documento (condivisa): il collo di bottiglia non è monitoraggio/agenti/automazione,
ma l'**economia unitaria**:

    utile netto per operazione x numero di operazioni sostenibili - costi fissi - errori operativi

## Delte concreti al pipeline (adottati)

1. **Obiettivo a 3 livelli** (al posto di "rendimento giornaliero" come motore):
   - A — sopravvivenza: mandato di rischio rispettato, riconciliazioni pulite, zero ordini
     duplicati/non autorizzati, costi reali coerenti col modello.
   - B — validità economica: expectancy netta positiva ANCHE nello scenario stressato; edge non
     concentrato in un solo asset/mese/regime; batte una baseline passiva corretta per costi.
   - C — significatività pratica: il profitto in euro giustifica complessità e rischio; capitale
     non bloccato dai minimi d'ordine; scalabilità senza degrado.
   → da recepire in M1: il rendimento composto resta metrica di REPORT, non di selezione.

2. **Scheda economica per strategia + cost-to-edge** = costo totale atteso / edge lordo atteso.
   Da produrre per ogni misura (P6 inclusa). Regola: non si promuove una strategia il cui costo
   centrale assorbe quasi tutto l'edge — e deve restare confortevole anche sotto stress di
   spread/slippage, non "appena sopra il pareggio".

3. **Score di utilità pre-registrato** per la selezione:
   rendimento netto stressato − penali (drawdown, turnover, concentrazione, instabilità tra
   regimi, complessità operativa). Pre-registrato PRIMA di vedere i risultati.

4. **Una tesi economica per volta** per l'ALLOCAZIONE di capitale (la ricerca resta a lane
   parallele — direttiva owner — ma il capitale va a una tesi per volta, con domanda precisa):
   - Tesi 1 — carry/funding (raccolta in corso: P4/P8).
   - Tesi 2 — momentum cross-sectional lento (P10, DSH): universo liquido, ribilanciamenti lenti,
     no-trade band, cap per asset/fattore.
   - Tesi 3 — trend + filtro di regime (filone P6/P7): filtro semplice e spiegabile, senza
     accumulare indicatori (ogni filtro consuma budget statistico).

5. **No-trade filter** (la strategia NON è obbligata a operare): spread relativo sopra soglia,
   profondità insufficiente, vol troppo bassa per coprire i costi, vol troppo alta per il profilo,
   funding≈0 dopo costi, dati stantii, correlazione aggregata alta, edge stimato < costo stressato.
   Pre-registrato, valutato out-of-sample, con penale per il numero di soglie provate.

6. **Esecuzione prima di nuovi segnali** (per il canary e oltre): prezzo teorico vs eseguito,
   slippage in bp, tempo al fill, quota maker/taker, partial fill, prezzo dopo 1/5/30 min;
   limit orders quando il fill-risk è compatibile; tetto di slippage oltre cui annullare;
   niente micro-ribilanciamenti; ordini minimi economici; il mancato fill ha un costo.

7. **Sub-account: confronto quantitativo 1 vs 2 vs 3 conti a 1.000€ PRIMA del live**
   (capitale utilizzabile, minimi d'ordine, costi, posizioni ottenibili, riconciliazione).
   Regola: separare i conti SOLO se l'isolamento riduce un rischio maggiore del costo economico
   e operativo introdotto. (La struttura a 3 conti non è un dogma.)

8. **Benchmark + test di incrementalità**: buy&hold dell'universo, long/flat semplice, equal-weight
   ribilanciato lentamente, cash. Ogni modifica deve dimostrare (nuovo − baseline) su rendimento
   stressato, robustezza, costi e rischio — altrimenti si scarta.

9. **Gate di capacità** (aggiunta al cancello per la fase live): capitale minimo praticabile,
   capitale massimo prima del degrado per slippage, posizioni massime, %ADV utilizzata, impatto
   di uscita normale/stressato, capacità per asset e portafoglio. Il gate dichiara l'INTERVALLO
   di capitale in cui il risultato è applicabile.

10. **Canary = apprendimento, non profitto immediato**: un conto, capitale minimo, nessun aumento
    automatico; metriche = fedeltà del modello di esecuzione (slippage reale vs previsto, fee
    effettive, latenza, riconciliazione, P&L ledger vs exchange); avanzamento solo dopo finestra
    predefinita senza anomalie, non perché "pochi trade sono andati bene".

11. **Complexity budget**: aggiungere componenti solo con beneficio misurabile (rendimento
    stressato, DD, costi, errori operativi, osservabilità); altrimenti è debito tecnico — anche
    se funziona.

12. **Research score ≠ allocation score**: capitale solo a strategie che superano ENTRAMBI.

## Priorità del prossimo ciclo (ordinate)

1. Ledger completo dei costi reali + **cost-to-edge** per le misure in essere (P6 inclusa).
2. **Benchmark e test di incrementalità** per P6/P7.
3. **Gate di capacità** nel pacchetto di promozione.
4. **Confronto 1 vs 3 sub-account** prima del live.
5. Una sola **tesi di capitale** in validazione (ora: trend/P6; carry in raccolta; momentum = ricerca).
6. **No-trade filter** pre-registrato (per la fase canary).

## Nota di onestà (dal documento, sottoscritta)

Se dopo questo processo non emerge un'aspettativa netta positiva, la conclusione PIÙ PROFITTEVOLE
può essere **non aumentare il capitale**: significherebbe che, a queste dimensioni, il costo di
ricerca ed esecuzione supera l'edge dimostrabile. Meglio saperlo con numeri che scoprirlo con soldi.

---
*Adottato da Hermes il 30/09/2026. Lane E1 "economia unitaria" aggiunta alla coda (candidati.json).*
