# Fabbrica Denaro — il nastro

Ogni 5 minuti (cron) un **tick** esegue/avanza UNA azione del percorso:

    candidato -> test (misure sui dati reali) -> cancello -> produzione SOLO su promozione

## Cosa fa un tick
1. heartbeat: aggiorna `STATO.md` (leggibile) e `log/fabbrica.log`;
2. scansione del canale DSH (`hermes_bridge/dsh/results.md`): voci nuove;
3. controllo dell'handoff P2 (`hermes_bridge/dsh/handoff/P2/`): se arrivano artefatti,
   verifica il `MANIFEST.sha256`;
4. stato P2: se il runner di misura è nel repo -> marca AZIONE "misurare";
5. watchdog **A0-PC** (`http://100.76.22.119:50080/api/health`) e **banco MARCODG1**;
6. specgen: se la coda delle spec è vuota, marca la prossima spec da materializzare
   (da `candidati.json`).

Le azioni che richiedono giudizio o dati nuovi vengono **marcate come AZIONE** in `STATO.md`
con l'owner (Hermes / DSH / A0). Il nastro non inventa numeri e non forza promozioni.

## Regole non negoziabili
- **Test prima dei numeri**; griglie dichiarate PRIMA; niente HARKing.
- **Il cancello decide meccanicamente**: la sua bocciatura è vincolante.
- **Produzione** = solo dopo PASS del cancello + review. Deploy a size minima sul sub-account
  corretto, dentro i limiti del mandato (2%/trade, -3%/giorno, -10% DD), un bot per conto,
  chiavi valide e preflight. Il capitale lo versa il proprietario: il cancello non è una
  scorciatoia per aggirarlo.
- **Zero ordini/invii da qui**: la fabbrica non tocca gli exchange.

## Collaboratori
- **Hermes** (mc2): review, commit/push, misure, dispatch, gate.
- **DSH** (Windows): implementazioni + misure in handoff su file (hash nel MANIFEST).
- **A0-PC** (Windows, API `:50080`): task con criterio = un test che fallisce sul codice vecchio.

Deposito job/prove: `fabbrica/inbox/` (append-only, chiunque).

## File
- `fabbrica.py` — il tick (stdlib only; gira col python del venv AOT).
- `candidati.json` — la coda **dichiarata** dei candidati/spec (stato per ciascuno).
- `state.json` — stato macchina (runtime, ignorato da git).
- `STATO.md` — stato leggibile (runtime, ignorato da git).
- `log/` — log dei tick (runtime, ignorato da git).
