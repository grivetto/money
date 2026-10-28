# E8 — «momentum estremo sui major liquidi» — hold-out Bitvavo (pre-registrazione)

**Data:** 2026-10-28 · **Autore:** Artù · **Stato:** PRE-REGISTRATA + PRESA_DA Artù (universo e finestra congelati PRIMA dei numeri)

## Come nasce (dichiarato)

Il verdetto E6 (21/10) ha bocciato la famiglia ma ha lasciato UNA osservazione post-hoc aperta:
sull'hold-out Binance (17 crypto top-volume) il long su estremi z≥+3 dà +2,414%/trade (t 5,31, n 761)
e il paniere OOS-3 +0,950% (t 3,34); su Bybit 57 simboli misti lo stesso segnale perde (−0,484%, t −3,97)
e su OKX 19 simboli è al limite (t 1,64). Stesso periodo, stessa regola: la differenza è l'UNIVERSO
(major liquidi vs small-cap), non il regime. Il registro E6 esige, per testarla: un quarto exchange
mai usato dalla famiglia come hold-out + pre-registrazione con universo fissato PRIMA dei numeri.
**Bitvavo**: venue già nel perimetro Denaro, MAI usata in alcuna misura della famiglia → hold-out pulito.
Preflight dati eseguito 28/10 PRIMA dei numeri: API pubblica (`api.bitvavo.com/v2`) risponde senza
chiave; storia 1h disponibile ≥ 2023-01 (finestra OOS coperta); volume misurato da `/ticker/24h`.

## Ipotesi (congelata)

Il momentum estremo (specchio esatto E5/E6) ha edge positivo SOLO sui major liquidi. Se T1 fallisce
anche qui, la famiglia «estremi di prezzo» si chiude DEFINITIVAMENTE (E2, E4, E5, E6, E8).

## Regola operativa

Identica a E6, zero gradi di libertà:

- z = (close − SMA168) / stdev168 su barre 1h
- long se z ≥ +3,0 · short se z ≤ −3,0
- cooldown 24 ore per simbolo; ingresso all'apertura della barra i+1
- uscita: prima barra con |z| ≤ 0,5 **oppure** 72 ore
- stop 3,0 × ATR(14) intrabarra, distanza massima 50%
- costi: base taker 0,25%/lato (tariffario pubblico Bitvavo, tier base) ⇒ **RT 0,50%**;
  stress ×2 = 1,00% RT; scenario maker 0,30% RT (solo descrittivo)

## Campioni

Un solo set, mai toccato: **OOS Bitvavo 1h, 7 coppie, 2024-06-01 → 2026-10-28**.

**Universo congelato il 28/10/2026** con criterio dichiarato: coppie EUR con `volumeQuote` ≥ 5.000.000 EUR
su `/ticker/24h` del 28/10/2026, escluse le stable. Risultato (volume misurato):

| Coppia | volume 24h (EUR) |
| :--- | ---: |
| BTC-EUR | 24.551.401 |
| XRP-EUR | 19.306.211 |
| ETH-EUR | 18.034.947 |
| SOL-EUR | 9.396.296 |
| HYPE-EUR | 9.220.602 |
| ADA-EUR | 7.637.254 |
| PEPE-EUR | 6.256.309 |

Idoneità preflight (prima dei numeri, criterio fisso): ≥ 12 mesi di candele 1h al 28/10/2026;
le coppie non idonee si escludono SENZA sostituzione. TRAIN non ri-misurato: resta quello di E6
(Bybit 2021-12→2024-05); nessuna ri-ottimizzazione.

## Criteri (3/3 + DSR)

- T1 **Bitvavo OOS**: media/trade > 0, t ≥ 2,0, n ≥ 30
- T2 costi ×2 (1,00% RT): media > 0
- T3 coerenza per lato: il **long** (driver dell'ipotesi) deve avere da solo media > 0 e t ≥ 2,0;
  lo short è descrittivo (negativo su tutti i set in E6)
- DSR ≥ 0,95 con N = 5 (look della famiglia: E5 ×2, E6 ×2, E8 ×1), var SR stimata sui look storici

## Obiettivo

Falsificare definitivamente (o promuovere) l'ultima ipotesi viva della famiglia «estremi di prezzo»:
edge positivo del momentum estremo sui major liquidi, misurato su un hold-out mai usato (Bitvavo EUR).
Output = verdetto T1-T3 + DSR, nessuna decisione di capitale.

## Contratto di verifica

- **Repo**: grivetto/money, motore da riusare `scripts/e6_momentum_estremo.py` (base 5c1b6bac, 28/10/2026) con nuovo loader dati Bitvavo; artefatti in `prove/e8_bitvavo.{txt,json}`.
- **Input**: candele 1h Bitvavo per le 7 coppie congelate, 2024-06-01 → 2026-10-28, scaricate da `api.bitvavo.com/v2/<pair>/candles` (pubbliche, senza chiave).
- **Output**: per coppia e aggregato — n trade, media/trade netta (RT 0,50%), t-stat, CI90 bootstrap, media a costi ×2, split long/short, DSR.
- **Criteri di accettazione** (checklist):
  - [ ] T1: media netta > 0 con t ≥ 2,0 e n ≥ 30 sull'OOS Bitvavo
  - [ ] T2: media > 0 a costi ×2 (1,00% RT)
  - [ ] T3: il long da solo ha media > 0 e t ≥ 2,0
  - [ ] DSR ≥ 0,95 con N = 5
- **Test falsificabile**: test anti-look-ahead obbligatorio PRIMA dei numeri — il segnale della barra i deve dipendere solo da candele chiuse ≤ i; il test atteso fallisce se la barra di segnale usa il close della barra stessa (stesso contratto di E5/E6: `tests/ricerca/`).
- **Fuori scope**: nessuna ri-ottimizzazione della regola; nessuna estensione dell'universo post-hoc; nessun ordine reale; funding/fee Bitvavo exact non misurati sul conto (scenario tariffario pubblico, limite dichiarato).
- **Procedura di verifica**:
  ```bash
  cd ~/money && .venv/bin/python scripts/e8_momentum_bitvavo.py && \
  .venv/bin/python -m pytest tests/ricerca/ -q -k "e8"
  ```

## Se passa

Non è un'autorizzazione: canary 14 giorni a taglia minima con riconciliazione esatta (come C1),
sizing 0,25% di rischio per trade (mandato), e solo dopo go esplicito dell'owner.

## Se fallisce

Famiglia «estremi di prezzo» CHIUSA DEFINITIVAMENTE: nessuna variante ulteriore. La ricerca
direzionale su OHLCV si riorienta sulla prossima lane pre-registrata: baseline TSMOM 12M/1M
long-only BTC/ETH (raccomandazione n.4 del report A0-Win 21/10).

