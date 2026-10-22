# Ipotesi pre-registrata: Funding Extreme Contrarian (Crowding Unwind)

**Nome**: funding_extreme_contrarian
**Data pre-registrazione**: 2026-10-22
**Stato**: pre-registrata PRIMA dei numeri (regola ROADMAP Fase 3)

## Motivazione economica
Il funding rate è il prezzo della leva: quando è estremo, una parte del mercato è
sovraffollata (long se funding >> 0, short se funding << 0). Il sovraffollamento è
fragile: la parte affollata paga un costo crescente per mantenere la posizione e
tende a chiudere (unwind) quando il costo supera la convinzione. L'unwind è un
flusso direzionale contro la posizione affollata → il prezzo reverte.

## Dati (reali, già in ~/money/data)
- Funding Bybit linear perp: `data/funding_bybit/*.json` — 58 simboli, 8h, 2020–2026.
- Prezzi Bybit spot 1d: `data/cache/bybit_<SYM>-USDT_1d.json` — 58 simboli, 2021–2026.
- Nessun dato futuro: z-score a t usa solo giorni ≤ t−1; entry al close di t
  (dopo che tutti i funding di t sono noti).

## Segnale
- F_t = somma dei funding del giorno t (3 periodi 8h, UTC; richieste ≥2 osservazioni).
- z_t = (F_t − mean(F_{t−30..t−1})) / std(F_{t−30..t−1}), richiesti ≥25 giorni validi.
- Evento: |z_t| > 2.0.
- Direzione: contrarian — z_t > 0 → short; z_t < 0 → long.
- Entry: close_t. Exit: close_{t+H}. H primario = 3 giorni.
- Un solo trade aperto per simbolo (no overlapping).

## Costi
- Round trip 0.30% del nozionale (taker 0.10% × 2 + slippage 0.05% × 2).
- Nozionale di riferimento: 50€ → fee 0.15€ per trade.

## Criteri di falsificazione (pre-dichiarati)
- mean net ≤ 0, oppure
- t ≤ 1.65, oppure
- IC bootstrap 90% ≤ 0, oppure
- PF ≤ 1.20, oppure
- maxDD > 25%, oppure
- expectancy < 3 × fee (0.45€ per trade su 50€).
Se uno qualsiasi fallisce → ipotesi NON promossa, archiviata con evidenza.

## Sensitività (riportate, NON usate per selezione)
- H ∈ {1, 3, 5, 7}; soglie |z| ∈ {1.5, 2.0, 2.5, 3.0}.
- Lato positivo (funding > 0) e negativo (funding < 0) riportati separatamente.
- La configurazione primaria è |z|>2.0, H=3: le altre sono sensitivity, non
  candidate. Nessuna selezione ex-post.

## Limiti dichiarati
- Prezzi spot come proxy dei perp (basis non modellata); l'esecuzione reale è
  perp per gli short e spot/perp per i long.
- Eventi cross-sectionalmente correlati (funding estremo è spesso market-wide):
  l'indipendenza è parziale; il DSR/closing test lo affronta.
- Campione 2020–2026 include regimi diversi; riportare per anno.
