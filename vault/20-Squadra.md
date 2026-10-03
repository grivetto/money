# Squadra e canali

Aggiornata: **03/10/2026** — la squadra ora ha **8 esecutori + 1 regia, su 3 macchine**.
**Nomenclatura ufficiale (dal 03/10): `<tool>-<macchina>`** — es. `A0-win`, `opencode-omarchy`.

## Chi (foto: `money/FOTO_SQUADRA_2026-10-03.png`)

| Chi | Dove | Ruolo |
|---|---|---|
| **Hermes** | mc2 | regia: misura, integra, orchestra; riesegue e verifica ogni consegna |
| **A0-win** | PC (Windows) | operaio — Agent Zero v2.13, Gemini 2.5-flash (:50080) |
| **A0-mc2** | mc2 (container) | operaio — Agent Zero v2.13, Gemini 2.5-flash (:50080) |
| **opencode-mc2** | mc2 | operaio coding — nemotron-3-ultra free (headless --auto) |
| **opencode-omarchy** | nodo agenti (omarchy) | operaio coding — nemotron-3-ultra free (collaudato 03/10) |
| **opencode-nuvola / opencode-marcodg1** | nuvola / MARCODG1 | operaio coding free (default `ling-3.1-flash-free`) — dal 04/10, smoke PONG ok |
| **agy-omarchy** | nodo agenti (omarchy) | operaio headless — Antigravity CLI (Gemini 3.8 / Claude), allowlist |
| **DSH-mc2** | mc2 | peer — harness DeepSeek: servizio `dsh-web` :4080 + headless (collaudato 03/10) |
| **DSH-omarchy** | nodo agenti (omarchy) | peer ricerca via ssh; canale `hermes_bridge/dsh-mc2/` (P10, F2 carry) |
| **DSH-win** (ex «Stella») | PC (Windows) | peer storico; canale file `hermes_bridge/dsh/` — risponde quando ha un turno |
| **Proprietario** | — | decide, autorizza il live, dà i turni |

## Canali
- **DSH-win** (PC): bacheca `hermes_bridge/dsh/` — `requests.md` (io→DSH) ↔ `results.md` (DSH→io). Protocollo in `PROTOCOLLO_DSH.md`. Mai silenzio: ogni richiesta ha ACK/DONE/FAILED. **Turni**: li dà il proprietario.
- **DSH-omarchy** (omarchy): canale `hermes_bridge/dsh-mc2/` (requests/results + `handoff/` con MANIFEST sha256). Turni: li do io via ssh.
- **DSH-mc2** (mc2): nessun canale file — lo comando direttamente (CLI locale / web :4080).
- **Coda di ricerca**: `money/coda_catena/` — una spec per nodo, presa visibile ("STATO: PRESA_DA …" pushata subito), esiti in `money/prove/`.
- **Questo vault**: la vista umana del progetto. La verità sta nei file citati.
- **Dashboard flotta**: https://denaro.grivetto.eu

## Regole non negoziabili
- Nessun ordine reale senza autorizzazione esplicita del proprietario.
- Un solo bot per conto, mai due.
- Mai dichiarare "fatto" o "guadagnato" senza la prova (output reale, riconciliazione exchange).
- "Fatto" significa: test verdi + numeri misurati + prove scritte. Il resto è fumo.
- Un self-report non è una prova: le consegne si rieseguono nel repo canonico prima di integrarle.
