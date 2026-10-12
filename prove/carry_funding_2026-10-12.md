# Carry funding delta-neutral — misura reale (2026-10-12)

> Misura read-only su OKX EEA (API pubblica `funding-rate-history`, 289 periodi = 96,3 giorni).
> Autore: agente Hermes. Scopo: stabilire **se** il carry funding batte l'Earn, **prima** di
> allocare un euro. Nessun ordine inviato.

## 1. La strategia

Long spot (asset X) + short perp (X, isolated), stesso nozionale `N` → esposizione netta ~0.
Si incassa il **funding** del perp quando il tasso è positivo (perp in contango, caso normale
nel mercato crypto). Il PnL di prezzo delle due gambe si annulla (a meno del basis drift).

## 2. Funding misurato (netto fee)

Fee OKX EEA acctLv2 (con X-Perps): spot taker 0,10%, perp taker 0,05% → round-trip **0,30%**.
(maker: spot 0,08%, perp 0,02% → round-trip 0,20%).

| Coppia | funding lordo 96g | netto taker | **netto/anno (taker)** | % periodi funding>0 |
|---|---|---|---|---|
| ADA-USD-SWAP | +2,442% | +2,142% | **+8,1%** | 97% |
| LINK-USD-SWAP | +2,160% | +1,860% | +7,0% | 93% |
| DOGE-USD-SWAP | +1,952% | +1,652% | +6,3% | 90% |
| XRP-USD-SWAP | +1,621% | +1,321% | +5,0% | 83% |
| BTC-USD-SWAP | (media 100p) | — | ~+5,6% lordo | 89% |

## 3. Il conto che decide: rendimento sul CAPITALE, non sul nozionale

Il rendimento qui sopra è sul **nozionale**. Ma il capitale richiesto è
`C = N (spot) + N/lev (margine perp)`, quindi il rendimento sul capitale è:

    r_capitale = funding / (1 + 1/lev)

| leva perp | capitale C | r sul capitale (funding 8,1%) | distanza liquidazione |
|---|---|---|---|
| 1x | 2,00·N | **4,05%** | 99,5% |
| 2x | 1,50·N | 5,40% | 49,5% |
| 3x | 1,33·N | 6,08% | 32,8% |
| 5x | 1,20·N | 6,75% | 19,5% |
| 10x | 1,10·N | 7,36% | 9,5% |

## 4. Verdetto

- A **leva 1x** (rischio di liquidazione trascurabile): il carry rende **~4% sul capitale** →
  **sotto** l'Earn USDC (che oggi rende ~4–5% **senza** rischio direzionale, senza funding,
  senza gestione).
- A **leva 3–5x**: rende 6,1–6,8% sul capitale, ma la liquidazione è a **20–33%** di distanza:
  uno spike di prezzo chiuderebbe la posizione in perdita. Rischio non banale su crypto.
- Su **1.100 €** la differenza tra l'Earn e il carry a 3x è ~+18 €/anno. **Non giustifica il
  rischio operativo** (due gambe, margine, funding che può girare negativo, riconciliazione).

**Conclusione: il carry funding è un edge reale ma sottile; a rischio comparabile NON batte
l'Earn in modo significativo. Non è la strada per "raggiungere profitti" con questo capitale.**

## 5. Cosa resta (onesto)

- **Rendimento risk-free**: massimizzare l'Earn sui fondi idle → +~5%/anno, zero rischio.
- **Edge direzionale**: lo screener (312k config, DSR 0,95) non ne ha trovati: 0 promossi.
- **Il canary** (C1) resta ciò per cui esiste: **validare l'esecuzione** (fill, fee, funding,
  riconciliazione) — non generare profitto. Finestra 14g aperta il 01/10, review 15/10.

## 6. Fonti

- `GET https://eea.okx.com/api/v5/public/funding-rate-history?instId=<X>&limit=400`
- `GET https://eea.okx.com/api/v5/public/funding-rate?instId=<X>`
- Fee: `money/costi.py` (tabelle ufficiali OKX EEA, conto con X-Perps, verificate live 06/10).
