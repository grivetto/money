# Registro degli esperimenti — append-only

**Regola (dal 2026-09-30, review esterna + audit dsh):** nessuna misura senza voce qui,
**prima del primo numero**. Ogni voce dichiara: id · data · ipotesi e meccanismo · dati ·
griglia dichiarata · **numero di varianti provate** · esito (verbatim del cancello) · stato ·
artefatti · hash di dati+codice (quando disponibile).

Le voci non si modificano: correzioni e nuovi tentativi sono **voci nuove** che le supersedono.
Il *conteggio delle varianti* è la materia prima della correzione per selezione multipla (vedi
`coda_catena/M1_release_validazione.md`): va dichiarato onestamente, anche quando fa comodo
non farlo. Un laboratorio che non conta i tentativi non può stimare la probabilità che il
"vincitore" sia un artefatto del caso.

**Avvertenza sulle voci storiche:** tutto ciò che precede il 2026-09-30 è **ricostruito a
posteriori** dagli artefatti in `prove/` e dalla coda. Dove un campo è ignoto: `n/d` — non è
una scusa per ometterlo nelle voci nuove.

**Contatore varianti dichiarate (cumulativo):** storico `n/d` (ricostruzione parziale);
dal 2026-09-30 in poi: **6** (P2: dichiarate, misurate, archiviate).

---

## Voci storiche (pre-registro, ricostruite)

- **H — RSI mean-reversion** → archiviata. Artefatti: `prove/H_rsi_mean_reversion.*`. Griglia/varianti: n/d.
- **I — Donchian breakout** → archiviata. Con perp: exp +2,47%/anno 180 EUR — sotto le soglie. Artefatti: `prove/I_donchian_breakout.*`. Varianti: n/d.
- **J — Rotazione forza** → **insufficiente** (campione piccolo: mancanza di dati, non merito). Artefatti: `prove/J_rotazione_forza.*`.
- **K — Effetto weekend** → archiviata. Artefatti: `prove/K_effetto_weekend.*`.
- **L — Momentum assoluto 60g** → archiviata (exp netta +2,61%, DD 57% — è la base di P2). Artefatti: `prove/L_momentum_assoluto.*`.
- **M — Capitolazione volume** → archiviata (exp -2,97% con_perp). Artefatti: `prove/M_capitolazione_volume.*`.
- **N — Breakout paniere** → archiviata. Artefatti: `prove/N_breakout_paniere.*`.
- **O — Reversal 2 giorni** → archiviata. Artefatti: `prove/O_reversal_2giorni.*`.
- **trend_lungo** → archiviata (misura principale; dipende dalla cache di alpha-omega-trading: vedi §riproducibilità / P9). Artefatti: `prove/trend_lungo_misura.txt`, `prove/trend_lungo_confronto_evidenza.txt`.
- **griglia_adattiva** → archiviata — **28 prove dichiarate** (misura di soglia, NON una strategia).
- **momento_4h** → esplorativa a 4h; esito n/d. Artefatti: `prove/momento_4h.*`.
- **portafoglio_2026-09-29** → esplorazione del DD di portafoglio (serializzato vs mark-to-market); tutti i rami archiviati. Artefatti: `prove/portafoglio_2026-09-29.*`.

## Voci con spec (`coda_catena/`)

- **P1 — Trend + stop chandelier** (2026-09-27) → archiviata: ipotesi smentita; A/B interno vs Donchian 6/8; exp -0,70% (con perp). Griglia: A/B 2 varianti dichiarate; storico n/d. Artefatti: `prove/P1_trend_atr_stop.*`, `prove/P1_pilota_btceth_2019.*`.
- **P2 — Momentum + vol targeting** (misurata 2026-09-30, dsh+Hermes) → **ARCHIVIATA per costruzione**: nessuna delle 6 configurazioni dichiarate porta il DDport ≤ 25% (controllo 42,8%; vt=0,50/0,60/0,75 → 46,8/47,5/41,7%). Il sizing riduce il DD *serializzato* (47,0% → 37,6% a vt=0,50) ma NON il DD di portafoglio mark-to-market: il DD è una proprietà di portafoglio (concorrenza + correlazione tra simboli), non del singolo trade. Il controllo riproduce il riferimento A/B (check OK). Artefatti: `prove/P2_vol_target.{txt,json}`; misura: `scripts/misura_p2.py`; test del gancio: `tests/ricerca/test_portafoglio_esp_variabile.py`.
- **P3 — Filtro SMA200** (2026-09-29) → archiviata: t 1,58 · DD 45,5% · exp +9,01%/op = 16,4× pedaggio · IC90 [+0,10%, +19,12%]; bocciata SOLO da t e DD. Varianti: A/B 6/8 dichiarate. Artefatti: `prove/P3_trend_filtro_200g.*`.
- **P4 — Funding carry** → parcheggiata: storia funding EEA ≈ 96 giorni, non misurabile; si accumula con P8. Spec: `coda_catena/P4_funding_carry.md`.
- **P5 — Donchian universo esteso** (2026-09-28) → archiviata: 407 coppie scansionate → 61 misurate; l'allargamento diluisce (t 1,44; DD 98,9%; IC90 [−0,28%, +8,93%]). Varianti: 61 misurate (su 407 scan). Artefatti: `prove/P5_universo.json`, `prove/P5_donchian_esteso.*`.
- **P6 — Livello portafoglio** → in coda (spec da materializzare). *Non ancora registrato come misura.*
- **P7 — Economia della soglia** → in coda (spec da materializzare).

## Infrastruttura (non strategie — non consumano gradi di libertà di ricerca)

- **P8 — Raccoglitore funding/basis** → integrato 2026-09-29 (`src/money/raccoglitore_funding.py`, 9 test nella suite). Append-only idempotente, guardia anti-ordini.
- **P9 — Verificatore di provenienza `prove/*`** → integrato 2026-09-30 (`src/money/verifica_provenienza.py`, 10 test). Primo uso previsto: pin dell'hash della cache dichiarata (la cache di `trend_lungo` è su Windows: il manifest va generato lì o la misura rifatta sui dati mc2).

## Registro variazioni

- 2026-09-30 — creato: ricostruzione storica + regola append-only + contatore varianti.
- 2026-09-30 — P9 integrato; verificatore di provenienza disponibile in `src/money/`.
- 2026-09-30 — P2 misurata e archiviata per costruzione (sizing: DD serializzato giù, DD portafoglio invariato/peggiore).
