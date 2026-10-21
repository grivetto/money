# 30 — Siti e domini del progetto (2026-10-15)

> Direttiva owner 15/10/2026: brand pubblico **«Denaro»** (Money resta il nome tecnico di sistema);
> la pagina della squadra **assorbita in /squadra**; doppioni legacy ritirati; zero storytelling. [hermes]

## Il disegno in tre cerchi

1. **VETRINA — il mondo.** Tutto il pubblico vive su `web.grivetto.eu` (landing principale, dal 21/10), col brand Denaro; le route applicative restano su `denaro.grivetto.eu`. Regola: dalla vetrina si linka solo vetrina (più GitHub); niente numeri non riconciliati.
2. **OFFICINA — solo noi.** Strumenti di lavoro sempre dietro **Cloudflare Access**:
   Zabbix, Grafana, Browser SSH. Mai linkati dalla vetrina.
3. **LABORATORIO — solo tailnet.** Il Kitchen Lab (`mc2.tail1b5252.ts.net`) è il backstage di mc2:
   invisibile al pubblico, da lì si raggiunge tutto.

## Mappa (verificata 2026-10-15)

| Hostname | Ruolo | Origin | Protezione | Stato |
|---|---|---|---|---|
| grivetto.eu | sito personale owner | — | **non si tocca** (301 → www.grivetto.eu) | ✓ |
| denaro.grivetto.eu | vetrina: `/` landing · `/dashboard` · `/agenti` · `/squadra` · `/scommessa.json` · `/api/infra.json` | **MARCODG1** `money-dashboard-marcodg1` (127.0.0.1:8913, dir `/home/marco/money/ops/dashboard`) | pubblico | 200 ✓ |
| denaro-api.grivetto.eu | feed JSON dell'aggregatore | MARCODG1 `:8912` | pubblico | 200 ✓ |
| web.grivetto.eu | **vetrina principale** (21/10) → landing Denaro, link a dashboard/agenti/squadra/scommessa/infra | MARCODG1 `python -m http.server 8914` in `/home/marco/denaro/landing` (stub precedente: `index.stub-20261015.html`) | pubblico | 200 ✓ (origin; 301 CF da rimuovere) |
| home.grivetto.eu | **ritirato** → 301 a denaro.grivetto.eu/ | nginx mc2 `:80` (vhost `grivetto-legacy-redirect.conf`) | pubblico | 301 ✓ |
| dashboard.grivetto.eu | **ritirato** → 301 a /dashboard | idem (tunnel cloudflared-home ripuntato a `:80`) | pubblico | 301 ✓ |
| zab.grivetto.eu | Zabbix | MARCODG1 → reverse tunnel → mc2 `:1080` | **Cloudflare Access** (app «zab») | ✓ |
| grafana.grivetto.eu | Grafana | MARCODG1 `money-grafana` `:3000` | **Cloudflare Access** (app «grafana», creata 15/10) | ✓ |
| ssh.grivetto.eu | Browser SSH | tunnel mc2 → sshd | Cloudflare Access (app «ssh») | ✓ |
| mc2.tail1b5252.ts.net | Kitchen Lab (home di mc2) | nginx mc2 (cert TLS tailscale) | **solo tailnet** (firewall blocca il pubblico) | ✓ |
| freellmapi.grivetto.eu | router LLM (extra-progetto) | mc2 `:3001` | API con chiave (UI pubblica) | decisione aperta |

## Dove vivono i file (deploy)

- **Dashboard/landing/squadra/agenti**: repo `ops/dashboard/` — serviti da **mc2** (`:8913`, copia speculare) e da **MARCODG1** (`:8913`, **il pubblico**).
  Deploy di una modifica: commit+push da mc2 → `ssh MARCODG1 'cd /home/marco/money && git pull --ff-only'` → `sudo systemctl restart money-dashboard-marcodg1` (per modifiche a `serve_dashboard.py`; gli HTML si rileggono a ogni richiesta).
- **Kitchen Lab**: sorgente `deploy/kitchen-lab/` → `sudo cp deploy/kitchen-lab/index.html /var/www/kitchen-lab/index.html` (mc2); solo tailnet.
- **Kit di ripristino**: `deploy/reinstall/landing/` (contiene anche la pagina squadra pre-assorbimento, ora ridondante).
- **Stub web**: `/home/marco/denaro/landing/` su MARCODG1 (fuori repo).
- **Dati vivi** (`scommessa.json`, `agenti.json`): aggiornati da cron su mc2 e copiati su MARCODG1 via `scp` (unico flusso mc2→MARCODG1).

## Cambi del 21/10

1. **web.grivetto.eu → vetrina principale** — nuova landing Denaro su MARCODG1 `:8914` (`/home/marco/denaro/landing/index.html`, sha256 `51e3188c…f71d`), dati live da `denaro-api.grivetto.eu/api/infra.json`; stub precedente salvato come `index.stub-20261015.html`.
   Rollback origin: ripristinare `index.stub-20261015.html` su MARCODG1 e riavviare il servizio `:8914`.
   Pendenza: rimuovere la Redirect Rule Cloudflare «[15/10/26] web.grivetto.eu legacy» (zona `cb5723e72edb4382bdd66c9cc4916685`, Rules → Redirect Rules) — senza dashboard CF resta 301.

## Cambi del 15/10 (con rollback)

1. **`/squadra` su denaro** — route `SQUADRA_ROUTES` + `squadra.html` + asset in `serve_dashboard.py`.
   Rollback: revert del commit + restart dei due servizi.
2. **web.grivetto.eu → 301** — Redirect Rule Cloudflare «[15/10/26] web.grivetto.eu legacy» (zona `cb5723e72edb4382bdd66c9cc4916685`, entrypoint dynamic-redirect) + stub origin di fallback.
   Rollback: rimuovere la regola dalla dashboard CF (Rules → Redirect Rules).
3. **home./dashboard. → 301** — vhost nginx `sites-enabled/grivetto-legacy-redirect.conf` (mc2) + tunnel `cloudflared-home` (config: `~/.cloudflared/config.yml`, backup `.bak-20261015-prelegacy`).
   Rollback: ripristinare il backup, rimuovere il vhost, `nginx -t && systemctl reload nginx`, `systemctl restart cloudflared-home`.
4. **Grafana → Access** — app «grafana» (id `06831d34-8000-4f08-ab78-f1c35b3e2fe2`, account CF `c44a6daf8a45000dab982a0dc8f94375`), policy allow email: sergio.grivetto@gmail.com + sergio@grivetto.eu.
   Rollback: eliminare l'app in Zero Trust → Access → Applications.

## Pendenze

- Censimento dei vhost nginx morti su mc2 (`sgrivett.ddns.net` :8899, `mgrivett.ddns.net` :8080, `mc2.myddns.me`, `denaro-dashboard` :8901 → 502) → spegnere ciò che è morto.
- Decidere l'accesso di `freellmapi` (se non serve pubblico: dietro Access o tailnet).
- (Opzionale, futuro) analytics privacy-friendly per la vetrina.
