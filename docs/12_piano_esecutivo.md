# 12 — Piano esecutivo: dalla diagnostica alla redditivita'

> **Data:** 2026-09-28 · **Autore:** [dsh] (sessione Windows) · **Stato:** R1 avviato, codice e test
> consegnati; R2-R4 pianificati con criteri di accettazione.
>
> Il piano nasce da `docs/11_audit_radicale_2026-09-28.md`. Ogni rilascio ha un **criterio di
> accettazione verificabile**: se il criterio non passa, il rilascio non e' finito, non importa
> quanto codice e' stato scritto.

---

## 0. Il principio che tiene insieme il piano

**La verita' prima del rendimento.** Il sistema precedente non e' morto per una strategia
sbagliata: e' morto perche' **non poteva accorgersi di perdere** — `legacy/trades.db` ha quattro
tabelle e zero righe, il PnL degli scalper era una costante scritta a mano, il kill switch non
poteva scattare. Ogni rilascio qui sotto esiste per rendere impossibile ripetere quel guasto.

L'ordine **non e' negoziabile**: contabilita' -> potenza statistica -> cancello corretto ->
rischio -> esecuzione. Saltare un passaggio riporta al legacy, che aveva l'esecuzione e non
aveva la verita'.

---

## 1. Roadmap: quattro rilasci

| # | Rilascio | Contenuto | Dipende da | Criterio di accettazione |
| :-: | :--- | :--- | :--- | :--- |
| **R1** | **Verita'** | ledger append-only; freschezza delle tariffe; quarantena di `legacy/` | — | ogni PnL deriva da fill reali; un verdetto cita la provenienza del dato; nessun import da `legacy/` |
| **R2** | **Potenza statistica** | universo point-in-time su USDT; correzioni di molteplicita' nel cancello | R1 | un nodo giudicato con `n_eff >= 300` e PBO dichiarato, **o** la dimostrazione numerica che nessun edge sopravvive |
| **R3** | **Rischio** | `rischio.py` applicato al nodo promosso; governatore dei drawdown attivo | R2 | maxDD del nodo sotto il 25% sulla stessa finestra, con lo stesso numero di operazioni |
| **R4** | **Esecuzione** | order state machine idempotente, paper trading, kill switch con test | R3 | 30 giorni di dry-run con ledger riconciliato a 0,01 EUR e slippage misurato vs assunto |

**Il traguardo di R3 e' l'unico che conta per la redditivita'.** Il quadro della catena e'
inequivocabile (dodici nodi misurati): **tutte** le famiglie reversal/mean-reversion/calendario
perdono a qualunque tariffa; **tutte** le famiglie trend hanno expectancy netta positiva a fee
spot ma con la stessa firma di fallimento — DD 47-57% e edge concentrato in un regime. Non manca
il segnale: **manca il domatore del drawdown.** La leva giusta e' **quanto si rischia per
operazione**, non come si esce (il chandelier ATR del nodo P1 ha *peggiorato* tutto: DD 55,6%
contro 47,0%).

---

## 2. Cosa e' stato consegnato in R1 (e parte di R3)

Tutto verificato: **333 test verdi** (erano 241), `ruff` pulito, nessun avviso.

| modulo | cosa fa | perche' esiste |
| :--- | :--- | :--- |
| `src/money/contabilita.py` | ledger append-only JSONL; match FIFO; commissioni e funding; drawdown **da picco**; `verifica_integrita()`; `riconcilia()` | la causa radice n.1: senza PnL vero, ogni altra metrica e' un'opinione |
| `src/money/statistica.py` | bootstrap **a blocchi**; `n_effettivo`; t **Newey-West**; **Sharpe deflazionato**; **PBO via CSCV** | il cancello dichiara di non correggere molteplicita' ne' autocorrelazione: due difetti dichiarati restano difetti |
| `src/money/rischio.py` | stop ATR dal lato giusto; size da R; Kelly frazionario; **vol targeting (spec P2)**; guardie pre-trade fail-closed; governatore dei drawdown; kill switch in **6 passi ordinati** | il layer di rischio precedente era decorativo: `DRAWDOWN_THRESHOLD` definito e mai confrontato |
| `src/money/costi.py` | `Tariffa.verificato_il` + `fonte`; `verifica_freschezza()` con scadenza a 90 giorni | la costante piu' importante del progetto era un numero senza data di validita', con due avvisi di variazione fee aperti su OKX EEA |
| `legacy/QUARANTENA.md` | 13 difetti documentati con `file:riga`; regole di non-esecuzione e non-import | "taglio dei rami secchi": la memoria resta, la dipendenza no |
| `tests/test_*.py` (5 file) | 92 test nuovi | una guardia senza un test che la viola e' una guardia che non esiste |

**Le tre scelte di progetto che contano piu' del codice:**

1. **Fail-closed ovunque.** `verifica_pre_trade` non solleva su un NaN: **rifiuta** l'ordine.
   `StatoRischio.arresto()` senza osservazioni ritorna `stato_inattendibile`. Il contrario
   esatto del legacy, dove `exposure.json` mancante produceva `{"exposure": 1.0}`.
2. **Il PnL si costruisce solo dai fill**, con match FIFO. Mai da "l'ordine non c'e' piu'":
   e' il bug di `sell_grid_bot.py:158`, che contava un ordine cancellato come riempito.
3. **La sequenza del kill switch e' il contenuto**: scheduler prima dei bot (i watchdog li
   riavviavano), poi cancel filtrati, poi **chiusura delle posizioni** (il legacy si fermava al
   passo 2 e lasciava l'inventario scoperto), poi ledger, poi notifica che fallisce in modo
   rumoroso, poi riconciliazione.

---

## 3. Correzione all'audit: una mia raccomandazione e' stata falsificata

Nell'audit avevo scritto che il vincolo era la **potenza statistica** e che l'universo andava
allargato oltre le 18 coppie EUR (avevo verificato: BTC/USDT su `eea.okx.com` dal 2018-01-11,
407 coppie spot USDT attive). **Hermes ha corso esattamente quel test (P5) e l'ha falsificato:**
su 61/407 coppie con universo congelato *prima* del risultato, la stima si **diluisce** invece di
stringersi — t da 1,620 a **1,441**, expectancy da +7,99% a +4,03%, IC90 che attraversa lo zero,
DD 98,9%.

**Quindi la mia spiegazione del nodo A era sbagliata, e il dato di P5 e' quello che vale.**
Resta vera un'altra cosa, e va detta per come e': allargare l'universo non era la leva del
rendimento, era la leva della **falsificabilita'**. Il test l'ha dimostrato: da "non misurabile su
n=35" a "misurato e negativo su n=263". **Un'ipotesi morta con numeri vale piu' di un'ipotesi viva
senza.** La lezione per il piano: R2 non promette un edge, promette di **decidere**.

---

## 4. Le metriche da monitorare

### 4.1 Cancello v2 — blocca una promozione

| metrica | soglia | dove |
| :--- | :--- | :--- |
| `n` e `n_effettivo` | `n >= 30`, e `n_effettivo >= 30` | `statistica.verdetto_statistico` |
| Intervallo a blocchi (IC90) | estremo inferiore **> 0** | `intervallo_media_blocchi` |
| t Newey-West | **> 1,65** | `t_stat_newey_west` |
| Sharpe deflazionato | **> 0,95** | `sharpe_deflazionato` con `n_tentativi` dichiarato |
| PBO | **< 0,20** | `pbo_cscv` |
| Drawdown da picco | **<= 25%** | ricalcolato dai ritorni, mai passato dal chiamante |
| Copertura del pedaggio | **>= 3x** | invariato dal cancello attuale |
| Rilevanza | **> benchmark risk-free** (3,5%) | criterio 7 con benchmark **obbligatorio** |
| Indipendenza dai blocchi | fail-closed | oggi passa di default: va chiuso |
| Freschezza tariffa | **<= 90 giorni** | `costi.verifica_freschezza` |

### 4.2 Esercizio — spegne il sistema

| metrica | soglia | frequenza |
| :--- | :--- | :--- |
| Riconciliazione ledger/exchange | |delta| <= **0,01 EUR** | giornaliera |
| Sharpe netto (dopo fee, spread, funding, slippage) | **> 1,0** su 12 mesi | mensile |
| Sortino netto | **> 1,5** | mensile |
| Calmar (rendimento / maxDD) | **> 1,0** | mensile |
| Slippage realizzato / assunto | **<= 1,5x** | per operazione, rolling |
| Costo medio per operazione | <= **1/3** dell'edge lordo medio | rolling |
| Degrado live vs backtest | expectancy live >= **50%** della backtest | primi 90 giorni |
| Posizioni orfane (senza stop exchange-side) | **0**, sempre | continua |
| Perdita giornaliera / settimanale | **2% / 5%** -> stop | automatica |
| Drawdown da picco | **10%** -> kill switch; **20%** -> chiusura | automatica |

---

## 5. Istruzioni operative

```powershell
# 1) la suite: deve restare verde E senza avvisi
python -m pytest tests -q

# 2) il ledger: leggere lo stato senza codice
Get-Content dati_cache/ledger/operazioni.jsonl | Select-Object -Last 20

# 3) freschezza della tariffa (fallisce se > 90 giorni: e' voluto)
python -c "from money.costi import get_tariffa, verifica_freschezza as v; print(v(get_tariffa()))"

# 4) il vol targeting della spec P2, su rendimenti solo-passati
python -c "from money.rischio import fattore_vol_target as f; print(f([0.05,-0.05]*15))"

# 5) la quarantena: nessun modulo del progetto importa da legacy/
python -m pytest tests/test_quarantena_legacy.py -q
```

**Prima di scrivere una riga di esecuzione (R4) restano da fare, in quest'ordine:** criteri 5 e 8
del cancello chiusi (drawdown ricalcolato internamente; indipendenza fail-closed); criterio 7 con
benchmark obbligatorio ed esposizione in unita' canonica; `n_tentativi` come campo obbligatorio di
`Esito`; provenance del dato (hash di `SerieBarre.chiave()`, cache, intervallo) dentro ogni
verdetto.

---

## 6. Cosa non fare

1. **Non un'altra strategia sulla stessa finestra.** Dodici nodi misurati; la settima ipotesi non
   e' un progresso, e' un costo. La leva e' il **DD**, non il segnale.
2. **Non abbassare una soglia** per far passare qualcosa. E' la qualita' piu' preziosa del
   progetto e va difesa.
3. **Non riaccendere la flotta legacy**, nemmeno "solo per provare".
4. **Non accendere la leva per alzare il rendimento.** Con DD 47% il problema e' l'esposizione,
   e la leva moltiplica il problema invece della soluzione.
5. **Non costruire dashboard prima del ledger.** Il progetto precedente aveva una dashboard
   aggregata e quattro tabelle vuote sotto.
