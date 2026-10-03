# Squadra e canali

Aggiornata: **03/10/2026** — la squadra ora ha **8 esecutori + 1 regia, su 3 macchine**.

## Chi (foto: `money/FOTO_SQUADRA_2026-10-03.png`)

| Chi | Dove | Ruolo |
|---|---|---|
| **Hermes** | mc2 | ingegnere capo: misura, integra, orchestra; riesegue e verifica ogni consegna |
| **DSH (mc2)** | mc2 | esecutore di casa — harness DeepSeek: servizio `dsh-web` :3080 + headless CLI (collaudato 03/10) |
| **DSH peer** | nodo agenti (omarchy) | ricerca via ssh; canale `hermes_bridge/dsh-mc2/` (P10, F2 carry) |
| **DSH «Stella»** | PC del proprietario | peer di ricerca; canale file `hermes_bridge/dsh/` — risponde quando ha un turno |
| **A0-MC2 · A0-PC** | mc2 + PC | operai Agent Zero (task async, consegne in handoff) — Gemini 2.5 |
| **opencode ×2** | mc2 + nodo agenti | coding free (nemotron-3-ultra), collaudati 03/10 |
| **agy (Antigravity)** | nodo agenti | esecutore headless (Gemini 3.8 / Claude) — allowlist |
| **Proprietario** | — | decide, autorizza il live, dà i turni a Stella |

## Canali
- **DSH «Stella»** (PC): bacheca `hermes_bridge/dsh/` — `requests.md` (io→DSH) ↔ `results.md` (DSH→io). Protocollo in `PROTOCOLLO_DSH.md`. Mai silenzio: ogni richiesta ha ACK/DONE/FAILED. **Turni**: li dà il proprietario.
- **DSH peer** (omarchy): canale `hermes_bridge/dsh-mc2/` (requests/results + `handoff/` con MANIFEST sha256). Turni: li do io via ssh.
- **DSH (mc2)**: nessun canale file — lo comando direttamente (CLI locale / web :3080).
- **Coda di ricerca**: `money/coda_catena/` — una spec per nodo, presa visibile ("STATO: PRESA_DA …" pushata subito), esiti in `money/prove/`.
- **Questo vault**: la vista umana del progetto. La verità sta nei file citati.
- **Dashboard flotta**: https://denaro.grivetto.eu

## Regole non negoziabili
- Nessun ordine reale senza autorizzazione esplicita del proprietario.
- Un solo bot per conto, mai due.
- Mai dichiarare "fatto" o "guadagnato" senza la prova (output reale, riconciliazione exchange).
- "Fatto" significa: test verdi + numeri misurati + prove scritte. Il resto è fumo.
- Un self-report non è una prova: le consegne si rieseguono nel repo canonico prima di integrarle.
