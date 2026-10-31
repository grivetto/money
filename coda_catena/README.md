# coda_catena/ — la coda di lavoro della catena crea → testa → promuovi/archivia

COME FUNZIONA (regole della catena, 2026-09-27, Hermes direttore d'orchestra)
============================================================================

1. Ogni file `P*.md` e' una SPEC di famiglia: ipotesi, meccanica precisa (entrata, uscita,
   anti-look-ahead), griglia dichiarata, universo e dati.
2. Chi e' libero (Hermes su mc2, DSH/Agent Zero su Windows, eventuali sub-agent) **prende**
   una spec scrivendo in testa `STATO: PRESA_DA <chi> <data>` — una sola volta, primo arriva.
3. Si implementa in `src/money/ricerca/<nome>.py` seguendo le convenzioni dei nodi H-O
   (costi da `money.costi`, Esito del cancello, nessuna eccezione su zero operazioni).
4. Test obbligatori in `tests/ricerca/` PRIMA dei numeri (anti-look-ahead, chiusura di tutte
   le operazioni, costi).
5. Verdetto con `scripts/misura_catena*.py` (stesso protocollo: griglia dichiarata provata
   tutta in addestramento, verifica OOS, `giudica`, scenari tariffa).
6. Artefatti in `prove/<nodo>.{txt,json}`. Se archivia: si archivia, niente "quasi".
7. DSH resta proprietario di docs/ e della narrativa dei verdetti; Hermes di deploy,
   esecuzione e di questa coda. Chi prende una spec aggiorna lo STATO nel file.

DATI LUNGHI (la chiave di volta, verificata 2026-09-27)
=======================================================
Le coppie **USDT** su eea.okx.com arrivano a **gennaio 2019** (le EUR solo a 2023-12).
Per le spec marcate `DATI: USDT-lungo`: universo USDT, INIZIO 2019-01-01, CONFINE
2024-06-01 (addestramento 5,4 anni, verifica 2,3 anni). Fee identiche (a livello conto).
La conferma finale prima della promozione si rifa' SEMPRE sulle EUR (campione corto).

STATO DELLA CODA
================
- P1_trend_atr_stop.md ...... FATTA, ARCHIVIATA (ipotesi chandelier smentita; A/B: Donchian 6/8)
- P2_momentum_vol_target.md . FATTA 30/09 — ARCHIVIATA (sizing: DD serializzato 47,0→37,6% ma DD portafoglio ↛ 42,8→41,7-47,5%: il DD è proprietà di PORTAFOGLIO — prove/P2_vol_target.*)
- P3_trend_filtro_200g.md ... FATTA 29/09 — ARCHIVIATA (integrata da hermes: 6/8 come Donchian; t 1,58; DD 45,5%)
- P4_funding_carry.md ....... PARCHEGGIATA (funding EEA = 96gg di storia, verificato da dsh: niente misura)
- P5_donchian_esteso.md ..... FATTA 28/09 — ARCHIVIATA: l'allargamento non regge (61 coppie; t 1,44; prove/P5_donchian_esteso.*)
- P6_portafoglio.md ......... ARCHIVIATA per costruzione (30/09) — nessuna delle 6 config soddisfa (vedi CONCLUSE.md)

---

## Aggiornamento 2026-10-16 — onda S5 (fronte funding/esecuzione; pre-registrate, lint 7/7)
- P21_carry_basket.md ........ FATTA 17/10 — ARCHIVIATA (misura ufficiale Artù: nessuna config con netto train>0; top-k perde vs DOGE-solo; implementazione DSH-omarchy)
- P22_regime_gate_netto.md ... FATTA 17/10 — ARCHIVIATA (implementazione Merlino; misura ufficiale Artù: ogni trigger delta<=0 su 10/10 a 0,40% e 0,62%; T3 mai avvenuto; timing del carry chiuso, sempre-on)
- P23_pedaggio_esecuzione.md . FATTA 18/10 — CHIUSA (Artù): fee reali = tariffa taker esatta (10/5 bp), riconciliazione MATCH; cicli 15,1–20,8 bp vs C=40 bp → soglie confermate; H2 maker-first non confermato su due run → non si fa. Report `prove/P23_report.md`
- Piano del fronte: `docs/34_fronte_ricerca_2026-10-16.md`

## Aggiornamento 2026-10-17 — P24 (operativa, tesoreria — NON esperimento)
- P24_dormienti_earn.md ...... INTEGRATA (Artù 18/10) — harness `scripts/earn_move.py` consegnato da Merlino (REQ-MERL-20261017-005, 34/34 test rieseguiti) + preflight reale dry-run PASS (purchase 211 USDC funding→savings, zero scritture); esecuzione reale in finestra mattutina 18/10. **Estensione REDEEM (P24b) integrata 18/10 (REQ-010: 68/68 test, suite 918): savings→funding→trading, guardia min-savings-residuo, riconciliazione a 3 comparti — sblocca lo step D3 carry.** Fuori dal gate JEV e dal conteggio tentativi.

## Aggiornamento 2026-10-18 — P26 (riapertura lane pairs, direttiva owner)
- P26_cointegrazione_rolling.md ... PRE-REGISTRATA (Artù 18/10) — cointegrazione v2: universo esteso (top 30 perp USDT OKX) + finestre rolling (120/180g, passo 5g); combina le tre varianti ammesse dal verdetto P13. Ultimo giro sulla lane pairs: se fallisce, archiviazione definitiva senza varianti ulteriori. **Preflight dati FATTO 18/10 (64/90 coppie idonee; addendum in spec: finestra effettiva [2020-10-01, 2024-06-01); artefatti `prove/p26_preflight_20261018/`)**. **Misura UFFICIALE 19/10 (Artù): 0/435 coppie eleggibili, exit 2 → ARCHIVIATA DEFINITIVA — lane pairs chiusa** (implementazione Merlino: 18 test, suite 936; run indipendente concorde; artefatti `prove/P26_pairs_rolling*`).

## Aggiornamento 2026-10-18 (notte) — E2 + ondata operai
- E2_significativita.md ...... FATTA 18/10 (Artù) — integrata: `src/money/ricerca/significativita.py` + 14 test (suite 890 verde); fix DD dal valore iniziale (verifica indipendente). Voce di manutenzione (fuori dal conteggio tentativi).
- Ondata operai 18/10: opencode-omarchy → E2 (consegnata 01:12, integrata) + preflight dati P26 (consegnato 15:57, verificato Artù: MATCH su DOGE/ETH/AVAX; addendum spec; artefatti `prove/p26_preflight_20261018/`) · agy-MARCODG1 → preflight dati tick (consegnato 17/10 23:12, verificato Artù 18/10: 4 file 13–16/10, 1.307.065 trade, 0 null/duplicati, 12 gap>60s; artefatti `prove/preflight_tick_20261018/`) + **watchdog `tick_watch` installato in cron su MARCODG1 (10:00 giornaliero; artefatti `prove/tick_watch_20261018/`, canonico in `deploy/cron/crontab-marcodg1.txt`)** · A0-mc2 → ricognizione on-chain/sentiment (docs/36, integrata 18/10).
- P27_d3_scala_carry.md ... **INTEGRATA (Artù 19/10)** — COPPIE LTC/AVAX nel gate carry (12 test, suite 930); **dry-run gate da MARCODG1 (19/10): PASS su LTC e AVAX** (gate carry ok=True, payback 34 periodi/8h, zero ordini) + dry-run redeem P24b PASS (piano 200 USDC savings→trading, min-residuo 500, zero scritture). Prossimo: apertura di UNA coppia (LTC) in finestra mattutina — autorizzazione D3 del proprietario («a step con i gate»).

## Aggiornamento 2026-10-19 (sera) — P28 + audit operai
- P28_chiusura_carry_multi.md ... **INTEGRATA (Artù 19/10)** — `scripts/carry_chiudi.py` (24 test, suite 978); review PASS; **dry-run reale da MARCODG1 PASS su DOT e ADA (zero ordini)**. Il carry multi ora sa chiudere (gap colmato); primo uso reale = decisione operativa con preflight + autorizzazione.
- Audit operai 19/10 (2 turni): **agy-MARCODG1** → audit raccolta dati: trovato e FIXATO il congelamento `data/esterni` (94h, bug "salta se esiste"; fix `c4b75e45` + guardia `raccolta:esterni` in watch_alerts; artefatti `prove/audit_raccolta_20261019/`) · **opencode-omarchy** → audit percorso capitale: 37 difetti (8 ALTA confermati da verifica Artù; priorità fix P1 carry_apri+earn_move, P2 canary; artefatti `prove/audit_capitale_20261019/`, REQ di fix in preparazione).

## Aggiornamento 2026-10-20 — P29 integrata + P30 pre-registrata (hardening capitale)
- P29_hardening_capitale.md ... **INTEGRATA (Artù 20/10)** — 7 fix P1 audit 19/10 (carry_apri: funding con segno, fill parziale con unwind, unwind perp-fallito, preflight saldo spot; earn_move: riconciliazione su eccezione, attendi_funding a delta, poll esteso purchase); review PASS (MANIFEST 11/11; rosso 11f/2p riprodotto in copia isolata; verde 13/13; suite **991**; diff senza collaterali) — commit `23aef229`; **dry-run col codice nuovo da MARCODG1 (sola lettura, zero scritture): LTC con preflight saldo spot 0 (fix attivo) + redeem 210 USDC pianificato**. D3 (apertura LTC): gate ok=True al 20/10 — pronto per finestra/go dell'owner.
- P30_canary_hardening.md ... **INTEGRATA (Artù 20/10)** — fix P2 audit sul canary C1 live (reprice spot/perp con residuo dal fill post-cancel e stop se illeggibile; unwind verificato; close atomica; lock sullo stato). Review: MANIFEST 5/5, **rosso 11f/2p riprodotto** in copia isolata, **verde 13/13**, suite **1004**, ruff pulito, diff confinato a `scripts/canary_carry.py` + test — commit `9d3c72d4`; **MARCODG1 a `9d3c72d`** e `/home/marco/canary/canary_carry.py` aggiornato (backup `.bak-preP30-20261020_2308`), `status --quiet` verificato end-to-end. Finding residuo (→ P33): il lock avvolge l'intero flusso ordini, quindi `status`/`close` vengono rifiutati durante un open/close — da convertire in pattern di prenotazione.

## Aggiornamento 2026-10-21 (notte) — P31 (chiusura carry) + incidente MARCODG1
- **E4_cascate_profonde.md** ... **MISURATA E ARCHIVIATA (Artù 21/10)** — soglia −10%, H=12h, long. TRAIN Bybit n=562 +2,670% (t 7,42) · OOS-1 Bybit n=308 +2,876% (t 5,25) · **OOS-2 OKX (19 simboli scaricati ex-novo) n=89 +1,352% (t 1,51, CI90 attraversa lo zero)** → T1 FAIL, DSR FAIL (0,000, N=21). **Non promuovibile**: segnale forte solo sull'exchange dove è nato. Famiglia «cascate» chiusa (E2+E4). Fix di metodo incluso: cache `eventi_di` per (dataset, soglia).
- **Incidente MARCODG1 20/10 22:41 → 23:03**: host perso per evento di alimentazione (Hetzner FSN1-DC22, maintenance power risolta; journal del boot precedente troncato senza shutdown message, nessun OOM) e **non è tornato su da solo** — riavvio manuale dell'owner. Catena alert corretta (22:45 «MARCODG1 irraggiungibile», 23:00 bots+flotta). Al ritorno: `zabbix-agent` fallito al boot (riavviato e attivo), `money-status-boot` KO per rete non ancora su a 25s (falso allarme, da rendere tollerante), aggregatore :8912 lento per ~2 min poi ok. **Posizioni verificate intatte via nuvola** durante il down: ADA 39ct short, DOT 78ct short, DOGE 11ct short, 0 ordini aperti, 1x isolated. Da fare: auto-power-on nel BIOS/UEFI o API Robot per il reset (serve accesso owner).
- P31_carry_chiudi_fix.md ..... **PRE-REGISTRATA (Artù 20/10)** — audit avversariale `carry_chiudi.py` (21 difetti: 3 ALTA, 10 MEDIA, 8 BASSA; `prove/audit_chiudi_20261020/`). **A1 confermato sulla posizione reale**: ccxt restituisce `contracts=+78, side=short` per DOT e `+39, short` per ADA → `qty_perp` perde il segno e il piano/l'ordine escono `sell reduceOnly` su uno short: **lo strumento non chiude le coppie carry in produzione**. Perimetro P31 = F1-F6 (3 ALTA + 3 MEDIA sullo stesso percorso); il resto è P32; il lock del canary è P33. REQ-MERL-20261020-015 dispatchata.

## Aggiornamento 2026-10-29 (notte) — E9 misurata e archiviata
- E9_funding_spread_crossvenue.md ... **MISURATA E ARCHIVIATA (Artù 29/10)** — misura ufficiale bit-a-bit con lo smoke Morgana: Bybit↔Binance 12m 0/5 positivi (t fino a 8,4 NEGATIVO), OKX 94g 2/5 = artefatto di finestra. Carry lordo positivo, costi 20bp RT + segno non persistente lo azzerano. **Filone funding cross-venue CHIUSO.** Prossima lane: on-chain netflows (RANK 2).

## Aggiornamento 2026-10-29 — E9 (funding-spread cross-venue, lane Morgana RANK 1)
- E9_funding_spread_crossvenue.md ... PRE-REGISTRATA (Artù 29/10, lint 7/7) — rendita market-neutral dal DIFF di funding tra venue (Bybit↔Binance 12m OOS + Bybit↔OKX 94g conferma), gambe opposte leva 1×. Dati Bybit/OKX già in casa; Binance da scaricare (endpoint pubblico). Dispatch: Morgana (implementazione + smoke), misura ufficiale Artù. Non è E7/P21: monetizza lo spread tra venue, non il segno né un paniere.

## Aggiornamento 2026-10-28 — E8 (hold-out Bitvavo, famiglia estremi) + direttiva catena owner
- E8_momentum_estremo_holdout_bitvavo.md ... PRE-REGISTRATA (Artù 28/10, lint 7/7) + PRESA_DA Artù — ultimo test della famiglia «estremi di prezzo»: momentum estremo sui major liquidi misurato su Bitvavo EUR (hold-out mai usato), universo congelato prima dei numeri (7 coppie, volume ≥5M EUR/24h al 28/10). Preflight dati fatto (API pubblica, storia 1h ≥2023-01). Motore: riuso `e6_momentum_estremo.py` + loader Bitvavo. Se T1 fallisce, famiglia chiusa definitivamente e si apre la lane TSMOM 12M/1M long-only BTC/ETH.
- Direttiva owner 28/10 (catena crea→testa→promuovi continua): i sub-creatori (loop S1/S3 automatici + A0) restano attivi; il collo di bottiglia misurato NON è l'orchestrazione ma l'assenza di edge promosso (0 candidati da 6 settimane, DSR 0,95) — nessuna strategia va in produzione senza il cancello spec→test→gate→owner.

## Aggiornamento 2026-10-26 — P34 (gate funding conservativo) + primo ciclo carry chiuso
- P34_gate_funding_conservativo.md ... **PRE-REGISTRATA (Artù 26/10)** — (F1) stima funding del gate: tariffa fissa X-Perp verificata contro la dichiarata / p10 rolling ≥30 periodi per USDT-SWAP; (F2) chiusura economica: `netto >= fee_uscita + basis_uscita` (lezione ciclo ADA: chiuso a netto MTM +0,093 → realizzato −0,157); (F3) riconciliazione su saldi REALI (fetch_balance/positions, mai stato.json stantio — difetto trovato in recon_giornaliero post-scaling DOT); (F4) watchdog tariffa X-Perp. Dispatch: Merlino.
- **Ciclo completo ADA chiuso 26/10 (primo della storia del carry multi)**: carry_chiudi --execute, perp 39 ct + spot 389,61 ADA → 0/0, fee uscita reali 0,1207 USDC = stima dry-run esatta. Realizzato −0,157 USDC su ~90 USDC nozionale in 33 epoche (11 giorni): funding +0,277 copre fee_in 0,135 ma non fee_out+basis (−0,25) → payback ciclo completo ≈47 epoche. Lezione: la condizione di chiusura MTM≥0 chiude prima del pareggio; criterio corretto in P34-F2.

## Aggiornamento 2026-10-29 14:58 — P34 in review + incidente riconciliazione (29/10)
- P34_gate_funding_conservativo.md ... **FATTA (Artù 29/10): REVIEW PASS finale + PR #11 → main d056a6b8 + deploy verificato sui dati vivi.** I 3 finding (multi-riga, flag ledger, watch solo aperte) chiusi da Merlino (suite 1070, rosso→verde); checkout MARCODG1 allineato a main (i tool operativi erano PRE-P34); recon corretto (TOTALE +0,84, net_7g +0,77, liq vera +124,23%, ADA realizzato −0,1565) e canale aggiornato; carry_watch ok=1/1 skip=5. Dettagli: voci 29/10 nel REGISTRO.
- fee_ledger: **FATTA 29/10** (Lancillotto, REQ-MD1-20261029-001; review Artù indipendente): backfill 33→43 righe (4 fill del 26/10 presenti, 0 duplicati), **realizzato ADA = −0,1565 USDC** valorizzato dal recon, cron portato a giornaliero (50 8 * * * + flock), canonico repo allineato. Resta: netto DOT condizionato dal fix F1 (REQ-MERL-023).

## Aggiornamento 2026-10-29 15:00 — 021 chiusa (cruscotto: rendita netta/giorno + benchmark Earn)
- 021 (riga "rendita netta €/giorno per € impegnato" + benchmark Earn su scripts/tabellone.py) ... **REVIEW PASS + INTEGRATA + DEPLOYATA (Artù)**: gate branch 1053 verdi; PR #12 mergiata (main eb32d5fe); deploy su MARCODG1 (sha 454b0dd5…) e verifica di esecuzione reale con gli stessi argomenti del cron — riga presente e datata. Follow-up: mappatura conto/endpoint della stima Earn.

## Aggiornamento 2026-10-29 — E8 misurata: famiglia «estremi di prezzo» CHIUSA DEFINITIVAMENTE
- E8_momentum_estremo_holdout_bitvavo.md ... **MISURATA E ARCHIVIATA (Artù 29/10)** — Bitvavo 1h, 7 coppie congelate, 594 trade: aggregato +0,444% t 1,30 (CI90 [−0,10%, +1,02%]), stress −0,056%, LONG +1,917% t 3,50 (T3 PASS), SHORT −1,12% t −3,02, DSR 0,24 → **1/4: NON PROMOSSA**. Famiglia E2/E4/E5/E6/E8 chiusa: nessuna variante. Test anti-look-ahead 5/5 prima dei numeri; due run a sha identico. Artefatti `prove/e8_bitvavo.*`; motore `scripts/e8_momentum_bitvavo.py`; dati `scripts/scarica_bitvavo_1h.py`. Prossima lane: TSMOM 12M/1M long-only BTC/ETH (da pre-registrare).

## Aggiornamento 2026-10-29 (3) — E10 pre-registrata (stablecoin issuance) + preflight on-chain di Morgana
- **Preflight on-chain (REQ-NUV-20261029-005, Morgana)**: DATI PRONTI con qualificazione — stablecoin flows (DefiLlama, 8 major, 2017→, 1d, gate 8/8) sì; exchange netflows free (CoinMetrics) solo BTC/ETH (2/5, niente USDT, 1d vs 1–6h del paper) → il paper NON è replicabile gratis. Handoff verificato (15/15 + 11/11).
- E10_stablecoin_issuance.md ... **PRE-REGISTRATA (Artù 29/10)** — proxy dichiarato: net issuance nucleo USDT+USDC+DAI; regola congelata (z trailing causale, long-only con isteresi, costi RT 0,20%/switch), TRAIN 2020-02→2024-06 / OOS 2024-06→2026-10, criteri T1–T3 + DSR N=2. Implementazione: Morgana (REQ-NUV-20261029-006). Se fallisce: famiglia on-chain chiusa.

## Aggiornamento 2026-10-29 (4) — E11 pre-registrata (TSMOM long-only BTC/ETH)
- E11_tsmom_btc_eth.md ... **PRE-REGISTRATA (Artù 29/10)** — la baseline time-series momentum 12M/1M nella variante long-only (imposta dalle venue spot-only; short negativi in E6/E8): R12M mensile, pesi uguali BTC/ETH, costi RT 0,20%; criteri T1–T3 + **T4 value-add (DD OOS ≤ DD buy&hold)** + DSR N=5. Implementazione: Merlino (REQ-MERL-20261029-025). Se fallisce: lane chiusa in questa forma.

- REQ-MERL-20261029-024 (follow-up F3): copertura tariffa **canary DOGE ripristinata** (canary_state.json, status=open) — REVIEW PASS + PR #18 → main d4ade17a + deploy MARCODG1; runtime «ok=2/2, skip=4, canary_state(DOGE), alert=NONE».

## Aggiornamento 2026-10-29 (5) — E11 misurata: lane TSMOM chiusa in questa forma
- E11_tsmom_btc_eth.md ... **MISURATA E ARCHIVIATA (Artù 29/10)**: OOS −0,0192%/g t −0,31; TRAIN +0,203%/g t 2,57; T4 PASS (DD 43,6% vs 60,2%); DSR 0,361 → **2/5 NON PROMOSSA**. Smoke Merlino (omarchy) == misura Artù (mc2), numeri identici; spot-check indipendente R12 ok. Prossimi: E10 (Morgana, in misura) · RANK 3 listing event-driven.

## Aggiornamento 2026-10-29 (6) — RANK 3: dati PRONTI + E12 pre-registrata
- Ricognizione REQ-MERL-20261029-026: **DATI PRONTI per OKX+Bybit** (annunci a data+ora, ground truth primo giorno via listTime+candele 8/8 OKX · 7/7 Bybit, delay annuncio→trading 4–24h); Bitvavo parziale; handoff 64/64.
- E12_listing_drift.md ... **PRE-REGISTRATA (Artù)**: «listing drift 24h long-only OKX EEA» — LONG open(t0) → FLAT close 24° bar 1H; costi RT 0,30% (+stress ×2); volume 24h ≥ 50k USDT; TRAIN 2023-06→2025-06 / OOS 2025-06→2026-10; gate T1 (t≥2,7 Bonferroni) · T2 · T3 · T4 (Bybit) · T5 (split-half). In esecuzione: Merlino (engine+test+smoke) → misura ufficiale Artù.

## Aggiornamento 2026-10-29 (7) — E12 misurata: lane listing chiusa in questa forma
- E12_listing_drift.md ... **MISURATA E ARCHIVIATA (Artù 29/10)**: 4/5 — **T1 FALSE per numerosità OOS (n=23 < 60)**; media OOS +69,99% (t 2,02); T2/T3/T4/T5 PASS (Bybit intero n=323, +533,05%, t 8,53). Review consegna Merlino: MANIFEST **37/37**, test **14/14** PRIMA dei numeri, mutate **3/3**, rerun determinismo ok, **misura == smoke bit-a-bit**. Engine+test+freeze nel repo (`scripts/e12_listing_drift.py`, `prove/e12_listing_drift/`); suite 1155. Seguito: eventuale nuova pre-registrazione (universo più ampio per potenza) = decisione Artù; la lane resta chiusa in questa forma.

## Aggiornamento 2026-10-30 (8) — E13 misurata: NON PROMOSSA (4/5); audit Bybit + economia ex-ante in corso
- E13_listing_drift_universo.md ... **MISURATA (Artù 30/10)**: T1 falso per numerosità (**n OOS 86 < 100**; t 2,72 ≥ 2,7, media +79,8%); T2/T3/T4/T5 PASS (Bybit OOS n=86, +381,8%, t 6,77). **Dissezione**: OKX mediana OOS +1,1% (media coda-driven; 2026 mediana 0,0%); **Bybit win-rate 100% = red flag** → REQ-MD1-20261030-003 (audit inquisitorio) + REQ-MERL-20261030-032 (economia ex-ante + entry ritardata). Nessun canary fino agli esiti. Fix `CUT_HI_MS` E12 (refuso date; numeri E12 identici). Suite 1185.

## Aggiornamento 2026-10-30 (7) — E10 misurata: NON PROMOSSA; famiglia on-chain chiusa
- E10_stablecoin_issuance.md ... **MISURATA (Artù 30/10): NON PROMOSSA (1/4)** — OOS aggregato −0,0418%/g (t −1,12), train +0,176%/g (t 2,52), DSR 0,122; sotto buy&hold. Famiglia on-chain/liquidity CHIUSA, nessuna variante.
- **Prossima lane (regola sistema, priorità 2): E14 carry funding multi-simbolo con selezione dinamica del paniere** — pre-registrazione in corso (Artù).
