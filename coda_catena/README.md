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
- P24_dormienti_earn.md ...... INTEGRATA (Artù 18/10) — harness `scripts/earn_move.py` consegnato da Merlino (REQ-MERL-20261017-005, 34/34 test rieseguiti) + preflight reale dry-run PASS (purchase 211 USDC funding→savings, zero scritture); esecuzione reale in finestra mattutina 18/10. Fuori dal gate JEV e dal conteggio tentativi.

## Aggiornamento 2026-10-18 — P26 (riapertura lane pairs, direttiva owner)
- P26_cointegrazione_rolling.md ... PRE-REGISTRATA (Artù 18/10) — cointegrazione v2: universo esteso (top 30 perp USDT OKX) + finestre rolling (120/180g, passo 5g); combina le tre varianti ammesse dal verdetto P13. Ultimo giro sulla lane pairs: se fallisce, archiviazione definitiva senza varianti ulteriori. In attesa di coda libera; implementatore da assegnare al via.
