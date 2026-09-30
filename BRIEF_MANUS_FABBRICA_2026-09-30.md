# Foto della "Fabbrica" — snapshot per Manus AI (30/09/2026)

> Cosa è questo documento: una fotografia del nastro automatico ("fabbrica") del progetto
> Denaro, scritta per essere autosufficiente (nessun accesso al repo necessario).
> Cosa chiediamo a Manus: suggerimenti sull'INFRASTRUTTURA (orchestrazione, resilienza,
> osservabilità, segreti multi-nodo, formato dei brief per agenti autonomi).
> Nessun segreto è incluso; i nodi sono identificati per nome.

---

## 1. Cos'è la fabbrica (TL;DR)

Un ciclo produttivo automatico che trasforma idee di trading in candidati verificati:

    candidato -> spec -> test -> cancello -> (promozione) | (archivio)

- Gira su un tick **ogni 5 minuti** (cron + flock): UN tick esegue/avanza **UNA** azione utile
  e aggiorna uno stato leggibile (`STATO.md`).
- **NON** tocca i mercati, **NON** piazza ordini, **NON** inventa numeri: le azioni che
  richiedono giudizio umano vengono solo MARCATE come "AZIONE" per l'owner.
- Regola d'oro del progetto: *"test prima dei numeri; il cancello decide; produzione solo
  su promozione"*.

## 2. Architettura (aggiornata al 30/09/26)

         +- mc2 (hub) -------------------------------------------------+
         |  Hermes (agente principale)  -  repo ~/money               |
         |  fabbrica.py  (cron 5', flock) -> state.json / STATO.md    |
         |  A0-MC2 (Agent Zero container, task di coding)             |
         |  canale DSH (file: requests.md / results.md)               |
         +-------------+-------------------------------+-------------+
                       | Tailscale                     | HTTP (tailnet)
         +-------------v-------------+   +-------------v---------------+
         | MARCODG1                  |   | A0-PC (Windows, dietro NAT) |
         | - banco a secco (timer)   |   | - Agent Zero + cartella     |
         | - aggregator/dashboard    |   |   ponte per consegne        |
         | - Zabbix + Grafana        |   | - DSH/Stella (agente locale)|
         +---------------------------+   +-----------------------------+
                       nuvola: health/exporter

- **mc2** — hub: agente Hermes, repository `money` (ricerca + strumenti), fabbrica,
  Agent Zero containerizzato, canale DSH.
- **MARCODG1** — banco a secco in sola lettura (systemd timer), aggregator/health/dashboard,
  monitoraggio (Zabbix, Grafana), watchdog dei servizi web.
- **nuvola** — health/exporter.
- **A0-PC** — Windows dietro NAT: secondo Agent Zero + cartella-ponte; un agente locale
  (DSH/Stella) scambia consegne con l'hub.
- Rete: **Tailscale** tra i nodi; nessuna porta pubblica esposta per gli agenti.

### Flusso di lavoro (dall'idea alla promozione)

    1. candidati.json (coda delle idee, con criterio di accettazione)
    2. spec in coda_catena/ (obiettivo, griglia param., metrica primaria, criterio)
    3. brief per un aiutante (A0-MC2 / A0-PC / DSH) — "un test che fallisce senza l'implementazione"
    4. consegna -> review di Hermes (si RIESEGUONO i test) -> integrazione (commit [hermes])
    5. misura su dati reali (artefatti in prove/, pre-registrati nel REGISTRO)
    6. cancello con 8 criteri oggettivi -> promozione o archivio

## 3. Dentro un tick (`fabbrica.py`, ~260 righe)

1. `check_dsh` — nuove voci nel canale DSH -> segnala AZIONE
2. `check_handoff` — artefatti in attesa + verifica MANIFEST sha256 (provenienza byte-exact)
3. `check_p2` — runner di misura presente -> segnala (voce storica, ormai chiusa)
4. `check_a0win` / `check_a0mc2` — salute dei due Agent Zero (HTTP)
5. `check_banco` — stato del banco a secco su MARCODG1 (via ssh: timer, rc, ultimo giro)
6. `check_specgen` — prossima spec da materializzare dalla coda candidati
7. `check_jev_gate` **(nuovo dal 30/09)** — gate di qualità sulle spec tramite JEV (TypeSafe):
   4 domande tipizzate (autosufficienza, testabilità del criterio, gap principale,
   lavoro non-trading). Una valutazione **per versione** (hash del file), **fail-open**,
   verdetto riportato in `STATO.md`.
8. `check_inbox` — file in ingresso da lavorare

Output: `state.json` (macchina) + `STATO.md` (umano) + `log/fabbrica.log`. Idempotente.

## 4. Stato attuale (30/09/2026, tiro n. 321)

- **Lane attive**: Hermes = P6 (cap di concorrenza/correlazione sul portafoglio, in misura)
  | DSH = P10 (momentum cross-sezionale) | A0-MC2 = P8B (report funding/basis)
  | A0-PC = BB1 consegnato e archiviato (bootstrap a blocchi: 8/8 test, certificato di pipeline).
- **Storico recente**: P2 (vol targeting) misurata e ARCHIVIATA per costruzione; P8 e P9
  integrati; suite di test del repo: **347 verdi**; ruff pulito.
- **Banco a secco**: attivo, rc=0, solo lettura (capitale di prova).
- **Gate JEV (prima passata sulle 7 spec in coda)**: TUTTE segnalate
  "non autosufficienti" per un agente senza contesto (self-contained 0.08–0.29);
  alcune anche "accettazione debole". Segnale sistematico sul formato dei brief -> vedi Domanda 5.
- **Commit recenti del repo**: `f75d432e` (gate JEV in fabbrica), `4717427f` (BB1 archiviato),
  `dd667348` (script Composio + integrazione JEV), `fa6cf7aa` (gate JEV), `e6ff1c7f` (P2).

## 5. Guardrail già in essere (vincoli non negoziabili del progetto)

- La fabbrica NON ha percorsi che toccano capitale: nessun ordine, nessuna scrittura sugli
  exchange. Il capitale live resta fuori dalla fase attuale (ricerca/validazione).
- JEV: solo advisory (mai enforcement), fail-open su qualunque errore, chiave usata solo
  verso il suo endpoint ufficiale.
- Segreti: file `.env` separati per macchina (permessi ristretti), mai in git, mai nei log.
  Le chiavi exchange si validano SOLO con chiamate reali via libreria ufficiale (mai
  controlli di firma artigianali).
- Un solo bot per conto (lock su file), preflight saldo/minimo negoziabile, kill-switch
  e limiti giornalieri nel risk manager.

## 6. Domande per Manus (infrastruttura)

1. **Orchestrazione**: il pattern "un tick ogni 5' + una azione" regge quando le lane
   diventano 5–10? Conviene passare a una coda eventi (webhook/inbox) invece del polling?
   Trade-off pratici su un setup come questo?
2. **Resilienza**: come rendere il nastro fault-tolerant su nodi eterogenei (Linux + Windows,
   NAT/Tailscale)? Qual è il pattern minimo di heartbeat + auto-recovery che adottereste per
   OGNI componente (cron, agenti, canali file)?
3. **Osservabilità**: oltre a STATO.md + log testuali, cosa aggiungere per accorgersi di
   DEVIAZIONI SILENZIOSE (tick fermo, coda che non avanza, verdetti stantii, consegne mai
   ritirate)? Quali 3–5 metriche minime?
4. **Segreti multi-nodo**: best practice per distribuire credenziali a 4 macchine senza un
   vault pesante (oggi: .env per nodo a permessi ristretti)? Rotazione e audit?
5. **Brief per agenti autonomi**: il gate misura che le nostre spec presuppongono contesto
   umano (self-contained 0.08–0.29). Che struttura minima consigliate per un brief eseguibile
   da un agente SENZA storia? (Il nostro criterio: un test che fallisce senza
   l'implementazione.)
6. **Canale di messaggistica**: oggi DSH scambia consegne via file (requests/results.md, con
   sync tra nodi). Quando conviene passare a un bus (Redis/HTTP) e con quali guardie?
7. **Costi/benefici**: quando il polling 5' diventa il collo di bottiglia al crescere delle
   lane, e quali numeri misurereste per decidere il salto di architettura?

## 7. Riferimenti (per chi ha accesso al repo)

- `~/money/fabbrica/README.md` (regole del nastro) e `STATO.md` (stato vivo)
- `~/money/coda_catena/` (spec P1…P10), `prove/REGISTRO_ESPERIMENTI.md` (registro misure)
- Storia commit del repo `grivetto/money` (prefisso `[hermes]` per gli interventi dell'agente)

---
*Generato il 30/09/2026 dall'agente Hermes (mc2) su richiesta dell'owner, per analisi esterna.*
