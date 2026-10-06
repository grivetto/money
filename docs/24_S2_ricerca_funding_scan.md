# 24 — S2 Ricerca: scansione del funding carry (X-Perp OKX EEA)

Direttiva: «massimizzare il rendimento costante, proteggendo il capitale» (mandato 06/10/2026).
Questo documento è la **spec dichiarata PRIMA** del lavoro (protocollo di sempre: spec → misura →
cancello). Non promuove nulla: produce una classifica di candidati da pre-registrare.

## Obiettivo

Quantificare l'edge di **funding carry** sui X-Perp OKX EEA: quali contratti hanno funding
sistematicamente a favore dello short (o del long) e con quale rendimento NETTO (fee, spread,
slippage) sulla taglia minima del conto (~1.000 €).

## Dati

- `data/funding_xperp.jsonl` (raccolto dal `raccoglitore_funding`): una riga per
  (simbolo perp, ts ms): `{"simbolo": "BTC/USD:USD-310404", "ts": 1782720000000,
  "funding": -0.0001102044624311, "basis_pp": 0.0, "fonte": "okx"}`.
- Estensione consentita: API pubbliche OKX EEA (ccxt, `fetchFundingRateHistory`) per portare la
  storia all'universo perp che ci interessa. SOLO endpoint pubblici.
- Tariffe del conto: `money.costi` (okx_eea con X-Perp; pedaggio misto ≈ 0,0018 round-trip) +
  slippage dichiarato per lato.

## Deliverable

1. `src/money/ricerca/funding_scan.py` — modulo: carica il JSONL, aggrega per simbolo,
   calcola per ogni simbolo: n osservazioni, funding medio/mediano giornaliero,
   annualizzato NETTO (fee entrata+uscita + slippage dedotti e dichiarati), frazione di giorni
   positivi per lato short, persistenza (autocorrelazione del funding), giorni di storia.
   Funzioni pure, testabili offline (il file di input è un parametro).
2. `tests/ricerca/test_funding_scan.py` — test su fixture sintetiche (no rete).
3. `scripts/funding_scan.py` — entrypoint: produce `prove/funding_scan_<data>.json` + `.txt`
   con la classifica e il dettaglio per simbolo; stampa un riassunto.

## Criteri di lettura (NON promozione)

- Ordinamento per rendimento NETTO annualizzato; evidenziare: persistenza > 0, n >= 60 giorni,
  netto > 0 dopo costi assumendo 1 ciclo di apertura/chiusura al mese (rotazione).
- Segnalare i simboli con |funding giornaliero| > 0,5% (soglia di anomalia del canary) come
  "da verificare" (possibile errore dati, non edge).
- L'output è DESCRITTIVO: i candidati si pre-registrano come esperimenti (spec propria) e passano
  da `money.cancello`. Nessuna promozione automatica.

## Vincoli

- Nessun ordine, nessuna chiave: solo dati pubblici e file locali.
- Solo stdlib + ccxt; niente pandas.
- Il lavoro gira in un worktree dedicato (`s2/funding-scan`), commit sul branch, MAI su main.
- Test: `python -m pytest tests/ricerca/test_funding_scan.py -q` deve passare.
