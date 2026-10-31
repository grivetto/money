# 30 — Siti e domini del progetto (2026-10-31)

> Decisioni Artù 31/10/2026 (direttiva «decidiamo» dell'owner): officina dietro Access CONFERMATA;
> la landing usa public.json come fonte unica pubblica; sgrivett.ddns.net rimosso localmente
> (record No-IP esterno in decadimento; cancellazione definitiva = pannello No-IP, azione owner).

## Stato verificato 31/10 (sweep anonimo dall'edge, curl -L)

| Hostname/path | Stato misurato | Protezione |
|---|---|---|
| web.grivetto.eu/ | 200 (landing; fetch unico = denaro-api/api/public.json, CORS aperto) | pubblico |
| grivetto.eu | 301 → www.grivetto.eu (200) | non si tocca |
| denaro.grivetto.eu: /agenti, /dashboard, /sala, /squadra, /trading-live(/…), /api/console(/…), /rendita.json, /api/rendita.json, /api/sala.json, /api/live-trading.json, /scommessa.json, /api/agenti.json, /infra.json, /airdrop, /dsh.json, /api/prom | 302 → cloudflareaccess login | app Access «denaro» |
| denaro.grivetto.eu/api/dsh.json | 200 (ACAO *) | pubblico |
| denaro.grivetto.eu/api/infra.json | 200 — RESIDUO: payload aggregatore (bot paper, zero chiavi); allineare in un giro futuro SOLO dopo verifica consumatori (public.json è il sostituto filtrato già attivo) | pubblico (residuo dichiarato) |
| denaro-api.grivetto.eu/api/public.json | 200 (ACAO *) — fonte unica della landing: equity, pnl 24h/7g, banco, canary, carry, bots aggregati | pubblico |
| denaro-api.grivetto.eu/api/infra.json | 302 → login | Access (decisione 29/10, commit bcda4213: «infra.json resta dietro Access») |
| zab./grafana./ssh.grivetto.eu | 302 → login | Access (app dedicate) |
| sgrivett.ddns.net | non più mantenuto da mc2 (vedi sotto) | rimosso |

## Decisioni del 31/10 (con delega piena)

1. **/scommessa.json, /api/agenti.json, denaro-api/api/infra.json RESTANO dietro Access.**
   Motivi misurati: la landing viva (MARCODG1) è già migrata su public.json (pubblico, ACAO *): nessun
   consumatore anonimo residuo dei tre path. Riaprirli invertirebbe la decisione registrata del 29/10
   (bcda4213) e la dottrina «tre cerchi» (docs/30 del 15/10: officina solo noi). Il docs/30 del 15/10
   dichiarava quei path pubblici: era un documento stantio, non una decisione viva — si allinea il
   documento, non si riaprono le route.
2. **Landing: canonico del repo consolidato col vivo.** `deploy/web-landing/index.html` era fermo al
   fetch di infra.json (381 righe di drift): copiato il vivo (sha256 `f9ed6d6e…`), fetch unico =
   `https://denaro-api.grivetto.eu/api/public.json`. Nessuna modifica al file servito.
3. **sgrivett.ddns.net: rimozione locale completa.**
   - 4 vhost morti spostati da `/etc/nginx/sites-available/` → `/tmp/vhost_morti_20261031/`
     (sgrivett.ddns.net, mgrivett.ddns.net, mc2.myddns.me, denaro-dashboard; nessuno era in
     sites-enabled, nessun listener attivo); `nginx -t` ok.
   - `snap.noip-client.launcher.service` disabilitato (doppione del DUC che manteneva il gruppo
     No-IP «group-mc2»); `noip-duc.service` resta attivo per mc2.myddns.me (verificato: risolve).
   - Nessun consumatore vivo trovato: ponte.py/ponte_daemon.py, cloudflared config e nginx attivo
     non referenziano sgrivett; i riferimenti residui sono solo storici (legacy/README, diario, outbox).
   - Record esterno No-IP: decade (piano free ≈30gg senza aggiornamenti). Cancellazione definitiva =
     pannello No-IP (azione owner). NB: la credenziale No-IP presente nel config dello snap è emersa
     nel transcript di sessione → DA RUOTARE sul pannello No-IP; lo snap non va riattivato.

## Rollback

- Canonico landing: `deploy/web-landing/index.html.bak-preconsolidamento-20261031` (fuori repo):
  ripristino = `cp` + commit. Il file servito su MARCODG1 non è mai stato toccato.
- Vhost: `cp /tmp/vhost_morti_20261031/<f> /etc/nginx/sites-available/` + `nginx -t` (nessun impatto
  sul nginx attivo: erano spenti anche prima).
- Snap DDNS: `sudo systemctl enable --now snap.noip-client.launcher.service` (sconsigliato: credenziale esposta).
- Access app «denaro»: non modificata in questo giro (nessun cambio policy).

## Pendenza residua

- `denaro.grivetto.eu/api/infra.json` pubblico (payload aggregatore, zero chiavi): decidere l'allineamento
  (chiusura sotto Access o ritiro) solo dopo aver verificato i consumatori anonimi; il sostituto filtrato
  (public.json) è già in produzione.
