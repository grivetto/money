# P15 — MVRV regime su BTC: da correlazione a strategia (2026-10-15)

> **Verdetto: ARCHIVIATA (griglia dichiarata: INSUFFICIENTE per n; esplorativa:
> expectancy OOS negativa).**
>
> La correlazione più forte mai vista in questo progetto (MVRV → rendimento 30g,
> **t = +20,96 su 5736 giorni**) **non sopravvive** alla traduzione in una
> strategia con costi reali. È la stessa firma di P1/P3/P5/P14: il segnale
> "spiega" il passato ma non paga il pedaggio.

---

## 1. Da dove nasce (il dato che ha motivato la misura)

`setaccia_onchain.py` del 2026-10-15, sui dati CoinMetrics appena scaricati:

| asset | metrica | corr | t | n |
| :--- | :--- | ---: | ---: | ---: |
| btc | CapMVRVCur → rend. 30g | **+0,267** | **+20,96** | 5736 |
| btc | CapMVRVCur (z) → rend. 30g | +0,240 | +18,41 | 5556 |
| btc | F&G → rend. 30g | +0,131 | +7,40 | 3144 |
| doge | F&G → rend. 30g | +0,210 | +12,02 | 3144 |

Con 5766 giorni di storia (2011 → 2026) e 131 coppie su 290 sopra |t| > 2,5,
questo era il candidato più forte mai emerso. **Una correlazione non è un edge:**
senza entrata, uscita e costi non si sa se sopravvive al pedaggio.

---

## 2. Il protocollo (dichiarato PRIMA dei numeri)

- **Segnale**: z-score di `CapMVRVCur` su finestra mobile W, **solo passato**
  (finestra `t-W..t-1` — nessun look-ahead).
- **Regola long/flat** (mai short: il lato short non è disponibile su spot EEA):
  entra quando `z < -z_in`, esce quando `z > z_out`.
- **Esecuzione**: segnale a fine giornata t, prezzo di esecuzione del giorno t+1.
- **Costi**: ciclo **0,630%** = round-trip spot OKX EEA 0,550% (dal conto,
  verificato 27/09) + slippage 0,04%/lato. Applicato a ogni entrata e uscita.
- **Griglia dichiarata**: W ∈ {180, 365} × z_in ∈ {1.0, 1.5} × z_out ∈ {0.0, 0.5}
  = **8 varianti**. Selezione su addestramento (2011→2018), **verifica OOS unica**
  (2019→2026).
- **Riferimento obbligatorio**: buy & hold sulla stessa finestra.
- **Controllo dichiarato**: segnale **invertito** — se anche l'invertito
  "funziona", il segnale è rumore con un drift.

---

## 3. Esito della griglia dichiarata

**NESSUNA variante con n ≥ 30 in addestramento.** Il segnale è troppo raro alle
soglie dichiarate:

| W | z_in | n addestramento |
| ---: | ---: | ---: |
| 180 | 1.0 | 10 |
| 180 | 1.5 | 4 |
| 365 | 1.0 | 4 |
| 365 | 1.5 | 2 |

→ **Verdetto formale: INSUFFICIENTE** (criterio 1 del cancello: n ≥ 30).

---

## 4. Misura esplorativa (soglie più lasche — NON promozione)

Eseguita **per capire se il segnale ha potenziale**, dichiarata come esplorativa
e non utilizzabile per una promozione. Soglie più lasche per avere n sufficiente:

### Addestramento (2011–2018)

| W | z_in | n | expectancy | t | drawdown |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 90 | 0,25 | 40 | +3,41% | +0,71 | **89,3%** |
| 90 | 0,50 | 30 | +4,50% | +0,73 | **91,1%** |
| 180 | 0,25 | 21 | +0,38% | +0,05 | 77,4% |
| 180 | 0,50 | 15 | −2,17% | −0,23 | 81,6% |

### Verifica OOS (2019–2026) — stesse varianti

| W | z_in | n | expectancy | t | drawdown |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 90 | 0,25 | 44 | **−0,26%** | −0,15 | 62,3% |
| 90 | 0,50 | 30 | **−1,59%** | −0,65 | 68,9% |
| 180 | 0,25 | 16 | **−1,81%** | −0,41 | 60,9% |
| 180 | 0,50 | 12 | **−1,72%** | −0,29 | 60,4% |

---

## 5. Perché è archiviata (i tre numeri che decidono)

1. **Expectancy OOS negativa in TUTTE le varianti** (−0,26% ÷ −1,81%). Non è
   "insufficiente": è **negativa**, cioè il segnale perde soldi.
2. **t-stat ≈ 0** (da +0,71 a −0,65). Anche quello positivo in addestramento non
   è distinguibile da zero: `corr +0,267` **non si traduce** in un t utilizzabile.
3. **Drawdown 60–91%.** Lontanissimo dal limite del cancello (≤25%). Con DD 90%
   in addestramento il capitale è distrutto prima di arrivare alla verifica.

**La lezione strutturale (identica a P1/P3/P5/P14):** una correlazione forte tra
una metrica e il rendimento futuro **non implica** che una strategia long/flat su
quella metrica paghi il pedaggio. La correlazione misura co-movimento; la
strategia paga **due volte** (entrata + uscita) e ogni ciclo costa 0,630%.

---

## 6. Ipotesi falsificate e cosa resta vero

| Ipotesi | Esito |
| :--- | :--- |
| "MVRV basso = buon momento per comprare" (long/flat) | **FALSIFICATA** — exp OOS negativa |
| "La correlazione t=+20,96 implica un edge tradabile" | **FALSIFICATA** — t strategia ≈ 0 |
| "Il segnale on-chain a bassa frequenza paga meno pedaggio" | **non sufficiente**: anche a bassa frequenza il segno dell'edge non regge OOS |

**Resta vero** (e va conservato): il **funding/carry** è ancora l'unico filone
vivo del progetto (C1 PASS, P12 descrittiva solida). L'on-chain, come segnale di
**direzione** long/flat, è chiuso.

---

## 7. Cosa NON è stato testato (onestà sui limiti)

- **Solo il lato long/flat.** Il lato short (dove MVRV alto predice ribasso) non è
  testato — richiede derivati, e su BTC EEA il funding è negativo.
- **Solo BTC.** Le altre 11 monete hanno dati ma non sono state misurate.
- **Solo MVRV.** Le altre 30 metriche (HashRate, SplyExUSD, flussi exchange...) e
  F&G/TVL non sono stati tradotti in strategie.
- **Nessun lag variabile.** Ho testato H esecuzione = t+1. Ritardi più lunghi
  (H=7, 30 giorni, dove la correlazione è più forte) **non** sono stati simulati:
  è un'ipotesi ancora aperta — la correlazione a 30 giorni era la più forte.

**Nota per il prossimo tentativo:** se si riprende l'on-chain, la variante da
testare è **H esecuzione ≥ 7 giorni** (la correlazione vive a orizzonte mensile,
non giornaliero) — ma va **pre-registrata** come voce nuova, non recuperata da qui.

---

## 8. Riproduzione

```bash
cd /home/marco/money
.venv/bin/python3 scripts/misura_p15_mvrv.py
```

Artefatto: `prove/P15_mvrv_regime.json`.
Dati: `data/esterni/onchain_btc.json` (CoinMetrics community, scaricato 15/10).
Costi: `money.costi` — `okx_eea_spot`, giro misto 0,550% (dal conto).
