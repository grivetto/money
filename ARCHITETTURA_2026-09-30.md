# Foto dell'architettura — progetto Denaro / Money

**30/09/2026, sera · fotografia dello stato vivo + proposta di "sistemata definitiva"**
(Generata da Hermes su mc2. Da usare per la revisione con l'owner e come base del riordino.)

---

## 0. Un colpo d'occhio

- **Un direttore lavori**: Hermes (mc2) — misura, scrive codice, review, dispatch, fabbrica, git.
- **Due operai di coding**: A0-MC2 (container su mc2) e A0-PC (Windows, dietro NAT) — eseguono
  brief, consegnano artefatti.
- **Un peer di pari livello**: DSH "Stella" (sessione Windows) — consegne verificate byte-exact
  (P2 integrata), canale file `requests.md ↔ results.md`.
- **Un giudice advisory**: JEV (TypeSafe) — gate qualità spec attivo nella fabbrica; mai enforcement.
- **Una piattaforma tool**: Composio — JEV connesso, CLI installata, script nel repo.
- **Il nastro**: la "fabbrica" su mc2 — un tick ogni 5', UNA azione per tick, stato in `STATO.md`.
- **Il trading**: NON attivo. Banco a secco in sola lettura su MARCODG1; nodi in piedi ma a vuoto;
  capitale di prova minimo; il deposito da 1.000€ arriva quando il software è stabile.
- **La logica**: idea → spec → test → cancello → promozione/archivio. *"Test prima dei numeri;
  il cancello decide; produzione solo su promozione."*

## 1. Chi c'è, dove, e cosa fa

| Entità | Dove | Ruolo | Stato 30/09 |
|---|---|---|---|
| **Hermes** | mc2 | Direttore lavori: misure, codice, review, dispatch, fabbrica, unico che pusha su git | Attivo |
| **A0-MC2** | mc2 (container `/a0`) | Operaio coding #1: brief → modulo+test+note nel workspace | P8B in corso (P8/P9 già integrati) |
| **A0-PC** | Windows (tailnet) | Operaio coding #2: brief → consegna nella cartella-ponte | BB1 consegnato e archiviato (8/8 test) |
| **DSH (Stella)** | sessione Windows | Peer/collaudatore: consegne di pari livello via canale file | P10 assegnata; 2 risposte da dare a loro |
| **JEV (TypeSafe)** | API + Composio | Giudice advisory: gate qualità spec (fabbrica), canale Composio, API diretta | 7 spec valutate; gate AUTOMATICO dal 30/09 |
| **Composio** | cloud + mc2 (CLI) | Piattaforma tool esterni (1500+ app) | JEV connesso (ACTIVE); CLI su mc2 (login umano pendente) |
| **Fabbrica** | mc2 (`~/money/fabbrica/`) | Il nastro: cron 5', stato, gate, coda candidati | Tiro n. 327, gate JEV attivo, banco rc=0 |
| **Banco a secco** | MARCODG1 | Verifica end-to-end in sola lettura (timer) | Passa, rc=0, nessun ordine |
| **Monitoring** | MARCODG1+nuvola+mc2 | Zabbix, Grafana, Prometheus, watchdog, dashboard/landing | Attivo (come da runbook) |

## 2. Mappa

```
                     ┌───────────────────────── MC2 — hub ─────────────────────────┐
                     │ Hermes (direttore lavori)                                   │
                     │  · fabbrica.py (cron 5') → STATO.md · gate JEV · lint spec  │
                     │  · repo: money (ricerca) · alpha-omega-trading (runtime)    │
                     │  · servizi: aggregator :8912 · dashboard :8913 · health     │
                     │    :8911 · feeder · exporter · node-mc2 (mc2sub1, idle)     │
                     │  · A0-MC2 (Agent Zero container)                            │
                     │  · canale DSH: requests.md ↔ results.md                     │
                     └──────┬──────────────────────────────────────┬───────────────┘
                            │ tailscale                            │ http (tailnet)
              ┌─────────────▼───────────────┐         ┌────────────▼─────────────────────┐
              │ MARCODG1                    │         │ A0-PC (Windows, dietro NAT)      │
              │  · banco a secco (timer)    │         │  · Agent Zero (operaio #2)       │
              │  · aggregator/dashboard/    │         │  · cartella-ponte consegne       │
              │    health · Prometheus ·    │         │  · DSH/Stella (peer, file-based) │
              │    Grafana · Zabbix ·       │         └──────────────────────────────────┘
              │    landing · watchdog       │
              └──────────────┬──────────────┘
                             │
                 nuvola: health · exporter · node-trade (idle)

   Giudice advisory: JEV (TypeSafe) → api.typesafe.ai (diretto) · Composio · gate in fabbrica
   Tool esterni:     Composio → REST v3.1 (script money/scripts/composio_tool.py)
```

### Il flusso di lavoro (la "logica del progetto")

```
IDEA → candidati.json → [spec in coda_catena + registro esperimenti]
     → brief-contratto → OPERAIO (A0-MC2 | A0-PC | DSH)
     → consegna (workspace/ponte + manifest sha256)
     → REVIEW di Hermes (test rieseguiti sul serio) → integrazione (commit [hermes], push via mc2)
     → MISURA (artefatti congelati in prove/) → CANCELLO (8 criteri oggettivi)
     → promossa | archiviata  →  (solo dopo) banco a secco → canary → live a taglia minima
```

## 3. La logica del progetto (in breve)

- **Obiettivo**: trading crypto automatico profittevole e sostenibile, capitale-agnostico
  (da piccoli tagli in su). LIVE solo a software stabile e checklist verde.
- **Metodo**: misura prima di toccare; una modifica alla volta; paper/dry-run prima; backtest
  onesti (fee+slippage, walk-forward); verifica sempre contro l'exchange; report brevi e verificabili.
- **Governance M1**: misure pre-registrate nel REGISTRO (n. varianti dichiarato prima del primo
  numero); il cancello decide (8 criteri); il miglior risultato non si anticipa; promozione =
  mai automatica.
- **Rischio** (mandato): risk/trade 2%, stop giornaliero −3%, DD massimo −10%; un bot per conto;
  kill-switch; preflight saldi. Proposta di allineamento cancello↔mandato (DD 25% diagnostico,
  promozione a DD ≤10% al sizing di deploy) — con le approvazioni ricevute va formalizzata.
- **Stato della ricerca**: P2 archiviata (vol targeting non doma il DD di portafoglio);
  prossimo numero = **P6** (cap concorrenza/correlazione); funding/basis in raccolta (P4/P8).

## 4. Stato vivo (30/09 sera, verificato)

- **Repo money**: suite **352 verdi**, ruff pulito; ultimi commit: `be0f9496` (lint spec + piano
  hardening), `a08754f1` (brief fabbrica per Manus), `f75d432e` (gate JEV in fabbrica),
  `4717427f` (BB1 archiviato), `dd667348` (Composio/JEV).
- **Fabbrica**: tiro 327 (cron regolare), A0-PC/A0-MC2 HTTP 200, banco rc=0, gate JEV su 7 spec.
- **Lane**: Hermes=P6 (misura) · DSH=P10 · A0-MC2=P8B · A0-PC=libero.
- **Trading**: nessun ordine reale (policy). Nodo mc2sub1 su ma in skip (equity non riconciliata:
  tema wallet funding↔trading aperto); banco a secco OK in sola lettura.
- **Composio**: chiave progetto operativa (money/.env), JEV ACTIVE, prime chiamate reali fatte.

## 5. Fragilità e frammentazioni (foto onesta)

1. **Repo multipli**: `alpha-omega-trading` (628M, runtime+deploy) · `denaro` e `denaro2` (due
   checkout dello stesso repo, branch denaro-v3) · `money` (ricerca). Ruoli e percorsi da fissare
   (direttiva owner: "uniformare sotto denaro, no denaro2") — rischio drift codice↔servizi.
2. **Canali di consegna multipli** (HTTP A0, file DSH, ponte A0↔DSH, workspace A0-MC2) senza un
   protocollo unico: serve formato comune (manifest + sha256 + marker READY + claim atomica).
   DSH segnala da sé che i warning silenziosi (base64) sono "il modo in cui nasce un guasto".
3. **Fabbrica ancora leggera**: niente job-store/lease/dedup; un tick rotto = nastro fermo senza
   métriche; il piano di hardening (Manus) è pronto — incremento 1 da eseguire.
4. **Brief eterogenei**: lint 1-2/7 blocchi-contratto, JEV 0.08–0.29 di autosufficienza — va
   adottato il template-contratto per OGNI dispatch (vale anche per DSH).
5. **Segreti sparsi**: `.env` per nodo; regola "zero secret by default" per A0-PC/DSH da attuare;
   inventario/rotazione da tracciare.
6. **JEV a tre canali**: regole d'uso da fissare in un punto solo (chi chiama, quando, advisory).
7. **Piccoli debiti**: `fleet-integrity.service` rotto; lane `stella/pump` morta da decommissionare;
   ponte A0↔DSH mai collaudato end-to-end; STATO.md con qualche riga statica stantia.

## 6. La "sistemata definitiva" — proposta in 3 fasi

**FASE A — riordino immediato (in autonomia, subito)**
- A1. **Protocollo unico d'ufficio** (`money/docs/PROTOCOLLO_FABBRICA.md`): ruoli, contratto-task
  (template Manus), canale consegne unico, registro dispatch. Vale per A0-MC2, A0-PC, DSH.
- A2. **Fabbrica Incremento 1** (piano `fabbrica/PIANO_HARDENING_2026-09-30.md`): job-store
  SQLite/lease/dedup → metriche minime → kill-switch → STATO derivato → handoff atomico.
- A3. **Chiusure**: risposta a DSH (P6 + ponte), decommissione lane morte, fix fleet-integrity,
  pulizia righe stantie in STATO.

**FASE B — consolidamento (questa settimana di lavoro)**
- B1. **Unificazione repo per ruolo** (ricerca=money; runtime=alpha-omega-trading/"denaro";
  deprecare denaro2) CON check delle dipendenze dei servizi prima di muovere qualsiasi path.
- B2. **Audit segreti**: zero-secret per A0-PC/DSH; inventario (owner, scopo, nodi, scadenza);
  separazione credenziali exchange vs ricerca/monitoring.
- B3. **Un canale di consegna** (protocollo file atomico; eventuale bus solo a soglia misurata).

**FASE C — verso il live (quando ricerca e software lo permettono)**
- C1. Chiudere **P6** (+ P7 soglia capitale/leva); decidere investibilità lane trend; funding in
  raccolta fino a copertura minima.
- C2. **Candele di avvicinamento**: banco → canary a taglia minima su UN conto, checklist
  promozione M1 verde; risk mandate formalizzato (con approvazioni ricevute).
- C3. **1.000€** e prime operazioni reali SOLO a checklist verde; report giornaliero riconciliato.

## 7. Invarianti (non si toccano)

- Nessun ordine reale senza autorizzazione; mai aggirare risk manager/kill-switch/limiti.
- Fail-closed su integrazione/test/manifest; fail-open SOLO per il parere JEV advisory.
- Un bot per conto; un solo scrittore git per repo (push via mc2).
- Segreti mai in git, log, chat, canali di consegna; misure mai senza pre-registrazione;
  niente numeri non riconciliati con l'exchange.

---
*Fine foto. Prossimo passo: revisione con l'owner → esecuzione Fase A in autonomia.*
