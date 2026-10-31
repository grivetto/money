# E15 — «carry funding a soglia su universo perp OKX» (pre-registrazione)

**Data:** 2026-10-31 · **Autore:** Artù · **Stato:** PRE-REGISTRATA (regola, universo, soglie e finestre congelati PRIMA dei numeri)

## Come nasce (dichiarato)

Dalla chiusura di E14 (selezione dinamica) per **DATA_BLOCKED**: il preflight di Morgana
(REQ-NUV-20261030-009, handoff MANIFEST 1568/1568 OK) ha misurato che `/api/v5/public/funding-rate-history`
conserva **~95,3 giorni** (doc OKX: «up to three months»; cut 2026-07-27T16:00Z identico su BTC/ETH/DOGE;
**0/517** perp con ≥12 mesi). Con 95 giorni non si misura la persistenza del ranking (2-3 ribilanciamenti),
quindi la selezione *dinamica per ranking storico* è chiusa. Questa lane cambia la domanda:
**una regola a soglia sul funding corrente (ex-ante, nessun ranking previsionale) è una rendita netta
dopo costi, sul capitale vincolato?** È la priorità 2 della REGOLA_SISTEMA (funding carry), e i dati
esistono: 517 perp, 192.071 epoche, candele 1D spot+perp con 12 mesi dove le serie esistono.

**Limite dichiarato in chiaro:** la finestra di misura è di ~95 giorni (un solo trimestre, un solo regime).
Nessuna annualizzazione del risultato: si riporta la media giornaliera netta e il rendimento sul capitale
vincolato nella finestra. Il verdetto è sulla finestra, non «sull'anno».

## Ipotesi (congelata)

Un portafoglio **delta-neutro** (long spot + short perp, 1x isolata, stesso nozionale) che a ogni giorno UTC
tiene solo le coppie il cui **funding annualizzato corrente** supera una soglia, incassa il funding netto
dopo fee e ribilanciamenti, e batte la baseline (Simple Earn ~3%/anno) **sul capitale totale vincolato**
(spot + margine perp), non sul nozionale.

## Dati (congelati)

- **Funding**: handoff REQ-NUV-20261030-009, `dati/funding_daily.json` — per simbolo e giorno UTC:
  `sum_rate` (somma dei rate delle epoche del giorno), `n_epochs`, `mean_rate`. 517 perp USDT-SWAP,
  192.071 epoche, 0 duplicati, 12 simboli con gap di cadenza 2-4x (nessun buco multi-giorno).
- **Prezzi**: candele 1D spot+perp dello stesso handoff; universo ridotto ai perp **con coppia spot**
  (297 perp senza spot = stock-token, esclusi) e con **≥90 giorni** di storia sia spot che perp.
- **Fee reali** (doc OKX verificata nel preflight): spot 8bp maker / 10bp taker; perp 2bp maker / 5bp taker.
  **Costo di switch assunto: 30bp round-trip** (conservativo: 20bp spot RT + 10bp perp RT), stress ×2 = 60bp.
- **Funding incassato**: `sum_rate` del giorno × nozionale della coppia (segno: positivo incassato dallo short).

## Regola (congelata, zero gradi di libertà)

- **Segnale** (osservabile a fine giorno t, eseguito all'apertura del giorno t+1):
  `FA_t = mean_rate(t) × epoche_anno(t) × 100` (funding annualizzato, %), dove `epoche_anno = n_epochs(t) × 365`.
- **Ingresso**: coppia ammessa se `FA_t >= 10.0%` (soglia di ingresso).
- **Uscita**: coppia chiusa se `FA_t < 5.0%` (isteresi) oppure funding negativo per 2 giorni consecutivi.
- **Cap di concentrazione**: massimo **5 coppie**; se più candidate, si tengono le 5 con `FA_t` più alto
  (selezione corrente, non ranking storico — nessuna previsione).
- **Pesi**: uguali; nozionale per coppia = capitale_vincolato_totale / (2 × 5) (spot + margine 1x).
- **Esecuzione**: prezzi di apertura del giorno t+1 (candela 1D); funding del giorno t+1 incassato se in posizione.
- **Capitale di riferimento**: 1.000 EUR; capitale **vincolato** per coppia = 2 × nozionale (spot + margine perp 1x).
- **Nessun look-ahead**: `FA_t` usa solo epoche chiuse del giorno t; l'esecuzione è a t+1.

## Finestre (congelate)

- Dataset effettivo: 2026-07-27T16:00Z → 2026-10-30 (95,3 giorni).
- **TRAIN**: primi 60% dei giorni con dati validi (≈57 giorni).
- **OOS**: ultimi 40% (≈38 giorni).
- Nessuna ottimizzazione delle soglie: 10%/5% sono congelate qui, prima di ogni numero.

## Criteri di promozione (tutti obbligatori)

- **T1 — OOS**: media giornaliera netta > 0 con **t ≥ 2,0** e n ≥ 30 giorni; CI90 bootstrap (seme fisso).
- **T2 — costi ×2**: con 60bp RT la media OOS resta > 0.
- **T3 — TRAIN coerente**: media TRAIN > 0 con t ≥ 1,5.
- **T4 — baseline**: rendimento OOS sul capitale vincolato > Simple Earn 3%/anno equivalente finestra.
- **DSR ≥ 0,95** (N = 2: soglia 10% e cap 5 coppie — due sole configurazioni dichiarate).
- **Concentrazione**: il risultato non deve dipendere da una singola coppia: togliendo la coppia
  con il contributo maggiore, la media OOS resta > 0.

## Retrocessione e kill (dalla REGOLA_SISTEMA, Hermes 3)

- Funding 7g netto annualizzato < 0 → STOP; DD dal picco > 10% → chiusura; riconciliazione non quadra
  2 run consecutivi → freeze + review Artù; leg mismatch > 1% per > 24h → riallineamento/chiusura.

## Se fallisce

Famiglia «funding carry» chiusa **in questa forma**; si passa alla priorità 3 della REGOLA_SISTEMA
(arbitraggio tra venue, con preflight dati dedicato). Nessuna variante delle soglie.

## Implementazione

- Engine: Merlino (Hermes 2), `scripts/e15_carry_soglia.py`, stdlib + `money.statistica`,
  test anti-look-ahead PRIMA dei numeri; dati congelati con hash; report JSON+TXT in `prove/e15_carry_soglia/`.
- Misura ufficiale: Artù dal repo canonico, riesecuzione indipendente e confronto bit-a-bit con lo smoke.
- Timebox: spec+dati ora; engine entro 48h; verdetto entro 72h.

---

## Obiettivo (verificabile)

Verificare se la regola a soglia congelata (ingresso `FA>=10%`, uscita `FA<5%`, cap 5 coppie) produce,
sull'OOS di ~38 giorni: **media giornaliera netta > 0 con t >= 2,0**, rendimento sul capitale vincolato
**> baseline Simple Earn 3%/anno** equivalente finestra, e **stabilità** (contributo della coppia top non
determinante). Esito binario: PASS (tutti i criteri) / FAIL (almeno uno).

## Input / Output

- **Input**: `dati/funding_daily.json` (517 perp: `sum_rate`, `n_epochs`, `mean_rate`), candele 1D spot+perp
  dello stesso handoff, fee 8/10bp spot e 2/5bp perp (doc OKX), soglie 10%/5%, cap 5, capitale 1.000 EUR.
- **Output**: `prove/e15_carry_soglia/e15_carry_soglia.json` con, per finestra (TRAIN/OOS): n giorni,
  media giornaliera netta, t, CI90 bootstrap, rendimento su capitale vincolato, baseline Earn, maxDD,
  numero di switch, contributo per coppia, esiti T1–T4 + DSR; e un `.txt` leggibile con la tabella.
  **Exit code**: 0 misura eseguita; 2 input non validi (fail-closed, nessun numero).

## Test falsificabile

`tests/ricerca/test_e15_antilookahead.py` (4 test, PRIMA dei numeri): (a) il segnale del giorno t non usa
epoche di t+1 (mutare un rate futuro non cambia la posizione di t); (b) il capitale vincolato è 2× il
nozionale (spot + margine 1x); (c) un funding negativo riduce il PnL (non viene incassato come positivo);
(d) input vuoto → exit 2. I test devono fallire su un motore che ignora la soglia o che usa il giorno t+1.

## Criteri di accettazione

- [ ] spec congelata e committata PRIMA dei numeri; [ ] motore deterministico (stdlib + `money.statistica`);
- [ ] 4/4 test verdi PRIMA dei numeri; [ ] smoke di Merlino == misura ufficiale di Artù bit-a-bit;
- [ ] report JSON+TXT con tutti i campi; [ ] verdetto PASS/FAIL con la motivazione numerica;
- [ ] archivio in `prove/REGISTRO_ESPERIMENTI.md` e `coda_catena/CONCLUSE.md`.

## Fuori scope (esplicito)

Funding oltre 95 giorni (non disponibile gratis); selezione per ranking storico (E14, chiusa);
leva > 1x; venue diverse da OKX; trasferimenti tra venue; perp senza coppia spot (stock-token);
modifica delle soglie dopo aver visto l'OOS; annualizzazione del risultato su 95 giorni.

## Verifica (riproducibile)

```bash
cd ~/money
.venv/bin/python -m pytest tests/ricerca/ -q -k e15          # 4/4
.venv/bin/python scripts/e15_carry_soglia.py \
  --dati-dir ~/hermes_bridge/nuvola/handoff/REQ-NUV-20261030-009/dati \
  --out-prove prove/e15_carry_soglia
sha256sum prove/e15_carry_soglia/e15_carry_soglia.json        # == hash dello smoke di Merlino
```

**Repo/commit di riferimento:** `github.com/grivetto/money`, spec committata in `main` prima dei numeri
(SHA riportato nella voce di registro).
