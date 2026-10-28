# E9 — «funding-spread cross-venue carry» (pre-registrazione)

**Data:** 2026-10-29 · **Autore:** Artù (ipotesi: Morgana, REQ-NUV-20261028-003 RANK 1) · **Stato:** PRE-REGISTRATA (regola congelata PRIMA dei numeri)

## Come nasce (dichiarato)

Prima missione di ricerca di Morgana (28/10), RANK 1: monetizzare lo SPREAD di funding tra venue sullo
stesso simbolo con posizioni opposte market-neutral (long dove il funding è più basso/negativo, short
dove è più alto). Non prevede il prezzo: incassa la differenza di tariffa tra venue.
**Dati già in casa** (consegna Morgana 22/10, `hermes_bridge/nuvola/handoff/REQ-NUV-20261022-002/`):
Bybit 12 mesi ×5 simboli; OKX solo 94 giorni (retention pubblica ≈3 mesi, verificato); diff annualizzata
su finestra comune Bybit↔OKX: DOT +251,8 bp · ADA −107,2 · LTC −230,1 · AVAX +13,3 · DOGE −258,9.
Non è E7 (funding direzionale, chiusa) né P21 (carry basket, chiusa): qui si sfrutta il DIFF tra venue.

## Ipotesi (congelata)

Esistono simboli in cui la differenza di funding tra due venue è persistente e di segno stabile per
mesi; su quei simboli una posizione opposta sulle due venue produce un flusso netto positivo, dopo
costi, senza esposizione direzionale.

## Regola operativa (zero gradi di libertà)

- Universo: DOT, ADA, LTC, AVAX, DOGE (già misurati). Nessuna aggiunta senza nuova pre-registrazione.
- Set principale: **Bybit ↔ Binance**, 12 mesi (2025-10 → 2026-10, funding 8h, endpoint pubblici).
  Set di conferma: **Bybit ↔ OKX**, finestra comune (94 giorni).
- Apertura (per simbolo, per coppia di venue): se |diff| = |funding_A − funding_B| ≥ 0,0010%/epoca
  (≈1,1%/anno) in media rolling su 7 epoche → gambe opposte: long sulla venue col funding minore,
  short sull'altra, stesso nozionale, leva 1× isolated.
- Chiusura: se |diff| < 0,0002%/epoca per 3 epoche consecutive, OPPURE segno invertito per 2 epoche
  consecutive (uscita immediata).
- P&L per epoca = (funding incassato netto) − 0; costi solo su apertura/chiusura: perp taker 5bp/lato
  × 2 gambe = **20bp RT** sul nozionale; stress ×2 = 40bp + slippage 1bp/lato.
- Anti-look-ahead: la decisione all'epoca t usa solo funding con timestamp ≤ t−1.
- Sizing dichiarato: nozionale per simbolo = capitale_allocato/5; capitale allocato = 25% dell'equity
  del comparto trading (coerente con la disciplina carry esistente). Il sizing NON si ottimizza.

## Campioni

| Set | Fonte | Ruolo |
| :--- | :--- | :--- |
| TRAIN | Bybit 1h? no — Bybit funding 8h, primi 8 mesi (2025-10→2026-05) | calibrazione soglie (fissate sopra) |
| OOS-1 | Bybit funding 8h, ultimi 4 mesi (2026-06→2026-10) | tenuta temporale |
| OOS-2 | Binance funding 8h, 12 mesi, stessa finestra Bybit | cross-venue (mai misurato prima) |
| CONFERMA | OKX funding 8h, 94 giorni comuni | terza venue |

## Criteri (4/4 + DSR)

- T1 OOS-1+OOS-2: media netta/epoca > 0, t ≥ 2,0, ≥ 200 epoche con posizione aperta
- T2 costi ×2 (40bp RT + slippage): media > 0
- T3 ≥ 3 simboli su 5 con media netta positiva
- T4 persistenza del segno: sul TRAIN, per i simboli con |diff| medio ≥ soglia, il segno del diff
  resta coerente per ≥ 70% dei mesi (criterio dichiarato prima dei numeri)
- DSR ≥ 0,95 con N = 3 (look della famiglia funding: P21, E7, E9)

## Obiettivo

Una rendita market-neutral misurabile in €/mese per € allocato, senza previsione di prezzo: se T1-T4
passano, il comparto carry si estende dal mono-venue al cross-venue.

## Contratto di verifica

- **Repo**: grivetto/money, nuovo motore `scripts/e9_funding_spread.py` (base 64d5f7db, 29/10/2026);
  artefatti in `prove/e9_funding_spread.{txt,json}`.
- **Input**: funding 8h Bybit/Binance/OKX per i 5 simboli (Bybit+OKX già in
  `hermes_bridge/nuvola/handoff/REQ-NUV-20261022-002/`; Binance da scaricare, endpoint pubblico,
  ~6 chiamate/simbolo — fattibilità verificata da Morgana il 22/10 su DOGE).
- **Output**: per simbolo e aggregato — epoche aperte, media netta/epoca, t-stat, CI90, media a costi
  ×2, persistenza del segno per mese, DSR.
- **Criteri di accettazione** (checklist):
  - [ ] T1: media > 0, t ≥ 2,0, ≥ 200 epoche
  - [ ] T2: media > 0 a costi ×2 + slippage
  - [ ] T3: ≥ 3/5 simboli positivi
  - [ ] T4: persistenza segno ≥ 70% mesi (TRAIN)
  - [ ] DSR ≥ 0,95 (N=3)
- **Test falsificabile**: test anti-look-ahead — la decisione all'epoca t usa solo funding ≤ t−1;
  il test atteso fallisce se si usa l'epoca t stessa (stesso contratto E5/E6/E8, `tests/ricerca/`).
- **Fuori scope**: CEX-DEX / Hyperliquid (lane separata E9b, se questa passa o chiude con dati);
  funding direzionale (E7); carry basket (P21); nessun ordine reale; nessuna ottimizzazione del sizing.
- **Procedura di verifica**:
  ```bash
  cd ~/money && .venv/bin/python scripts/e9_funding_spread.py && \
  .venv/bin/python -m pytest tests/ricerca/ -q -k "e9"
  ```

## Se passa

Canary 14 giorni a taglia minima con riconciliazione esatta (come C1), sizing 0,25% rischio/trade,
e solo dopo go esplicito dell'owner. Le gambe opposte su due venue richiedono due conti: la fattibilità
operativa (secondo conto, whitelist, trasferimenti) è un vincolo da verificare PRIMA del canary.

## Se fallisce

Filone «funding cross-venue» chiuso: resta in produzione solo il carry mono-venue (DOT/DOGE), e la
ricerca passa alle lane on-chain netflows (RANK 2 Morgana) e listing event-driven (RANK 3).
