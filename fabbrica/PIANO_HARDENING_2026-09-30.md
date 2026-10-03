# Piano hardening fabbrica — adozione del documento Manus (30/09/2026)

Fonte: "Architettura migliorata della Fabbrica" (Manus AI, 30/09/2026; docx dell'owner).
Verdetto Hermes: proposta solida e tarata sul nostro stack — SI adotta, con adattamenti.
NON si adotta adesso Kubernetes/Redis/orchestratori: percorso a 3 livelli:
(1) hardening del nastro esistente, (2) control-plane/worker con contratto uniforme,
(3) bus leggero SOLO a soglia misurata. Principio guida:
**il polling resta il meccanismo di sicurezza, gli eventi sono l'acceleratore.**

## Adattamenti al nostro stack (rispetto al documento)
- Tempi: in "sessioni di lavoro" di agenti, non giorni-uomo; nessuna promessa di calendario.
- Worker contract: A0 ha gia' la sua API; per A0-PC/DSH si usano adattatori locali
  (file + HTTP) invece di imporre /v1/jobs ovunque da subito. Uniformare per gradi.
- Job-store: SQLite WAL in `fabbrica/jobs.db` (riuso esperienza SQLite del progetto).
- Metriche: consumatori esistenti = Prometheus/Grafana/Zabbix su MARCODG1; esporre da mc2.
- Segreti: regola "zero secret by default" per A0-PC/DSH; credenziali ricerca/JEV separate
  da quelle exchange (da attuare con l'audit, Incremento 3).
- JEV resta advisory e fail-open; il lint strutturale e' deterministico e NON dipende da modelli.

## Incremento 1 (hardening) — backlog con stato
- [x] JEV gate advisory automatico sulle spec + verdetto in STATO.md (commit f75d432e, 30/09)
- [x] Lint strutturale deterministico delle spec: src/money/spec_lint.py + CLI + 5 test (30/09)
- [x] Job primitives: job_id + idempotency_key + lease_until + attempt + retry/backoff (jobs.db WAL) — modulo `fabbrica/jobs.py` integrato 30/09 (J1 via A0-MC2, 10/10 test); **cablato nel tick il 03/10** (`check_jobs`: accoda azioni con dedup, auto-chiude i job verificabili, metriche `factory_jobs_*`)
- [x] Dedup consegne: stesso idempotency_key => mai doppia integrazione — attiva per le azioni del nastro (spec/inbox, 03/10); per gli handoff si integra col protocollo di consegna (lane DSH-win, in corso)
- [x] Wire del lint nel tick (accanto al gate JEV) — 03/10: `check_lint`, un esito per hash in `STATO.md` e fix-job automatici
- [ ] Metriche minime: last_successful_tick ✓, queue_oldest_age ✓, heartbeat_age ✓, stale_gate_age ✓, job metrics ✓ (03/10); resta `job_duration` (in attesa dei claim automatizzati)
- [x] STATO.md derivato: generated_at + control_plane_revision (git rev); non fonte di verita' — dal 03/10
- [x] Kill-switch di fabbrica (file STOP: blocca nuovi job, non cancella la coda; visibile in STATO) — attivo dal 30/09; esteso a job-store/lint il 03/10
- [ ] Handoff atomico: scrittura tmp + fsync + rename, marker READY per ultimo, claim atomica
- [ ] Heartbeat di progresso per worker (A0: ultimo poll ok; banco: ultimo giro; con timestamps)

Criterio di uscita Incremento 1: un riavvio di mc2 / dei worker / della sincronizzazione
NON produce doppie integrazioni ne' perdite.

## Incrementi successivi (sintesi dal documento Manus)
2. Contratto worker uniforme (healthz/readyz/v1/jobs), adapter Windows per A0-PC, classi di
   errore (transient/busy/invalid/test/policy), recovery lease scadute, dashboard coda+heartbeat.
3. Segreti e audit: inventario credenziali (owner, scopo, nodi, scadenza), .env.example come
   schema, rotazione tracciata senza valori; opzione age/SOPS per bundle cifrati per nodo.
4. Bus SOLO a soglia (misurare >=7 giorni): >50 job/giorno o >10 eventi/min | P95 presa in carico
   >2 min | >20 handoff pendenti >15 min | fan-out >=3 consumer | >1% duplicati.
   Prima scelta: HTTP autenticato su tailnet + inbox SQLite; poi Redis AOF; NATS oltre.

## Regole invariate (non negoziabili)
- Fail-closed per integrazione/test/manifest/policy; fail-open SOLO per il parere JEV advisory.
- Promozione mai automatica verso capitale/live: gate + azione umana restano separati.
- Un bot per conto; segreti mai in git, mai nei log, mai nei canali di consegna.

## Aggiornamenti
- **2026-10-03**: job-store e lint cablati nel tick (`check_jobs`/`check_lint`); dedup azioni + auto-chiusura verificabile (spec materializzate/aggiornate, inbox rimosso); metriche `factory_jobs_*` e `factory_specs_lint_bad`; `STATO.md` con control-plane rev. Restano: handoff atomico (lane DSH-win), claim atomica, `job_duration`.
