# Microstruttura e order-flow: misure ed esiti (2026-10-12)

Contesto: la ricerca su candele (5+ anni, 20 famiglie, 31 simboli, 2 scenari di fee)
dà **0 candidati** con `sr0 ≈ 0.41`: le famiglie predittive non hanno edge dopo le fee,
e il train sharpe ≈ 0 anche a fee 0.07% dimostra che non è solo questione di costi.
Qui si documentano i due fronti successivi, entrambi su **dati tick reali Bybit**
(`public.bybit.com/trading`, gratuiti, con lato aggressore).

## 1. Order-flow imbalance -> rendimento del minuto successivo

Dati: 29 giorni di tick, 2026-09-13 -> 2026-10-11.
- DOGEUSDT: 13.080.860 trade, 41.701 minuti
- SOLUSDT: 17.018.557 trade, 41.731 minuti

Segnale: `imb[m] = (volBuy - volSell) / (volBuy + volSell)` nel minuto m.
Obiettivo: rendimento realizzato nel minuto m+1 = `(close[m+1]-close[m])/close[m]`.

| Simbolo | corr(imb, rend+1) | t-stat | exp. lorda (segui flusso) | exp. lorda (invertito) |
|---|---|---|---|---|
| DOGE | **-0.0121** | -2.46 | -0.0013% | +0.0013% |
| SOL | **-0.0075** | -1.53 | -0.0003% | +0.0003% |

Costo taker perp (andata+ritorno) = **0.11%**. L'edge lordo e' **85-350x piu' piccolo
dei costi**. Lettura: il flusso a 1 minuto non ha potere direzionale sfruttabile; il
segno leggermente negativo (micro-reversal) e' coerente con la letteratura ma
economicamente irrilevante.

## 2. Market making simulato (ultima arena)

Modello dichiarato (ottimistico di proposito): quotazione passiva, bid a `px*(1-delta)`;
fill per **attraversamento** del livello (upper bound del fill rate: assume di essere in
cima al book); uscita a `entry*(1+target)`; chiusura **al mercato** dopo `timeout`
(adverse selection). Fee Bybit perp: maker 2 bps, taker 5.5 bps.

29 giorni, DOGEUSDT (26.919 fill a delta=1) e SOLUSDT (21.954 fill):

| delta | timeout | DOGE exp.netta | t | SOL exp.netta | t |
|---|---|---|---|---|---|
| 1 bp | 300s | -0.0598% | **-89.6** | -0.0612% | **-94.5** |
| 1 bp | 900s | -0.0585% | -54.0 | -0.0589% | -58.0 |
| 5 bps | 300s | -0.0732% | -40.1 | -0.0639% | -42.2 |
| 10 bps | 900s | -0.0676% | -12.6 | -0.0572% | -12.2 |
| 20 bps | 900s | -0.0638% | -4.9 | -0.0451% | -3.5 |

**Ogni configurazione perde**, con t-stat schiaccianti anche su 20+ mila fill.
Meccanismo: il fill avviene mentre il prezzo scende contro di te; quando il mercato non
torna entro il timeout, la chiusura forzata al mercato mangia piu' dello spread
catturato. E' il modo in cui il market making retail muore a queste fee.

## 3. Spread reale vs fee maker (perche' il MM non poteva funzionare)

Best bid/ask pubblici, campione 2026-10-12 21:19 UTC:

| Simbolo | Bybit spot | Bitvavo |
|---|---|---|
| BTC | 0.012 bps | 3.0 bps |
| SOL | 0.92 bps | 4.9 bps |
| DOGE | 1.18 bps | 19.3 bps |
| ADA | 8.25 bps | 10.7 bps |

Fee maker **Bybit spot = 10 bps**: lo spread e' sotto la fee -> nessun margine.
Le uniche nicchie con margine **lordo** positivo sono Bybit perp su simboli illiquidi
(maker 2 bps vs ADA 8 bps) e Bitvavo (maker 5 bps vs DOGE 19 bps), e il modello
mostra che l'adverse selection le mangia.

## Conclusione

- Order-flow direzionale: **chiuso** (85-350x sotto i costi, 30M tick).
- Market making: **chiuso** (perdita sistematica, t fino a -94, 48k fill).
- Resta la misura continua dello spread (cron ogni 5') per documentare, e la
  ricerca **on-chain / sentiment** su un'altra classe di dato (in corso).

Strumenti: `scripts/scarica_storia_bybit.py`, `scripts/scarica_tick_bybit.sh`,
`scripts/analisi_orderflow.py`, `scripts/simula_mm.py`, `scripts/campiona_spread.py`.
