# P21 — Carry multi-coppia: selezione e pesi del paniere (estensione di C1)
STATO: DA PRENDERE — pre-registrata 2026-10-16 (hermes); primo dispatch a DSH-omarchy (turno headless 16/10 sera). La misura UFFICIALE la esegue Hermes.
Repo: grivetto/alpha-omega-trading · commit di registrazione: ea7ae01b (file di questa voce: `coda_catena/P21_carry_basket.md`).

## Obiettivo (verificabile)
Decisione operativa: definire CON REGOLA PUBBLICA la selezione e i pesi del paniere carry X-Perp su OKX EEA, per estendere oltre C1 (DOGE) e oltre la coppia ad hoc DOT+ADA. Output della misura: per ogni configurazione, flusso funding NETTO (costi di ciclo detratti) in addestramento e in verifica + confronto con le baseline dichiarate. Nessuna promozione automatica: la promozione passa dal cancello come voce formale.

## Contesto
C1 è la validazione esecutiva di UN simbolo; il carry multi è oggi una scelta ad hoc (DOT+ADA) mai giustificata da una regola misurata. D2/D3 della ROADMAP scalano il carry a step condizionati: la regola di composizione è il prerequisito mancante. Il filone funding è l'UNICO con evidenza positiva netta (P12, P19b).

## Ipotesi
- H1 (selezione): una regola top-k per media funding trailing 30g, ribilanciata ogni 30g su calendario, batte in NETTO le baseline dichiarate (DOGE-solo; paniere-corrente DOT+ADA; media-carry dei 10) in addestramento E regge in verifica.
- H2 (pesi): a parità di selezione, {equal, inverse-vol} differiscono MENO della selezione stessa (la scelta di COSA tenere conta più di COME pesarlo).
- H3 (drawdown): il paniere k=3 riduce il max drawdown del flusso cumulato vs DOGE-solo.

## Meccanica (dichiarata prima dei numeri)
- MU: funding per evento 8h (00/08/16 UTC). Selezione a t: media funding ultimi 30 giorni per simbolo, SOLO eventi ≤ t−1 (anti-look-ahead); top-k. Ribilanciamento ogni 30g a data fissa di calendario.
- Ogni cambio di composizione = 1 ciclo (uscita coppia + entrata coppia). Costo ciclo C = 0,40% per coppia coinvolta (conservativo P12: spot 0,10%×2 + perp 0,05%×2 + slippage 0,10%); stress C = 0,62%.
- NETTO(H) = flusso funding catturato − C × n_cicli, su finestre rolling di {30, 90} giorni — riportate TUTTE, nessuna selezione.
- Baseline dichiarate: (b1) DOGE-solo always-on; (b2) DOT+ADA equal (stato attuale); (b3) media-carry dei 10 major equal-weight senza selezione.
- Confronto: {k=2,3,4} × {equal, inverse-vol} = 6 configurazioni; tutte provate in addestramento; la migliore per NETTO(90g) addestramento va a verifica UNICA.

## Griglia dichiarata (minima — niente ottimizzazione)
- k ∈ {2,3,4}; pesi ∈ {equal, inverse-vol}; lookback selezione = 30g (UNICO); ribilancio = 30g (UNICO); costi {0,40%, 0,62%}. NIENT'ALTRO. Ogni variante ulteriore = nuova voce di registro (regola del contatore varianti).

## Universo, dati e campionamento
10 major con funding EEA (da P19b): DOGE, LTC, ADA, XRP, LINK, BTC, ETH, SOL (archivio lungo) + DOT, AVAX (campione corto, riportati a parte). Dati: (a) storia funding via ccxt pubblico `fetchFundingRateHistory` (nessuna chiave, OKX EEA USDT-swap — profondità tipica ~3 mesi); (b) archivio interno `data/funding_xperp.jsonl` (dal 29/06) per la finestra recente; (c) finestre: addestramento = primi 70% del campione, verifica = ultimi 30% (UNICA, non ritagliata a posteriori). Survivorship: delistati assenti dagli archivi (dichiarato). CAMPIONE CORTO dichiarato in OGNI output (generalizzazione temporale = rischio principe).

## Criteri di stop / esiti ammessi
- Nessuna configurazione con NETTO addestramento > 0 → archiviata (la composizione resta ad hoc documentata; D3 scala solo su C1 + coppia corrente).
- Successo (candidata esecutiva): NETTO > 0 in addestramento E in verifica E ≥ miglior baseline netta E maxDD flusso ≤ 50% di DOGE-solo.
- Esiti ammessi: {candidata-esecutiva, descrittiva, insufficiente, archiviata}. Mai "promossa" senza cancello.

## Anti-bias
- Media a t usa SOLO eventi ≤ t−1 (test dedicato: atteso = ricalcolo manuale su finestra marker).
- Ribilanci a date di calendario fisse; nessuna scelta ex-post di finestre o simboli.
- Costi SEMPRE detratti, anche per le baseline (le regole di uscita frequenti sono morte su questo in P12-addendum: 0/10 netto).

## Fuori scope
- NIENTE P&L di prezzo, delta residuo, mark price, liquidazione: rischio dell'esecuzione (C1/carry), non di questa misura (funding-only, come P12).
- Nessun ordine, nessuna chiave, nessuna scrittura in `~/money` da parte dell'implementatore: si consegna in handoff.
- Non modificare script esistenti (`scripts/misura_p12.py`, moduli `src/money/ricerca/*`): nuovo codice isolato.

## Contratto di consegna (per l'implementatore)
Input: i dati pubblici sopra + questa spec + `src/money/costi.py` come riferimento di stile per i costi. Output atteso: `misura_p21.py` (CLI: `--smoke` su 3 simboli/finestra ridotta; default = campione pieno), `test_misura_p21.py`, artefatto `P21_smoke.json` dal run `--smoke`, `LEGGIMI.md`, `MANIFEST.sha256`, `READY` (per ultimo).
Criteri di accettazione:
- [ ] `--smoke` gira end-to-end su dati reali pubblici e produce `P21_smoke.json` con le 6 configurazioni × 2 costi (anche su finestra ridotta)
- [ ] i test passano: anti-look-ahead (la selezione a t ignora gli eventi > t−1; atteso = ricalcolo manuale su marker) e conteggio cicli su serie sintetica
- [ ] zero dipendenze da chiavi API: solo endpoint pubblici
- [ ] consegna via scp in `dsh-mc2/handoff/P21/` con MANIFEST e READY per ultimo
Comando di verifica (nel proprio scratch):
```bash
python -m venv .venv && .venv/bin/pip install ccxt pytest numpy
.venv/bin/python -m pytest test_misura_p21.py -q
.venv/bin/python misura_p21.py --smoke && head -50 P21_smoke.json
```
## Riferimenti
P4 · P12 (+addendum netto) · P19b · C1 (docs/16) · ROADMAP.md D3 · docs/18 (protocollo referee).
