# P22 — Carry: gate di regime RARO, giudicato NETTO dei costi di ciclo
STATO: FATTA — ARCHIVIATA (2026-10-17). Implementazione Merlino (REQ-002, hash OK, 13/13 test rieseguiti da Artù); misura UFFICIALE di Artù 17/10: ogni trigger delta<=0 su 10/10 simboli a entrambi i costi; T3 mai avvenuto. Verdetto: il timing del carry e' chiuso, sempre-on. Artefatti: `prove/P22_full_2026-10-17.json`.
Repo: grivetto/alpha-omega-trading · commit di registrazione: ea7ae01b (file di questa voce: `coda_catena/P22_regime_gate_netto.md`).

## Obiettivo (verificabile)
Chiudere l'UNICA variante lasciata aperta dall'addendum P12 (01/10): le uscite FREQUENTI perdono netto (0/10), ma un segnale RARO di regime negativo persistente non è mai stato misurato. Output: per ogni trigger dichiarato, delta NETTO (costi di ciclo detratti) di carry-gated vs always-on, per simbolo, + stabilità tra le metà.

## Contesto
P12 conclude "sempre-on è la regola" per le uscite al primo negativo; l'addendum invita esplicitamente a testare solo segnali rari (es. regime negativo persistente) come NUOVA voce. Questa è quella voce. Se il gate vince netto → regola operativa per la futura P4-formale / scala D3; se perde → il fronte "timing del carry" si chiude con questa voce (zero revival senza nuova evidenza).

## Ipotesi
- H1: almeno un trigger con ≤ 4 episodi/anno per simbolo migliora il NETTO vs always-on su ≥ 6/10 simboli.
- H2: i trigger cross-sectional (breadth) battono i trigger per-simbolo in stabilità (segno concorde nelle due metà su ≥ 6/10).

## Meccanica (dichiarata prima dei numeri)
- Trigger dichiarati (tutti e soli): T1 = media funding 7g < 0; T2 = media funding 14g < 0; T3 = breadth (frazione dei 10 major con media 7g > 0) < 20%.
- Azione: trigger attivo a t ⇒ flat da t (nessun funding catturato); trigger spento ⇒ rientro all'evento successivo. OGNI transizione (uscita E rientro) paga C = 0,40% per coppia (stress 0,62%).
- Metriche: flusso NETTO annualizzato per simbolo (gated − always-on), n. episodi/anno, quota periodi flat, maxDD del flusso, stabilità tra due metà calendariali fisse.
- Anti-look-ahead: trigger calcolato su eventi ≤ t−1.

## Griglia dichiarata
{ T1, T2, T3 } × costi {0,40%, 0,62%}. Nessuna soglia ottimizzata, nessuna combinazione di trigger. NIENT'ALTRO. Varianti ulteriori = nuova voce di registro.

## Universo, dati e campionamento
10 major come P21 (DOT/AVAX a parte, campione corto). Stessa base dati di P21 (ccxt pubblico + archivio interno `data/funding_xperp.jsonl`). Divisione a metà calendariale fissa (per data, non per convenienza). CAMPIONE CORTO dichiarato in ogni output.

## Criteri di stop / esiti ammessi
- Delta netto ≤ 0 su ≥ 5/10 simboli per tutti i trigger → ARCHIVIATA: "il timing del carry è chiuso; sempre-on". 
- Successo: delta > 0 su ≥ 6/10 E stabilità (segno concorde tra le metà) su ≥ 6/10 → adottabile-su-evidenza (nuova voce per la regola operativa; mai live diretto).
- Esiti ammessi: {adottabile-su-evidenza, descrittiva, insufficiente, archiviata}.

## Anti-bias
- Costi contati per OGNI transizione (uscita e rientro), mai gratis; se un trigger è attivo a sprazzi è un'uscita frequente mascherata: si conta e si riporta.
- Il rientro avviene all'evento successivo alla condizione: una transizione per volta, niente rientri ottimistici.
- Metà fisse di calendario, non scelte a posteriori; costi SEMPRE detratti anche per sempre-on (baseline dichiarata).

## Fuori scope
- P&L di prezzo (funding-only, come P12/P21); ordini; chiavi; modifiche a `scripts/misura_p12.py` (nuovo modulo isolato `misura_p22.py`).

## Contratto di consegna (per l'implementatore)
Input: dati pubblici + archivio come P21 + questa spec. Output atteso: `misura_p22.py` (CLI `--smoke`), `test_misura_p22.py`, `P22_smoke.json`, `LEGGIMI.md`, `MANIFEST.sha256`, `READY`.
Criteri di accettazione:
- [ ] `--smoke` su 3 simboli produce le 3 righe trigger × 2 costi nel JSON
- [ ] test anti-look-ahead: il trigger a t ignora eventi > t−1 (atteso = ricalcolo manuale su marker)
- [ ] test conteggio transizioni su serie sintetica (atteso: n transizioni esatto, inclusi casi di trigger a sprazzi)
- [ ] consegna in `dsh-mc2/handoff/P22/` (MANIFEST, READY per ultimo)
Comando di verifica:
```bash
.venv/bin/python -m pytest test_misura_p22.py -q
.venv/bin/python misura_p22.py --smoke && head -50 P22_smoke.json
```
## Riferimenti
P12 + addendum 01/10 · P21 · C1 · ROADMAP.md D3.
