# 18 — Programma di ricerca quant: protocollo, audit dati, coda

Data: 2026-10-01 · hermes · stato: ATTIVO
Origine: batch di brief "ricercatore quant scettico" (proprietario, 01/10) — questo doc
trasforma quella richiesta in protocollo operativo del progetto.

## 0. La regola unica
Niente è un edge perché "sta in letteratura" o perché il backtest è bello. La letteratura è
il **prior**; il giudice è il **cancello** (`src/money/cancello.py`, 8 criteri con soglie
dichiarate prima): n≥30 · IC90 bootstrap > 0 · t>1,65 · PF>1,20 · DD≤25% · exp ≥ 3× pedaggio ·
EUR/anno ≥ soglia · indipendenza dai blocchi. Ogni misura nasce da una **voce nel
REGISTRO_ESPERIMENTI prima del primo numero**. Chi non passa si archivia; con n<30 il
verdetto è "insufficiente", mai "promosso".

## 1. Audit dati — cosa possiamo testare DAVVERO (probe 01/10/2026)

| Dato | Stato | Fonte / limite |
|---|---|---|
| OHLCV daily, majors crypto | DISPONIBILE | 2020-10-01→oggi, paginazione `dati.py`; finestra standard "USDT-lungo", confine addestramento 2024-06-01 |
| OHLCV intraday (1m–4h) | PARZIALE | finestre recenti via API; copertura storica da verificare PRIMA di ogni spec intraday |
| Funding rate EEA | DISPONIBILE | archivio locale `data/funding_xperp.jsonl` (dal 03/07, raccolta ogni 4h); API pubblica ~33gg |
| Open interest | DA VERIFICARE | endpoint pubblici OKX; copertura EEA da testare |
| Spot / Swap tradabili EEA | DISPONIBILE | 1.148 spot · 495 swap (probe). Short solo via perp |
| OPZIONI | NON DISPONIBILE | **OKX EEA: 0 strumenti**. → ogni studio IV vs RV è impossibile sul nostro venue |
| Tick / order book | NESSUNO STORICO | registrazione forward possibile (WS pubblico); latenza retail → HFT escluso per costruzione |
| News / transcript / earnings | NON DISPONIBILE | e comunque equity (PEAD/transcript fuori venue) |
| Azioni / equity | NON DISPONIBILE | nessun dataset, nessun conto titoli; richiederebbe acquisto dati point-in-time |
| Alternative data | NON DISPONIBILE | on-chain tecnicamente accessibile (API pubbliche) ma nessuna pipeline |
| ETF flows (BTC/ETH) | DA COSTRUIRE | dati pubblici esterni, latenza giornaliera |
| Calendario macro | NON USATO | nessun feed |

## 2. Protocollo "referee ostile" — come blocchiamo ogni classe di bias
1. **look-ahead** → segnali su barra chiusa, esecuzione barra+1; `verifica_provenienza.py`; test anti-leakage nei misura_*
2. **survivorship** → universo deciso dalla copertura dati ("la verifica di copertura decide, non noi" — metodo P1)
3. **data snooping** → voce registro prima; griglia minima dichiarata; contatore varianti cumulativo
4. **p-hacking** → criteri nel codice; verdetto riproducibile (seme bootstrap fisso)
5. **multiple testing** → varianti dichiarate; upgrade futuro: deflated Sharpe quando varianti > 10
6. **overfitting parametri** → parametri da letteratura/default; selezione solo su addestramento con n≥30; verifica una volta sola
7. **leakage train/test** → confine dichiarato; nessuna ri-selezione dopo la verifica
8. **costi/slippage** → `costi.py`: spot EEA 0,550%/0,700% senza X-Perp → 0,180%/0,200% con X-Perp; perp 0,020%/0,050% + funding (~0,4× fee); ogni spec dichiara la tariffa assunta
9. **liquidità/impact** → filtri dichiarati; a <1k€ l'impact è ~0 ma `min_notional` fissa il taglio minimo
10. **leva nascosta** → nei test leva 1×; ogni leva è parte dell'ipotesi, dichiarata
11. **gap risk** → esecuzione ad apertura barra+1 (il gap è un costo dichiarato, mai "allo stop")
12. **regime dependence** → criterio 8 (via blocco migliore); risultati per sottoperiodi dichiarati
13. **crowding** → sezione obbligatoria nella spec: "chi è dall'altra parte?"
14. **decadimento edge** → assunto il post-publication decay (McLean-Pontiff); edge pubblicato = dimezzato
15. **impossibilità operativa** → preflight (saldi, min_notional, permessi, simbolo) prima di ogni promozione
16. **selezione retrospettiva** → mai promozioni a posteriori; finestre/soglie dichiarate prima

## 3. Template di spec (obbligatorio, i 12 punti)
1. ipotesi nulla / alternativa · 2. definizione precisa del segnale · 3. universo e
campionamento · 4. dati con timestamp e provenienza · 5. periodi addestramento/verifica
(confine dichiarato) · 6. benchmark obbligatori (Donchian, BTC buy&hold, cash/carry) ·
7. metriche (rendimento netto, expectancy, PF, DD serializzato e di portafoglio, t/IC
bootstrap, turnover, hit rate, skew, tail) · 8. costi realistici (tabella `costi.py`) ·
9. significatività (HAC, bootstrap) · 10. controlli overfitting (griglia minima, n≥30) ·
11. criteri di STOP (DDport>25% o exp<3×pedaggio o t/IC nulli → archiviazione) ·
12. condizioni paper phase (≥30 operazioni forward in officina → live size minima).

## 4. Triage dei brief ricevuti (verdetto per classe)
- **GIÀ FATTO/ARCHIVIATO** (con artefatti in `prove/`): mean-reversion (H), reversal (O),
  weekend (K), capitulation (M: exp −2,97%), breakout (I, N), momentum puro (L), trend
  P1–P6/P11 (DD portafoglio 37,8–98,9%: mai sotto 25%).
- **IN CORSO**: P10 momentum cross-section (dsh) · M1 release · E1 economia · C1 canary carry.
- **TESTABILE ORA (candidabile a spec)**: continuzione post-estremo (MAI testata con
  z/ATR/percentile) · cointegrazione pairs (famiglia ASSENTE dal registro) · funding
  regime/timing (collegata alla tesi viva) · dispersion/vol regime come filtro di sizing ·
  capitulation 2.0 (breadth/funding su vendite estreme).
- **NON TESTABILE OGGI** (detto esplicitamente): IV vs RV (no opzioni EEA) · tick/HFT (no
  storico, no infra) · cross-exchange arb (un solo venue, capitale frammentato) · index
  rebalancing / PEAD / transcript NLP / alt-data / slow-info equity (fuori venue, no dati) ·
  retail options flow (no opzioni). Servono acquisto dati e/o nuovi venue: decisione del
  proprietario, non della ricerca.

## 5. Le 10 ipotesi candidate per il NOSTRO banco (mappa operativa)
| # | Ipotesi | Dati | Stato | Prior |
|---|---|---|---|---|
| 1 | Continuazione post-estremo daily (z/ATR/percentile + filtri vol/volume) | ok | NUOVA | medio |
| 2 | Reversal post-estremo (gap vs intraday, holding 1–20g) | ok | varianti di H/O/M (archiviate) mai testate con z/ATR | basso |
| 3 | Cointegrazione pairs/basket majors (half-life, soglie) | ok (daily) | NUOVA (famiglia assente) | medio-basso |
| 4 | Funding regime & timing (finestre 00/08/16, trending, OI) | funding ok, OI da verificare | NUOVA, su tesi VIVA | medio |
| 5 | Momentum cross-section top-k | ok | IN CORSO (P10/dsh) | medio |
| 6 | Dispersion regime come filtro di sizing | ok | NUOVA | medio |
| 7 | ETF flows → drift BTC | da costruire | RIMANDATA | medio |
| 8 | Order-book imbalance (solo registrazione forward) | da costruire | RIMANDATA (HFT escluso) | n/a |
| 9 | Capitulation 2.0 (breadth/funding/corr) | parziali | variante di M | basso |
| 10 | Carry enhancement (compensazione funding tra periodi) | ok | NUOVA | medio |

## 6. Coda operativa proposta
1. **P10** (dsh, in corso) — lane nuova più matura.
2. **Funding regime/timing** — l'unica che può migliorare la tesi VIVA (carry).
3. **Cointegrazione pairs** — lane nuova e scorrelata; kill rapido (half-life + costi + rottura).
4. **Continuazione post-estremo** — rapida, completa la mappa degli estremi.
5. **Capability future** (registratore L2, ETF flows) solo quando 1–4 hanno verdetti.

## 7. Governance
- Ogni spec nasce con voce nel REGISTRO_ESPERIMENTI; verdetti nel registro; artefatti in `prove/`.
- Le soglie del cancello vivono nel codice: cambiarle richiede un commit con motivo — mai a mano nel verdetto.
