# Infrastruttura — vista rapida

## Nodi
| Nodo | Ruolo | Cosa gira |
|---|---|---|
| **mc2** | regia + ricerca | Hermes, fabbrica ×100 (master 3 s), bridge/canali, Zabbix «Money», A0-mc2, **DSH-mc2 (dsh-web :4080 + headless)**, opencode, agy — **tutti in auto-start (07/10)** |
| **MARCODG1** | lato exchange + web | banco a secco (5 min, DRY-RUN), aggregatore :8912, dashboard/landing, Grafana, **canary C1 live**, worker fabbrica, opencode + agy (auto-start) |
| **nuvola** | appoggio | health, exporter, zabbix-agent + tunnel, worker fabbrica, opencode + agy (auto-start) |
| **nodo agenti** (Omarchy) | agenti | **DSH-omarchy** (headless + web UI `dsh-web` :5080) + **opencode-omarchy** (v2.0.24) + **agy-omarchy** + A0 (:50080, Docker) — **servizi auto-start, completati 08/10**; RDP riparato 14/10 (xrdp → sessione X11 su :10) |
| **win** (PC Windows, «andromeda») | agenti Windows | A0-win (:50080, Docker), **DSH-win** (`DSH-Web` :3080, Task Scheduler), opencode — accesso SSH di regia in auto (chiave ed25519) |

## URL pubblici
- Progetto: **https://denaro.grivetto.eu** — landing «il trading» (root) · **/dashboard** (flotta live, json: `/api/infra.json`) · **/agenti** · **/squadra** (la squadra dev)
- Ritirati con 301 (15/10): web.grivetto.eu → /squadra · home.grivetto.eu → / · dashboard.grivetto.eu → /dashboard
- Strumenti dietro Cloudflare Access: zab.grivetto.eu (Zabbix) · grafana.grivetto.eu (Grafana) · ssh.grivetto.eu (Browser SSH)
- Lab (solo tailnet): https://mc2.tail1b5252.ts.net (Kitchen Lab)

## Soldi e chiavi (stato al 14/10)
- OKX main: ≈1.100 € (funding + Simple Earn) — la chiave main risponde solo dall'IP di MARCODG1
- **03/10: deposito owner +1.000 EUR** → equity main ≈1.100 EUR (accredito nel funding wallet, verificato read-only: +1.000,00 esatti). Deploy carry subordinato alla review del 15/10.
- **C1 canary** (DOGE delta-neutral, size minima): aperto 01/10 su MARCODG1; nel cancello (stop ATR + kill switch); review **15/10**.
- Sub-account (mc2sub1 / marcosub1 / nuvolasub1): dust
- **Banco a secco**: attivo su MARCODG1 — ciclo automatico ogni 5 min, solo DRY-RUN, tripwire a 100,00 €

## Esecuzione (pronta, ma a porta chiusa)
Nel repo `money` vive `src/money/esecuzione/`: preflight, sizing, idempotenza, dry-run di default.
Il live richiede **tre chiavi in fila**: variabile `MONEY_LIVE_ARMED=1` + file di promozione
dal cancello + preflight verde. Mai stato raggiunto — e va bene così finché non c'è un edge promosso.
