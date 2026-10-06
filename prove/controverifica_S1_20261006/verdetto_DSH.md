# Contro-verifica indipendente — scansione S1 (REQ-20261006-202344-5433843)

**Data:** 2026-10-06 20:26 UTC  
**Nodo:** DSH (omarchy) — ricalcolo da zero, nessun import del codice `money` (solo `numpy`/stdlib; qui nemmeno numpy).  
**Perimetro:** 5 configurazioni/simbolo top-descrittive della verifica (`>= 2024-06-01`) della scansione S1 (16 major, 32 config x 7 famiglie).  
**Dati:** `inputs/okx_eea_<SYM>-USDT_1d.json`, 2196 barre 1d per simbolo, ultima barra 2026-10-05.

## Assunzioni di costo (dichiarate)

- **Modello primario (identico alla scansione S1 ufficiale):** tariffa `okx_eea_con_perp`, giro misto = maker 0,08% + taker 0,10% = **0,18% per round trip** (pedaggio), più **slippage 0,04% per lato** applicato moltiplicativamente su entrambe le gambe (`netto = (1-s)(1+lordo)(1-s) - 1 - pedaggio`). Costo all-in ~0,26% per operazione.
- **Variante letterale del task:** fee 0,05%/lato (0,10% round trip) + slippage 4 bp/lato, cioè ~0,18% all-in. Riportata in tabella come `costi task` per trasparenza: è ~8 bp più ottimistica del modello ufficiale.
- **Costi doppi (robustezza c):** pedaggio 0,36% + slippage 0,08%/lato (~0,52% all-in).

> Nota di merito: per riprodurre i numeri ufficiali al 7° decimale ho dovuto usare **tutte** le barre presenti negli input (ultima **2026-10-05**), mentre il registro dichiara `FINE_STORIA = 2026-09-25`. Il ritaglio a 2026-09-25 cambia n di ±1 e l'expectancy di ~0,4 bp: non sposta il verdetto, ma è una discrepanza di dichiarazione da sanare.

## Tabella — numeri ricalcolati (verifica, costi ufficiali)

| # | config | simbolo | n | exp netta | t-stat | profit factor | DSR (vs 322 tentativi) | CI90 block bootstrap (10 op, 2000 iter) | P(exp>0) |
|---|--------|---------|---|-----------|--------|---------------|----------------------|------------------------------------------|---------|
| 1 | mom_abs(L=20) | DOGE/USDT | 35 | +6,80% | 0,865 | 3,206 | 0,098 | [-2,39%, +14,78%] | 0,773 |
| 2 | mom_abs(L=10) | XLM/USDT | 56 | +6,19% | 0,804 | 2,647 | 0,026 | [-2,01%, +14,35%] | 0,801 |
| 3 | mom_abs(L=10) | XRP/USDT | 61 | +5,15% | 0,842 | 2,544 | 0,022 | [-1,58%, +11,44%] | 0,794 |
| 4 | mom_abs(L=20) | XRP/USDT | 49 | +4,85% | 0,774 | 2,732 | 0,037 | [-1,93%, +11,08%] | 0,727 |
| 5 | rsi2(3,15,65) | XRP/USDT | 32 | +2,54% | 1,712 | 2,717 | 0,358 | [+0,78%, +4,02%] | 0,964 |

Soglia ufficiale di sopravvivenza: **DSR >= 0,95** (nessuno la supera; SR0 di benchmark = 0,370 per operazione, da 322 tentativi valutabili). Il DSR è ricalcolato qui per ogni caso con i parametri del meta ufficiale (322 tentativi, varianza Sharpe train 0,01605, skew 0 e curtosi 3 come `money.statistica`); nell'output ufficiale era calcolato solo per il simbolo selezionato per configurazione.

**Confronto con i numeri ufficiali (task / `scansione_S1_20261006_2022.json`):**

| # | config | simbolo | n uff. | n mio | exp uff. | exp mia | t uff. | t mio | esito |
|---|--------|---------|--------|-------|----------|---------|--------|-------|-------|
| 1 | mom_abs(L=20) | DOGE/USDT | 35 | 35 | +6,80% | +6,80% | 0,865 | 0,865 | identico |
| 2 | mom_abs(L=10) | XLM/USDT | 56 | 56 | +6,19% | +6,19% | 0,804 | 0,804 | identico |
| 3 | mom_abs(L=10) | XRP/USDT | 61 | 61 | +5,15% | +5,15% | 0,842 | 0,842 | identico |
| 4 | mom_abs(L=20) | XRP/USDT | 49 | 49 | +4,85% | +4,85% | 0,774 | 0,774 | identico |
| 5 | rsi2(3,15,65) | XRP/USDT | 32 | 32 | +2,54% | +2,54% | 1,712 | 1,712 | identico |

## Robustezza

### a) Due sub-periodi (per data di ingresso)

| config | simbolo | P1 [2024-06-01, 2025-07-01) n / exp | P2 [2025-07-01, fine] n / exp |
|--------|---------|------------------------------------------|--------------------------------|
| mom_abs(L=20) | DOGE/USDT | 13 / +18,21% | 22 / +0,06% |
| mom_abs(L=10) | XLM/USDT | 25 / +13,82% | 31 / +0,04% |
| mom_abs(L=10) | XRP/USDT | 28 / +13,60% | 33 / -2,02% |
| mom_abs(L=20) | XRP/USDT | 19 / +13,30% | 30 / -0,50% |
| rsi2(3,15,65) | XRP/USDT | 14 / +3,71% | 18 / +1,64% |

### b) Block bootstrap (blocchi contigui di 10 operazioni, 2000 iterazioni)

| config | simbolo | exp media | CI90 (partizione) | CI90 (blocchi scorrevoli) | P(exp>0) | n blocchi |
|--------|---------|-----------|-------------------|------------------------|---------|-----------|
| mom_abs(L=20) | DOGE/USDT | +6,80% | [-2,39%, +14,78%] | [-2,38%, +14,89%] | 0,773 | 4 |
| mom_abs(L=10) | XLM/USDT | +6,19% | [-2,01%, +14,35%] | [-2,12%, +16,16%] | 0,801 | 6 |
| mom_abs(L=10) | XRP/USDT | +5,15% | [-1,58%, +11,44%] | [-2,21%, +13,06%] | 0,794 | 7 |
| mom_abs(L=20) | XRP/USDT | +4,85% | [-1,93%, +11,08%] | [-2,17%, +10,72%] | 0,727 | 5 |
| rsi2(3,15,65) | XRP/USDT | +2,54% | [+0,78%, +4,02%] | [+0,93%, +4,42%] | 0,964 | 4 |

### c) Costi doppi (fee e slippage per lato x2) e variante costi del task

| config | simbolo | exp (costi ufficiali) | exp (costi x2) | t (x2) | PF (x2) | exp (costi task) |
|--------|---------|----------------------|----------------|--------|--------|------------------|
| mom_abs(L=20) | DOGE/USDT | +6,80% | +6,54% | 0,832 | 3,028 | +6,88% |
| mom_abs(L=10) | XLM/USDT | +6,19% | +5,93% | 0,770 | 2,501 | +6,27% |
| mom_abs(L=10) | XRP/USDT | +5,15% | +4,89% | 0,800 | 2,388 | +5,23% |
| mom_abs(L=20) | XRP/USDT | +4,85% | +4,58% | 0,732 | 2,533 | +4,93% |
| rsi2(3,15,65) | XRP/USDT | +2,54% | +2,28% | 1,537 | 2,468 | +2,62% |

### d) Sensibilità alla convenzione di partenza

Se si applica il segnale ripartendo da zero al 2024-06-01 (`dentro=False`), invece della convenzione del rig (stato calcolato sull'intera storia e operazioni filtrate per data di ingresso), i numeri cambiano:

| config | simbolo | n (convenzione rig) | n (riavvio al confine) | exp (riavvio) |
|--------|---------|---------------------|------------------------|---------------|
| mom_abs(L=20) | DOGE/USDT | 35 | 36 | +6,40% |
| mom_abs(L=10) | XLM/USDT | 56 | 56 | +6,19% |
| mom_abs(L=10) | XRP/USDT | 61 | 61 | +5,15% |
| mom_abs(L=20) | XRP/USDT | 49 | 50 | +4,76% |
| rsi2(3,15,65) | XRP/USDT | 32 | 32 | +2,54% |

## Verdetti

Criterio: **sì** = numeri riprodotti *e* robusti (CI90>0, entrambi i sub-periodi positivi, regge i costi doppi); **parziale** = numeri riprodotti ma robustezza incompleta; **no** = numeri non riprodotti o segno negativo. Il criterio NON è la significatività sotto selezione multipla: quella resta il DSR, e nessuno la supera.

| # | config | simbolo | regge i numeri? | merita escalation a esperimento? |
|---|--------|---------|-----------------|----------------------------------|
| 1 | mom_abs(L=20) | DOGE/USDT | **parziale** | NO — descrittivo di selezione multipla (512 tentativi, 322 valutabili): t basso, CI90 della expectancy include 0 e/o sub-periodo negativo. |
| 2 | mom_abs(L=10) | XLM/USDT | **parziale** | NO — descrittivo di selezione multipla (512 tentativi, 322 valutabili): t basso, CI90 della expectancy include 0 e/o sub-periodo negativo. |
| 3 | mom_abs(L=10) | XRP/USDT | **parziale** | NO — descrittivo di selezione multipla (512 tentativi, 322 valutabili): t basso, CI90 della expectancy include 0 e/o sub-periodo negativo. |
| 4 | mom_abs(L=20) | XRP/USDT | **parziale** | NO — descrittivo di selezione multipla (512 tentativi, 322 valutabili): t basso, CI90 della expectancy include 0 e/o sub-periodo negativo. |
| 5 | rsi2(3,15,65) | XRP/USDT | **sì** | SOLO come esperimento pre-registrato MIRATO (ipotesi singola), non come candidato: regge bootstrap/costi x2 ma DSR=0,358 << 0,95 e t=1,712 < 2. |

### Dettaglio dei verdetti

**1. mom_abs(L=20) su DOGE/USDT — parziale.** Ricalcolo: n=35, exp=+6,80%, t=0,865, PF=3,206 (ufficiale: n=35, exp=+6,80%, t=0,865). Sub-periodi: P1 n=13 exp=+18,21%, P2 n=22 exp=+0,06%. CI90 expectancy: [-2,39%, +14,78%] (P>0 = 0,773). Costi x2: exp=+6,54%, t=0,832. DSR=0,098 (SR=0,146 vs SR0=0,370). Motivo: numeri ufficiali riprodotti esattamente; CI90 include 0. Escalation: NO — descrittivo di selezione multipla (512 tentativi, 322 valutabili): t basso, CI90 della expectancy include 0 e/o sub-periodo negativo.

**2. mom_abs(L=10) su XLM/USDT — parziale.** Ricalcolo: n=56, exp=+6,19%, t=0,804, PF=2,647 (ufficiale: n=56, exp=+6,19%, t=0,804). Sub-periodi: P1 n=25 exp=+13,82%, P2 n=31 exp=+0,04%. CI90 expectancy: [-2,01%, +14,35%] (P>0 = 0,801). Costi x2: exp=+5,93%, t=0,770. DSR=0,026 (SR=0,107 vs SR0=0,370). Motivo: numeri ufficiali riprodotti esattamente; CI90 include 0. Escalation: NO — descrittivo di selezione multipla (512 tentativi, 322 valutabili): t basso, CI90 della expectancy include 0 e/o sub-periodo negativo.

**3. mom_abs(L=10) su XRP/USDT — parziale.** Ricalcolo: n=61, exp=+5,15%, t=0,842, PF=2,544 (ufficiale: n=61, exp=+5,15%, t=0,842). Sub-periodi: P1 n=28 exp=+13,60%, P2 n=33 exp=-2,02%. CI90 expectancy: [-1,58%, +11,44%] (P>0 = 0,794). Costi x2: exp=+4,89%, t=0,800. DSR=0,022 (SR=0,108 vs SR0=0,370). Motivo: numeri ufficiali riprodotti esattamente; P2<=0; CI90 include 0. Escalation: NO — descrittivo di selezione multipla (512 tentativi, 322 valutabili): t basso, CI90 della expectancy include 0 e/o sub-periodo negativo.

**4. mom_abs(L=20) su XRP/USDT — parziale.** Ricalcolo: n=49, exp=+4,85%, t=0,774, PF=2,732 (ufficiale: n=49, exp=+4,85%, t=0,774). Sub-periodi: P1 n=19 exp=+13,30%, P2 n=30 exp=-0,50%. CI90 expectancy: [-1,93%, +11,08%] (P>0 = 0,727). Costi x2: exp=+4,58%, t=0,732. DSR=0,037 (SR=0,111 vs SR0=0,370). Motivo: numeri ufficiali riprodotti esattamente; P2<=0; CI90 include 0. Escalation: NO — descrittivo di selezione multipla (512 tentativi, 322 valutabili): t basso, CI90 della expectancy include 0 e/o sub-periodo negativo.

**5. rsi2(3,15,65) su XRP/USDT — sì.** Ricalcolo: n=32, exp=+2,54%, t=1,712, PF=2,717 (ufficiale: n=32, exp=+2,54%, t=1,712). Sub-periodi: P1 n=14 exp=+3,71%, P2 n=18 exp=+1,64%. CI90 expectancy: [+0,78%, +4,02%] (P>0 = 0,964). Costi x2: exp=+2,28%, t=1,537. DSR=0,358 (SR=0,303 vs SR0=0,370). Motivo: numeri ufficiali riprodotti esattamente. Escalation: SOLO come esperimento pre-registrato MIRATO (ipotesi singola), non come candidato: regge bootstrap/costi x2 ma DSR=0,358 << 0,95 e t=1,712 < 2.

## Conclusioni

- **I numeri ufficiali si riproducono esattamente** (n, expectancy e t-stat al 7° decimale) su tutte e 5 le configurazioni, una volta usata tutta la serie degli input. La pipeline della scansione S1 è quindi aritmeticamente corretta: il problema non è un bug di calcolo.
- **4 su 5 non reggono** (i `mom_abs`): expectancy trainata da poche operazioni grandi (win rate 26-46%), secondo sub-periodo piatto o negativo (+0,06% / +0,04% / -2,02% / -0,50%), CI90 bootstrap che include lo zero e DSR <= 0,10. Sono code di selezione, non edge.
- **1 su 5 regge la robustezza descrittiva** (`rsi2(3,15,65)` su XRP): positivo in entrambi i sub-periodi (+3,71%, +1,64%), CI90 della expectancy sopra zero ([+0,78%, +4,02%]) anche con blocchi scorrevoli e con costi doppi (+2,28%, t=1,54). **Ma** n=32, t=1,71 < 2 e soprattutto **DSR = 0,36**, molto sotto la soglia 0,95: è l'unico che merita un esperimento pre-registrato mirato, non una promozione.
- **Discrepanza da sanare (dichiarazione, non calcolo):** il registro dichiara `FINE_STORIA = 2026-09-25`, ma i numeri ufficiali si ottengono solo includendo le barre fino al 2026-10-05. L'impatto sui verdetti è nullo, ma la finestra va dichiarata in modo coerente.
- **Coerente con l'esito ufficiale**: 0 candidati (DSR < 0,95) resta la conclusione corretta; questi 5 record sono descrittivi e non promuovibili.
