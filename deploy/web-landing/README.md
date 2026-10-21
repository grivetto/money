# web-landing — vetrina principale web.grivetto.eu

Landing di primo livello del progetto **Denaro** (brand pubblico), servita da
`web.grivetto.eu`. Le pagine operative restano su `denaro.grivetto.eu`
(dashboard, agenti, squadra, scommessa.json, api/infra.json) e sono raggiungibili
dalla landing.

## Origin

- Host: **MARCODG1**, unit `money-landing-marcodg1`
  (`python3 -m http.server 8914 --bind 127.0.0.1 --directory /home/marco/denaro/landing`).
- Tunnel Cloudflare «denaro-marcodg1»: hostname `web.grivetto.eu` → `http://127.0.0.1:8914`.
- File statici: ogni richiesta rilegge dal disco — **nessun restart** dopo il deploy.

## Dipendenza dati live

La landing fa fetch di `https://denaro-api.grivetto.eu/api/infra.json`
(CORS `*`, feed aggregatore MARCODG1 :8912) e mostra: capitale riconciliato
OKX main, canary DOGE, carry DOT/ADA, bot paper/live, banco PASS.
Senza rete o feed giù: chips «dati live non disponibili», pagina comunque usabile.
Nessun cookie, nessun tracking, nessuno script esterno oltre ai font Google.

## Deploy (da mc2)

```bash
ssh MARCODG1 'cd /home/marco/money && git pull --ff-only'
ssh MARCODG1 'cp /home/marco/money/deploy/web-landing/index.html \
              /home/marco/money/deploy/web-landing/trading-2026-10-08.jpg \
              /home/marco/denaro/landing/'
# verifica: sha atteso in testa al commit + HTTP 200 sul titolo giusto
ssh MARCODG1 'sha256sum /home/marco/denaro/landing/index.html && \
              curl -s http://127.0.0.1:8914/ | grep -o "<title>[^<]*</title>"'
```

## Rollback

1. Stub pre-21/10 (301 via meta refresh verso denaro/squadra):
   `cp /home/marco/denaro/landing/index.stub-20261015.html \
       /home/marco/denaro/landing/index.html`
2. In alternativa riattivare la Redirect Rule Cloudflare
   «[15/10/26] web.grivetto.eu legacy» (zona `cb5723e72edb4382bdd66c9cc4916685`).

## Nota Cloudflare

Finché esiste la Redirect Rule «[15/10/26] web.grivetto.eu legacy», il 301 scatta
prima dell'origin e la landing non si vede. La regola va rimossa dalla dashboard CF
(Rules → Redirect Rules). Mappa completa in `docs/30_siti_e_domini_2026-10-15.md`.
