# 🎛️ Sala di Controllo — Denaro

> Aggiornato: **2026-10-14** — [hermes]

## Stato in una riga
Ricerca: **filone esplorativo chiuso** (6 arene × 59 simboli / 5+ anni → 0 edge validato); carry misurato (non batte l'Earn); canary C1 in validazione (review **15/10**); audit interno chiuso — piano E1–E4 in corso.
Capitale: **≈1.100 €** su OKX; **zero bot live** fuori dal canary C1 (size minima); nessun ordine reale senza autorizzazione.

## Soldi
| Dove | Importo | Note |
|---|---|---|
| OKX main (funding + Simple Earn) | ≈1.100 € | +1.000 € depositati il 03/10 (SEPA, verificato) |
| Sub-account | dust | mc2sub1 / marcosub1 / nuvolasub1 |
| **Totale flotta** | **≈1.100 €** | live: https://denaro.grivetto.eu (dashboard su /dashboard) |

## Ricerca — dove siamo
| Nodo | Stato | Risultato in una riga |
|---|---|---|
| P1–P6, P10–P14 (trend / momentum / vol / pairs) | ❌ archiviate | nessun edge oltre il pedaggio |
| Microstruttura (order-flow, MM, spread) | ❌ chiusa 12/10 | 0 edge su tick reali; dati tick Bybit (5+ anni) riusabili |
| On-chain / sentiment | ❌ bocciati 12/10 | walk-forward negativo |
| Multi-timeframe (1d/4h/1h) | ❌ completo 13/10 | 0 candidati |
| P4 funding carry | ❌ misurata 08/10 | non batte l'Earn a rischio comparabile; ri-misura quando la storia >180 g |
| S4 caccia continua | 🔄 in cron (*/5) | satura (316k tentativi, 0 candidati); resta come guardia |
| Watchlist S1 (rsi2-XRP, mom_abs) | ⏸ | descrittivi, mai promossi |
| **C1 canary carry DOGE** | 🔄 in validazione | delta-neutral dal 01/10; nel cancello (gate unico + stop ATR + kill switch); review **15/10** |

## Il traguardo
Prima promozione al cancello = **DD ≤ 25% + t ≥ 1,65 + expectancy ≥ 3× pedaggio**.
Poi, in fila: dry-run esecuzione → banco a secco → live con size minima. Dettagli in [[10-Pipeline-di-Ricerca]].

## Prossime mosse
1. **Review C1 (15/10)**: dati OKX reali; decisione sul carry.
2. **Piano E1–E4** (audit 13/10): chiudere le 11 lacune; i fix della notte 13→14 sono già atterrati.
3. **Kaggle TPU** (free AI per la flotta): in coda per lo slot; quando live, URL+key su mc2 (`~/kaggle-tpu-lab`). Skill `kaggle-free-ai-server`.
4. **Carry**: ri-misura con soglia netta 8% quando la storia supera ~180 giorni.

Chi fa cosa: [[20-Squadra]].
