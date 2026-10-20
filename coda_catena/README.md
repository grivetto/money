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
- **Incidente MARCODG1 20/10 22:41 → 23:03**: host perso per evento di alimentazione (Hetzner FSN1-DC22, maintenance power risolta; journal del boot precedente troncato senza shutdown message, nessun OOM) e **non è tornato su da solo** — riavvio manuale dell'owner. Catena alert corretta (22:45 «MARCODG1 irraggiungibile», 23:00 bots+flotta). Al ritorno: `zabbix-agent` fallito al boot (riavviato e attivo), `money-status-boot` KO per rete non ancora su a 25s (falso allarme, da rendere tollerante), aggregatore :8912 lento per ~2 min poi ok. **Posizioni verificate intatte via nuvola** durante il down: ADA 39ct short, DOT 78ct short, DOGE 11ct short, 0 ordini aperti, 1x isolated. Da fare: auto-power-on nel BIOS/UEFI o API Robot per il reset (serve accesso owner).
- P31_carry_chiudi_fix.md ..... **PRE-REGISTRATA (Artù 20/10)** — audit avversariale `carry_chiudi.py` (21 difetti: 3 ALTA, 10 MEDIA, 8 BASSA; `prove/audit_chiudi_20261020/`). **A1 confermato sulla posizione reale**: ccxt restituisce `contracts=+78, side=short` per DOT e `+39, short` per ADA → `qty_perp` perde il segno e il piano/l'ordine escono `sell reduceOnly` su uno short: **lo strumento non chiude le coppie carry in produzione**. Perimetro P31 = F1-F6 (3 ALTA + 3 MEDIA sullo stesso percorso); il resto è P32; il lock del canary è P33. REQ-MERL-20261020-015 dispatchata.
