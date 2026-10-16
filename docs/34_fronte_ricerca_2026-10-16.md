# 28 — Nuovo fronte di ricerca (onda S5): dove cercare l'edge adesso
Data: 2026-10-16 · Autore: hermes (ingegnere capo) · Stato: ATTIVO

## Perché un fronte nuovo
La caccia sulle candele è chiusa PER EVIDENZA, non per sfiducia: S1–S4 hanno battuto
~600.000 configurazioni (S4: 316.728 tentativi, 0 candidati al DSR; il loop giornaliero
continua a dare 0). Il filone "indicatori su OHLCV" ha emesso il suo verdetto: nessun edge
sopravvissuto ai costi sulle nostre tariffe. L'unico motore con evidenza netta positiva è il
FUNDING/CARRY (P12, P19b, C1). E il pedaggio è il giudice di ogni edge (cancello, criterio 6):
ridurlo = creare edge. Quindi il fronte S5 NON è "ancora candele": è funding + esecuzione + dati nuovi.

## L'onda S5 — tre voci, tutte pre-registrate PRIMA dei numeri
1. **P21 — Paniere carry: regola di selezione e pesi** (estende oltre C1 e DOT+ADA).
   Spec: `coda_catena/P21_carry_basket.md`. Netto costi, 6 configurazioni, 3 baseline.
2. **P22 — Gate di regime RARO sul carry, giudicato NETTO** (chiude l'ultima variante aperta
   dall'addendum P12). Spec: `coda_catena/P22_regime_gate_netto.md`.
3. **P23 — Pedaggio REALIZZATO sui nostri fill + studio maker-first** (il costo vero, non le
   tariffe). Spec: `coda_catena/P23_pedaggio_esecuzione.md`.

## Chi lavora (gli aiutanti)
- **DSH-omarchy**: implementa P21 (turno headless pilotato da mc2; consegna via handoff `dsh-mc2/handoff/P21/`). REQ formale sul canale `dsh-mc2/`.
- **Primo libero** (fabbrica/DSH/opencode/A0): P22 — la spec è in coda; si prende con `STATO: PRESA_DA <chi> <data>`.
- **Hermes**: P23 (dati banco read-only già in mano) + review dei consegnati + misure UFFICIALI + cancello.
- **Fabbrica**: il tick riconosce le nuove spec (specgen); job-store = coda di lavoro dei worker.

## Dati e tempi
- Funding: storia via ccxt pubblico (~3 mesi) + archivio interno in crescita. La scansione
  completa del filone (n ≥ 60 giorni) matura a metà novembre.
- Tick/orderflow: raccolta attiva su MARCODG1 (DOGE per ora). Scansione dichiarata quando ci
  saranno ≥ 30 giorni di dati (~15/11). Fino ad allora: accumulo, zero misure premature.
- Ritmo: P21 questa settimana; P22 subito dopo; P23 appena il ledger ha materiale sufficiente.

## Disciplina (non negoziabile)
- Ogni voce passa dal cancello; nessun live senza canary; costi SEMPRE detratti; campione corto
  dichiarato; contatore varianti; se una voce muore (archiviata) il fronte lo dichiara e si sposta.
- Nessun ordine reale, nessuna chiave in gioco in queste voci: sono misure.

## Cosa cambia per la scala (D2/D3 ROADMAP)
P21 dà la regola per COMPORRE il paniere quando si scala; P22 dà la regola di QUANDO stare
fuori; P23 dà il costo VERO da usare nelle soglie. Insieme = l'infrastruttura di decisione per
portare il carry da ~180€ a 400€+ (D3) senza inventare nulla. La scala parte solo con un esito
positivo di queste voci; altrimenti si resta a C1+coppia corrente e si continua a cercare.
