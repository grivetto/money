# P26 — Cointegrazione v2: universo esteso + statistica ROLLING (lane pairs)

STATO: PRE-REGISTRATA 2026-10-18 (Artù) — in attesa di coda libera; implementatore da assegnare al via (primo libero o Merlino). Riapre la lane P13 (archiviata 01/10) con le varianti esplicitamente ammesse dal suo verdetto, su direttiva dell'owner (18/10: pilastro «arbitraggio statistico — test di cointegrazione costanti»).
Repo: `grivetto/money` · commit di registrazione: `3e8e8c19` (file di questa voce: `coda_catena/P26_cointegrazione_rolling.md`).

## Obiettivo (verificabile)
Verificare se lo spread di coppie «cointegrate a tratti» su un universo ESTESO è sfruttabile con statistica ROLLING (beta e half-life ricalcolati su finestre mobili), a costi reali. Esiti ammessi: **candidata-su-evidenza** oppure **archiviazione definitiva della lane pairs** (zero revival). Output: per coppia eleggibile — n. episodi, expectancy netta, DD, rotture; verdetto del cancello.

## Contesto
- P13 (10 major, EG su addestramento unico, z 60g) → archiviata: nessuna coppia passa (top DOGE/LINK t=−3.77 vs soglia 3,8; half-life 44–108g vs [3,30]; beta instabili).
- Il verdetto P13 ammetteva esplicitamente tre varianti: universo più largo; finestra z più lunga; beta/mean-reversion rolling. Questa voce le combina.
- Direttiva owner 18/10 (pilastro «arbitraggio statistico»). **Ultimo giro sulla lane**: se anche la v2 fallisce, la lane si chiude senza ulteriori varianti.
- Freeze famiglie: riguarda le famiglie predittive direzionali su OHLCV (chiuse per evidenza S1–S4). Questa è arbitraggio relativo (market-neutral), famiglia distinta e già ammessa storicamente (P13). Dichiarato per igiene.

## Ipotesi
- H1: su universo esteso (top 30 perp USDT OKX) con statistiche ROLLING esistono coppie la cui relazione è «cointegrata a tratti» con persistenza misurabile: finestra «viva» (|t_rho| ≥ 3,5 E half-life ∈ [5, 90]g) in ≥ 60% delle finestre dell'addestramento E nell'ultima finestra.
- H2: se eleggibili, il trading dello spread (z 60g) in verifica OOS produce expectancy netta ≥ 3× pedaggio con DDport ≤ 25%.

## Meccanica (dichiarata PRIMA dei numeri)
- Dati: USDT-lungo (dal 2019-01-01; fee identiche a livello conto). Addestramento [2020-01-01, 2024-06-01); verifica [2024-06-01, oggi].
- Universo: top 30 perp USDT OKX per volume medio dell'addestramento (survivorship dichiarato: universo = strumenti listati oggi).
- Finestre rolling: W ∈ {120g, 180g} (griglia: 2 valori), passo 5g. In ogni finestra: EG due passi (OLS log-log; ADF sui residui) → t_rho; half-life = −ln2/ln(1+rho).
- Finestra «viva»: |t_rho| ≥ 3,5 E half-life ∈ [5, 90]g.
- Eleggibilità: viva in ≥ 60% delle finestre dell'addestramento E viva nell'ultima finestra. Cap operativo: **max 3 coppie** (ordine: % finestre vive decrescente).
- Operatività: z(t) = (spread(t) − media_60g(t)) / sd_60g(t) su osservazioni ≤ t; spread = log(P_a) − beta·log(P_b) con beta dell'ultima finestra viva. Ingresso |z| ≥ 2 allo close t → esecuzione all'apertura t+1. Uscita |z| ≤ 0,5 · stop |z| ≥ 4 · stop-di-relazione (coppia non più viva al ricalcolo) · fine serie. Una posizione per coppia.
- Capitale: 0,25× equity per coppia, due gambe perp a margine isolato 1× (NIENTE leva).
- Griglia: {W: 120, 180} × {z: 60g} — NIENT'ALTRO. Varianti ulteriori non ammesse (la lane chiude comunque a questo giro).

## Costi
- 0,30% per ciclo completo dichiarato (0,20% fee due gambe + 0,10% slippage); stress 0,45%. Funding differenziale delle due gambe incluso e riportato (mai nascosto).

## Verifica OOS e criteri (cancello)
- Verifica [2024-06-01, oggi], UNA volta, configurazione congelata dall'addestramento.
- Successo: DDport ≤ 25% E expectancy netta (campione eseguito) ≥ 3× pedaggio. Secondarie sempre riportate: t-stat, n (se < 30 → «insufficiente», mai «promossa»), PF > 1,20, criterio 8, due metà.
- Rotture: se > 20% degli episodi sfonda z ≥ 4 senza rientrare entro 30g → coppia esclusa a prescindere dal P&L.

## Criteri di stop / esiti ammessi
- Nessuna coppia eleggibile in addestramento → **ARCHIVIATA DEFINITIVAMENTE** (lane pairs chiusa: nessuna variante ulteriore, mai più riaperta senza un fatto nuovo esterno).
- Eleggibili ma verifica negativa → archiviata (numeri nel registro).
- Candidata-su-evidenza → NON live: nuova voce per la promozione (preflight, size minima, autorizzazione owner).
- Esiti ammessi: {candidata-su-evidenza, descrittiva, insufficiente, archiviata}.

## Anti-bias
- Statistiche solo su osservazioni ≤ t; esecuzione t+1; test anti-lookahead in `tests/ricerca/` PRIMA dei numeri.
- Selezione SOLO su addestramento; verifica una volta sola; nessuna soglia ottimizzata.
- Persistenza come correzione strutturale del multiple testing (435 coppie): soglia per-finestra dichiarata (3,5) + severità nella persistenza ≥ 60% + cap 3 coppie.
- Funding differenziale mai nascosto; scenari tariffa sempre riportati; campione corto dichiarato in ogni output.

## Definizioni (autosufficienza per l'implementatore)
- **EG due passi**: OLS di log(P_a) su log(P_b) nella finestra; ADF (Augmented Dickey-Fuller) sui residui; `t_rho` = t-stat del coefficiente autorigressivo rho dell'ADF.
- **half-life** = −ln2 / ln(1 + rho) in giorni (rho dal medesimo ADF).
- **spread(t)** = log(P_a(t)) − beta·log(P_b(t)); beta = pendenza OLS dell'ultima finestra «viva».
- **z(t)** = (spread(t) − media_60g(t)) / sd_60g(t), medie/sd calcolate su osservazioni ≤ t.
- **Finestra «viva»**: |t_rho| ≥ 3,5 E half-life ∈ [5, 90]g.
- **P_a / P_b**: prezzi di chiusura daily dei due strumenti della coppia (quote USDT).

## Vincoli
- Ambiente: implementazione in scratch (omarchy/worker) con venv dedicato; letture dal repo canonico via ssh read-only; NESSUNA scrittura in `~/money` (integra Artù).
- Dati: candele USDT-lungo da `data/` (archivio interno) o ccxt pubblico su `eea.okx.com`; la lista dei 30 perp va dichiarata in output (criterio di selezione + data di estrazione).
- Librerie: pandas, numpy, statsmodels — nessuna dipendenza nuova non dichiarata; niente ML.
- Vietato: ordini reali, chiavi exchange, scritture su exchange, modifiche a C1/carry, qualunque variante oltre la griglia dichiarata.
- Output: solo `prove/P26_pairs_rolling.{txt,json}` + modulo/test/runner/LEGGIMI in handoff.

## Input / Output
- **Input**: candele USDT-lungo (archivio interno/ccxt), lista universo 30 perp, questa spec.
- **Output**: `prove/P26_pairs_rolling.{txt,json}` con screening, episodi, expectancy netta, DD, rotture, verdetto; exit code 0/≠0.

## Contratto di consegna (per l'implementatore)
Implementatore: primo libero (fabbrica/DSH/opencode) o Merlino — assegnato al via. Consegna via handoff (`merlino/handoff/P26/` o `dsh-mc2/handoff/P26/`): `p26_pairs_rolling.py` + `test_p26_pairs_rolling.py` + `misura_p26.py` + artefatti + `LEGGIMI.md` + `MANIFEST.sha256` + `READY` (ultimo).
Criteri di accettazione:
- [ ] test EG su serie sintetiche cointegrate note: **assert** su t_rho e half-life **attesi** (calcolati a mano nel test); senza implementazione i test devono **fallire**
- [ ] test anti-lookahead sulle finestre rolling: le statistiche a t usano solo osservazioni ≤ t (atteso = ricalcolo manuale su marker)
- [ ] test conteggio episodi/rotture su serie sintetica (atteso: valori esatti a mano)
- [ ] screening riproducibile a parità di dati; zero ordini, zero chiavi, zero scritture su exchange
- [ ] `misura_p26.py` end-to-end produce `prove/P26_pairs_rolling.{txt,json}`

## Verifica (riproducibile)
Comando di verifica:
```bash
cd ~/money && .venv/bin/python -m pytest tests/ricerca/ -k p26 -q
.venv/bin/python scripts/misura_p26.py --screening   # fase 1: addestramento
.venv/bin/python scripts/misura_p26.py --verifica    # fase 2: OOS, UNA volta
```

## Fuori scope
- Modifiche a C1/carry in produzione; ordini reali; chiavi; varianti non dichiarate; riapertura della lane se archiviata (decisione vincolante); qualunque scrittura su exchange.

## Riferimenti
P13 (verdetto + varianti ammesse) · `docs/18_programma_ricerca_quant.md` (protocollo) · cancello (`src/money/cancello.py`) · direttiva owner 2026-10-18 · `coda_catena/README.md`.

## Addendum 2026-10-18 (Artù) — finestra di addestramento effettiva (da preflight dati)
PRIMA di qualsiasi numero: il preflight dell'archivio (consegna opencode-omarchy, verificata da Artù; artefatti `prove/p26_preflight_20261018/`) mostra che 59/90 coppie USDT hanno prima barra **2020-10-01** (artefatto di raccolta OKX: confine di paginazione), non 2020-01-01; solo BTC/ETH risalgono al 2019-01-01. Interpretazione ufficiale:
- **Finestra di addestramento effettiva: [2020-10-01, 2024-06-01)** (coerente con la convenzione «USDT-lungo» di P1/P3/P10/P14). La finestra di verifica resta [2024-06-01, ultima barra per coppia].
- **Eleggibilità**: prima barra ≤ 2020-12-08 E copertura ≥95% su [2020-10-01, 2024-06-01) E copertura ≥95% su [2024-06-01, ultima barra]. (90/90 file contigui: 0 buchi interni.)
- **Ranking volume**: volume NOTIONAL medio (v×close, USDT) — il campo `v` è in valuta base, non confrontabile tra simboli.
- **Esito preflight**: 64/90 coppie idonee. Top 30 candidate (per notional, finestra effettiva): BTC, ETH, DOGE, OKB, SOL, DOT, BCH, FIL, LTC, XRP, ETC, AVAX, LINK, ATOM, UNI, TRX, NEAR, THETA, XLM, AAVE, ADA, SUSHI, CRV, ALGO, EGLD, NEO, LRC, KSM, ZIL, YFI — lista completa in `prove/p26_preflight_20261018/p26_candidate_finestra_effettiva.json`.
- Coda dei file: 71 si fermano al 2026-10-06 (batch di raccolta, non delisting; copertura verifica ≥98,7% comunque).
