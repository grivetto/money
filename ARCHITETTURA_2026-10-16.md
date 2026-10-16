# Architettura del progetto Denaro / Money

**16/10/2026, sera · stato verificato live · nessun segreto in questo documento**
(Generata da Hermes su mc2. Versione visual: `FOTO_SISTEMA_2026-10-16.png` · squadra: `FOTO_SQUADRA_2026-10-16.png`.)

---

## 0. Un colpo d'occhio

- **Un direttore lavori**: Hermes (mc2) — misura, codice, review, dispatch, fabbrica, git.
- **16 operai su 5 macchine**, tutti in auto-start systemd: A0 ×3 (mc2/omarchy/win) ·
  DSH ×3 · opencode ×4 · agy ×4 · Hermes ×2. Pannello live: `denaro.grivetto.eu/agenti`.
- **Il capitale**: ≈ **1.096 €** su OKX EEA, riconciliato ogni 5 minuti dal banco a secco
  (`PASS`, riconciliazione quadra, ordini aperti 0, chiave read-only). Comparti:
  trading ≈368 € · funding ≈194 € · Simple Earn ≈534 €.
- **Il trading è tutto paper**, tranne **due esperimenti reali a taglia minima**: canary C1
  (carry DOGE delta-neutral, dal 01/10, review 14 giorni **PASS**) e carry multi-coppia
  DOT+ADA (dal 15/10). Nessun altro bot live; nessun ordine senza autorizzazione del proprietario.
- **Il metodo**: idea → spec pre-registrata → operaio → review → misura → cancello (8 criteri)
  → paper → canary → live minima → scala. Zero promozioni forzate.
- **L'affidabilità**: alert Telegram (digest giornaliero con Δ scomposto *cambio vs resto* +
  soglia equity), watchdog, heartbeat, hardening delle porte. Lezione fondativa: *«zero silenzi»
  — un componente giù senza alert è un incidente*.

## 1. I nodi

| Nodo | Dove | Ruolo |
|---|---|---|
| **mc2** | casa (fisica, LAN + Tailscale) | **l'hub**: regia Hermes, fabbrica ×100, Zabbix, banco/alert, snapshot, dashboard interna |
| **MARCODG1** | VPS (Tailscale + IP whitelisted OKX) | **trading + web**: aggregatore master, dashboard pubblica, landing, banco a secco, watchdog, ricerca |
| **nuvola** | VPS (Tailscale) | **monitoraggio**: health, exporter, Zabbix agent (tunnel inverso), nodo paper |
| **omarchy** | casa (desktop, LAN) | **nodo agenti**: DSH, opencode, agy, A0; RDP per accesso umano |
| **win** | PC Windows | **operai extra**: A0-win, DSH-win (dietro NAT, raggiunto dai servizi) |

Rete: **Tailscale** tra i nodi remoti; LAN diretta mc2↔omarchy; `ssh.grivetto.eu` = tunnel
Cloudflare verso mc2. I servizi interni stanno su **loopback** e si raggiungono via tunnel.

## 2. I servizi (casa unica: repo `money`)

### mc2 — l'hub
- `hermes-gateway` (user unit) — la regia.
- **Fabbrica ×100**: `fabbrica-tick.timer` (user), worker, watchdog ogni minuto.
- Stack money: `money-health-mc2` :8911 · `money-aggregator-mc2` :8912 · `money-dashboard-mc2` :8913.
- `denaro-feeder-mc2` (canale dati ZeroMQ) · `denaro-exporter-mc2` :9100 (Prometheus).
- **Zabbix** (docker: server/web/db) + agent + tunnel inverso con MARCODG1.
- Cron: snapshot infra 1', dev_platform 1', agenti 1', watch_alerts 5–30', cruscotto 5',
  funding_watch 1h, raccolta funding 4h, scommessa 10', gen_dashboard 5'.
- `denaro-node-mc2` (user, **paper** su 7 asset) · **xrdp** (RDP LAN/Tailscale) ·
  hardening porte `MC2HARD` (solo LAN/Tailscale; internet chiuso).

### MARCODG1 — trading + web
- `money-aggregator-marcodg1` :8912 — **il master**: legge i nodi via ssh, serve `/api/infra.json`.
- `money-dashboard-marcodg1` :8913 · `money-landing-marcodg1` :8914 · `money-health-marcodg1` :8911.
- `money-banco-secco` (5') — la riconciliazione contabile read-only (trading+funding+Earn).
- `money-watchdog-marcodg1` (2') — auto-recovery dello stack web.
- `fabbrica-worker.timer` · `money-ricerca-*` (raccolta/scansione edge).
- Canary status (10') · **Prometheus + Grafana** (dietro Cloudflare Access) · exporter · cloudflared · zabbix-agent.

### nuvola
- `denaro-node-nuvola-trade` (**paper**, 6 asset) · `money-health-nuvola` :8911 · `denaro-exporter` · zabbix-agent.

### omarchy / win — il nodo agenti
- omarchy: DSH :5080 · opencode :49374 · agy (daemon) · A0 :50080 — systemd auto-start.
- win: A0-win · DSH-win :3080.

## 3. Il percorso del denaro

- **Casa**: OKX **EEA** (`eea.okx.com`: hostname obbligatorio per la compliance).
- **Conti**: `main` (tutto il capitale) + 3 sub-account storici (dust). **Un bot per conto** —
  mai due bot sullo stesso conto.
- **Esecuzione** (solo su autorizzazione): preflight → gate pre-trade con stop → ordini
  **LIMIT** (mai market) → `clOrdId` idempotenti → journal → riconciliazione.
- **Le chiavi**: vivono solo nei `secrets/` dei nodi autorizzati (IP-bound; la main opera da
  MARCODG1/nuvola). Importi e permessi minimi; mai in git/log/chat.
- **Contabilità**: il settore si legge su **tre comparti** — trading, funding/cash, Simple Earn
  (lezione 11/10: un comparto non letto = un falso crollo). Banchi e aggregatori usano una
  chiave **read-only**; ogni numero esposto porta la sua fonte.
- **Valuta**: il capitale è in **$ (USDC/Earn)** → il totale in € oscilla col cambio;
  il digest giornaliero scompone ogni movimento in *cambio vs resto* (decisione owner 16/10:
  si resta in $, con visibilità piena).

## 4. Il percorso dei dati e del web

- L'**aggregatore master** (MARCODG1) raccoglie: bot health, saldi per conto, nodi via ssh
  (mc2 via tunnel inverso `:2222`), servizi, canary, carry, ricerca. Serve `/api/infra.json`
  (snapshot rigenerato ogni minuto).
- **Pubblico**: `denaro.grivetto.eu` = dashboard + `/squadra` + `/agenti` (Cloudflare);
  `web.` / `home.` / `dashboard.grivetto.eu` = 301 al sito nuovo. Zabbix e Grafana dietro
  **Cloudflare Access**. Tutto servito da MARCODG1 (mc2 ha le copie speculari).
- **Gli alert** leggono lo stesso payload: bots (regressioni con rientro), equity (crollo,
  letture incomplete, **soglia 1.090 €** con motivo), flotta (fleet-integrity), carry (canary),
  check locale (container/unit/disco). Audit di ogni invio in `~/.denaro_alerts/sent.log`.

## 5. Il metodo (catena di produzione)

`coda_catena/` (spec pre-registrate) → **fabbrica** (operaio grande) / agenti → review Hermes
(test rieseguiti nel repo) → `prove/` (artefatti congelati) → **cancello a 8 criteri** (DSR)
→ promossa | archiviata → **banco a secco** → **canary** → **live a taglia minima** → scala.

Regole: *test prima dei numeri; il cancello decide; fail-closed*; niente scorciatoie sul risk
manager; le idee nuove nascono **pre-registrate** (ipotesi, criteri e costi dichiarati PRIMA dei numeri).

## 6. Ricerca: dove siamo (16/10/2026)

- **Filone esplorativo chiuso**: 6 arene × 59 simboli su 5+ anni → **0 edge validato**;
  microstruttura, on-chain/sentiment, multi-timeframe bocciati; S4 «caccia continua» fermata (esaurita).
- **Vivo**: il **carry/funding** regíme-gated — C1 canary (review 14gg PASS, funding al 117,9%
  dell'atteso) + carry multi-coppia DOT+ADA; sorveglianza X-Perp con soglie.
- **Gate di promozione**: DD ≤ 25% · t ≥ 1,65 · expectancy ≥ 3× pedaggio. Poi dry-run → banco → live minima.

## 7. Affidabilità e sicurezza

- **Zero silenzi**: ogni daemon critico ha heartbeat, restart e allarme (watchdog fabbrica 1' ·
  dashboard 2' · fleet-integrity · canary 10' · Zabbix triggers «equity crollo» e «Operaio giù»).
- **Alert Telegram** `@DenaroAlertBot`: check 5' · bots 10' · equity 10' · carry 15' · flotta 30' ·
  **digest 9:00** (capitale, Δ24h/Δ7g con scomposizione, flotta, canary). Anti-spam per chiave + spool di retry.
- **Sicurezza**: un bot per conto · chiusure d'emergenza kill-switch a file · hardening porte
  (RDP/SSH solo LAN/Tailscale) · segreti solo nei `secrets/` (600) · niente withdraw dai processi automatici.
- **Backup e ripristino**: backup giornalieri dello stato (db/segreti), kit di reinstallazione in
  `deploy/reinstall/`, unit e cron versionati («tutto in git» si scopre solo al momento del bisogno).

## 8. Economia (vincolo di realtà)

Capitale ≈1.096 €; costi noti ≈9 €/mese (VPS) + ≈22 €/mese (AI Pro). Con questo capitale il
progetto è **strutturalmente in perdita**: pareggio ≈2,6 k€ col solo costo VPS, ~6–9 k€ con
tutti i costi. La leva dominante è il **capitale** (o il taglio costi), non la strategia —
nessuna scala senza evidenza out-of-sample.

## 9. Invarianti (non negoziabili)

1. Mai dichiarare guadagni non riconciliati con l'exchange.
2. Mai aggirare risk manager, kill switch o limiti — nemmeno «per un test».
3. Mai segreti in git, log o chat.
4. Mai due bot sullo stesso conto.
5. Mai operare su chiavi morte o simboli disabilitati.
6. Un passo per volta, backup e rollback pronti; prima paper, poi live minima.

## Riferimenti

`README.md` / `README.it.md` (storia e metodo) · `SCHEDA_PROGETTO.md` (quadro d'insieme) ·
`docs/` (documentazione 01–24) · `vault/` (Sala di Controllo + Diario, git) ·
`prove/REGISTRO_ESPERIMENTI.md` (verdetti) · `coda_catena/CONCLUSE.md` · `fabbrica/STATO.md`.
