# Pipeline di Ricerca — crea → misura → promuovi/archivia

Regola di fondo: **si misura prima di credere**. Ogni ipotesi diventa un "nodo" (modulo Python),
che passa una griglia dichiarata in addestramento, poi la verifica fuori campione, poi il cancello.

## Il cancello (8 criteri, tutti obbligatori)
1. n ≥ 30 operazioni fuori campione
2. IC bootstrap 90% con estremo inferiore > 0
3. t-stat > 1,65 (una coda, 5%)
4. profit factor > 1,20
5. maxDD ≤ 25%
6. expectancy ≥ 3× pedaggio
7. ≥ 10 €/anno su 1.000 € di capitale di riferimento
8. edge non concentrato in un solo blocco temporale

## Costi misurati (OKX EEA)
- **Spot** andata+ritorno misto: **0,550%** → soglia 3× = 1,65% netti/operazione
- **Swap** (scenario): **0,070%** — 7,9× più economico, si riporta ma non decide il verdetto

## Coda attuale (`money/coda_catena/`)
| Spec | Stato | Esito |
|---|---|---|
| P1 trend + ATR stop | ❌ | chandelier smentito: l'uscita non è la leva per il DD |
| P2 momentum vol-target | 🔄 DSH | **in corso** — l'ultimo attacco al DD |
| P3 trend + filtro SMA200 | ❌ 29/09 | 6/8; DD non risolto (45,5%) |
| P4 funding carry | ⏸️ | dati insufficienti (96 gg) |
| P5 Donchian esteso | ❌ | l'edge non regge l'allargamento d'universo |

## Il filone vivo — canale/trend su 10 majors USDT
Finestra di verifica 2024-06 → 2026-09 (dati USDT dall'ottobre 2020, tre regimi in addestramento):

| | Donchian 55/20 | P3 40g + canale20 |
|---|---|---|
| Expectancy netta | +7,99%/op | **+9,01%/op** |
| Copertura pedaggio | 14,5× | **16,4×** |
| IC90 | + | **+** |
| Profit factor | 1,97 | **2,01** |
| t-stat | 1,62 | 1,58 |
| maxDD | 47,0% | 45,5% |

**Unico ostacolo comune: il drawdown.** Il segnale è congelato; si lavora solo sul sizing (P2).

## Dove stanno i file
- Spec e stati: `money/coda_catena/` • Prove complete: `money/prove/` • Codice: `money/src/money/ricerca/`
