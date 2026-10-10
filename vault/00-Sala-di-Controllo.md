# 🎛️ Sala di Controllo — Denaro

> Aggiornato: **2026-10-07** — [hermes]

## Stato in una riga
Ricerca: **nessuna promossa**, ma il filone funding carry ha i primi candidati descrittivi solidi (S2) e il canary C1 in validazione (review **15/10**).
Capitale: **≈1.100 €** su OKX, **zero bot live**, nessun ordine reale senza autorizzazione.

## Soldi
| Dove | Importo | Note |
|---|---|---|
| OKX main (funding) | ≈1.100 € | +1.000 € depositati il 03/10 (SEPA, verificato) |
| Sub-account | dust | mc2sub1 / marcosub1 / nuvolasub1 |
| **Totale flotta** | **≈1.100 €** | live: https://denaro.grivetto.eu (dashboard su /dashboard) |

## Ricerca — dove siamo
| Nodo | Stato | Risultato in una riga |
|---|---|---|
| P1 chandelier ATR | ❌ archiviata | lo stop in uscita peggiora tutto |
| P2 vol targeting | ❌ archiviata (30/09) | il sizing riduce il DD seriale ma NON il DD di portafoglio |
| P3 filtro SMA200 | ❌ archiviata | 6/8 ma DD 45,5% e t 1,58 |
| P5 Donchian esteso | ❌ archiviata | l'edge non regge l'allargamento |
| P10/P14 momentum | ❌ chiuso | P10 insufficiente; P14 archiviato su universo ampio |
| P13 cointegrazione | ❌ archiviata | 0 coppie passanti |
| **S1 scansione** (loop notturno) | 🔄 in corsa | 512 tentativi/giorno, 0 candidati; watchlist: rsi2-XRP, mom_abs |
| **S2 funding scan** | 🔎 descrittivi | 7 candidati lato short (DOGE/LINK/ADA ~+6% ann.); da pre-registrare |
| **S3 caccia adattiva** | ✅ eseguita 07/10 | 1.760 + 6.902 tentativi, **0 candidati** |
| **P4 funding carry** | ⏳ spec pronta | bozza self-contained (gate JEV ok), da chiudere in coda |

## Il traguardo
Prima promozione al cancello = **DD ≤ 25% + t ≥ 1,65 + expectancy ≥ 3× pedaggio**.
Poi, in fila: dry-run esecuzione → banco a secco → live con size minima. Dettagli in [[10-Pipeline-di-Ricerca]].

## Prossime mosse
1. **C1 canary (review 15/10)**: delta-neutral DOGE aperto; check funding normalizzato — review con dati OKX reali.
2. **P4 spec**: bozza pronta (supera gate JEV) → scrivere in `coda_catena/`, chiudere i 2 job fabbrica.
3. **Flotta in auto-start**: opencode + agy su tutti i nodi (fatto 07/10) — verificare tenuta al prossimo reboot.

Chi fa cosa: [[20-Squadra]].