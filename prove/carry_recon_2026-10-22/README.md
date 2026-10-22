# Riconciliazione carry DOT/ADA — 2026-10-22

Prodotto da **Hermes-MARCODG1** (nodo carry) su REQ-20261022-003, integrato da Artù (mc2) dopo verifica hash.

- `RECON_DOT_ADA.md` — riconciliazione completa: funding, fee, uPL, delta spot, netto. sha256 `83f50176…`
- `recon.csv` — tabella per macchina. sha256 `50da1f34…`
- `manifest.json` — provenienza dati OKX (endpoint, timestamp di fetch, sha256 dei grezzi). sha256 `1167301a…`

Note:
- Strumenti reali in portafoglio: X-Perp EEA `DOT-USD_UM_XPERP-310808` e `ADA-USD_UM_XPERP-310404` (NON i `*-USDT-SWAP`, che hanno funding molto più basso).
- Solo dati pubblici OKX (nessuna chiave); fill da `logs/fee_ledger.jsonl`.
- Risultato (18 epoche funding, 16/10 00:00Z → 21/10 16:00Z): funding X-Perp +0.3159 USDC, fee ingresso -0.2697 USDC, uPL perp +2.4850, delta spot MTM -2.6400 → netto stimato -0.1088 USDC. Il funding ha già superato le fee; il payback resta dominato dallo sbilancio d'ingresso e dal basis.
