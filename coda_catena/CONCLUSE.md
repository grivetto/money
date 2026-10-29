# Spec fuori dal gate di dispatch — CONCLUSE (retrofit 2026-10-06)

Le spec elencate qui NON hanno piu' oggetto nel gate di dispatch (JEV + lint) ne' nel
job-store: esperimenti con verdetto gia' congelato nel registro, oppure voci che non sono
esperimenti (infrastruttura integrata, milestone di governance).

Il gate vale per le spec **attive**: al 19/10 nessuna voce di ricerca attiva (P26 chiusa) — P4 e P8 concluse l'08/10
(P4 misurata con verdetto nel registro; P8 infrastruttura integrata, non esperimento);
P21 e P22 concluse il 17/10, P23 conclusa il 18/10, P26 conclusa il 19/10 (verdetti nel registro).
Aggiungere/rimuovere voci SOLO quando lo stato nel registro cambia — rimuovere una voce
riapre gate e fix per quella spec.

- P1_trend_atr_stop.md — archiviata (verdetto nel registro, 27/09)
- P2_momentum_vol_target.md — archiviata per costruzione (30/09)
- P3_trend_filtro_200g.md — archiviata (29/09)
- P5_donchian_esteso.md — archiviata (28/09)
- P6_portafoglio.md — archiviata per costruzione (30/09)
- P10_momentum_cross.md — insufficiente; filone chiuso da P14 (03/10)
- P11_vol_breakout_atr.md — archiviata per costruzione (30/09)
- P12_funding_regime.md — misurata, descrittiva solida (01/10); il carry prosegue via P4/C1
- P13_cointegrazione_pairs.md — archiviata (01/10)
- P14_momentum_universo.md — archiviata (03/10)
- E1_economia_unitaria.md — infrastruttura integrata (30/09); non e' un esperimento
- M1_release_validazione.md — milestone di governance; il suo stato vive nel piano M1
- P4_funding_carry.md — misurata l'08/10/2026: 9/10 simboli sotto la soglia dell'8% netto dichiarata PRIMA (DOT promosso, copertura 62 g) ⇒ nessuna allocazione; ri-misura quando la storia supera ~180 giorni
- P8_funding_harvest.md — infrastruttura integrata e attiva (raccolta funding cron 4h, certificato P8B); non è un esperimento
- P21_carry_basket.md — archiviata (nessuna config con netto addestramento > 0; verdetto nel registro, 17/10)
- P22_regime_gate_netto.md — archiviata (ogni trigger delta<=0 su 10/10 simboli; timing del carry chiuso, 17/10)
- P23_pedaggio_esecuzione.md — FATTA 18/10 (fee reali = tariffa taker esatta, riconciliazione MATCH; soglie confermate; maker-first non consigliato; report `prove/P23_report.md`)
- P24_dormienti_earn.md — FATTA 18/10 (mossa D2 eseguita: 211 USDC funding + 25 USDC trading → Simple Earn, savings 835,75 USDC; estensione redeem P24b integrata 18/10: 68 test, sblocca D3; voce operativa di tesoreria, non esperimento)
- P25_kpi_settimanali.md — FATTA 18/10 (KPI settimanali + collector fee ledger integrati e in cron lunedì; voce operativa di osservabilità, non esperimento)
- E2_significativita.md — infrastruttura integrata (18/10): strumenti di significatività bootstrap + Monte Carlo in `src/money/ricerca/significativita.py`; non è un esperimento
- P26_cointegrazione_rolling.md — ARCHIVIATA DEFINITIVA (19/10: screening ufficiale 0/435 coppie eleggibili, exit 2; run indipendente concorde; verdetto nel registro) — lane pairs chiusa

- **E7 — funding_extreme_contrarian** (22/10) — NON PROMOSSA, 6/6 criteri colpiti: n=4332, netto −0,2213%/trade (t −1,49), lordo +0,0787% (t +0,53, cioè zero), PF netto 0,93, maxDD 102%, IC90 attraversa lo zero. Artefatti: `prove/REGISTRO_ESPERIMENTI.md` (voce 22/10), handoff `hermes_bridge/merlino/handoff/E7/`, spec `docs/ipotesi/funding_extreme_contrarian.md`. Il funding non è un segnale direzionale: è una rendita da incassare (carry).
- E8_momentum_estremo_holdout_bitvavo.md — MISURATA e archiviata (29/10): NON PROMOSSA (1/4); famiglia «estremi di prezzo» chiusa definitivamente
- E9_funding_spread_crossvenue.md — MISURATA e archiviata (29/10): NON PROMOSSA (0/5 su 12m); filone funding cross-venue chiuso
- E11_tsmom_btc_eth.md — MISURATA e archiviata (29/10): NON PROMOSSA (2/5); lane TSMOM chiusa in questa forma
- E12_listing_drift.md — MISURATA e archiviata (29/10): NON PROMOSSA (4/5; T1 n=23<60, segno OOS positivo t=2,02); lane listing chiusa in questa forma
