# Fabbrica Denaro — il nastro

Ogni 3 secondi (timer systemd; x100 dal 02/10) un **tick** esegue/avanza UNA azione del percorso.
La fabbrica è **distribuita**: master su mc2 + un **worker di nodo** su MARCODG1 e nuvola (ogni 5s,
unità `fabbrica-worker.timer`) che pubblicano i controlli locali in `fabbrica/shards/`;

    candidato -> test (misure sui dati reali) -> cancello -> produzione SOLO su promozione

## Cosa fa un tick
1. heartbeat: aggiorna `STATO.md` (leggibile) e `log/fabbrica.log`;
2. scansione del canale DSH (`hermes_bridge/dsh/results.md`): voci nuove;
3. controllo dell'handoff P2 (`hermes_bridge/dsh/handoff/P2/`): se arrivano artefatti,
   verifica il `MANIFEST.sha256`;
4. stato P2: se il runner di misura è nel repo -> marca AZIONE "misurare";
5. watchdog **A0-MC2** (API locale); **A0-PC** e **banco MARCODG1** arrivano dagli shard dei worker (nuvola / MARCODG1 — niente ssh nel tick);
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

## Worker di nodo (fabbrica distribuita)
Installazione su MARCODG1/nuvola: copiare `worker.py` in `~/fabbrica/`, poi
`deploy/systemd/fabbrica-worker.{service,timer}` in `/etc/systemd/system/` con
`__USER__`/`__HOME__`/`__NODE__` sostituiti, quindi
`systemctl daemon-reload && systemctl enable --now fabbrica-worker.timer`.

## File
- `fabbrica.py` — il tick master (stdlib only; gira col python del venv AOT).
- `worker.py` — worker di nodo (stdlib): controlli locali -> shard verso mc2.
- `shards/` — shard dei worker (runtime, ignorato da git).
- `candidati.json` — la coda **dichiarata** dei candidati/spec (stato per ciascuno).
- `state.json` — stato macchina (runtime, ignorato da git).
- `STATO.md` — stato leggibile (runtime, ignorato da git).
- `log/` — log dei tick (runtime, ignorato da git).
