# Squadra e canali

| Chi | Dove | Ruolo |
|---|---|---|
| **Hermes** | mc2 | ingegnere capo: misura, integra, orchestra; il cancello decide per lui |
| **DSH** | PC Windows | scrive codice nel repo `money` (ora su **P2**); canale: `hermes_bridge/dsh/` |
| **agent-zero** | container su mc2 | workspace `site/projects/denaro-p3`; consegna P3 integrata (riscritta) da Hermes |
| **Antigravity** | PC Windows | nuovo — censimento in corso |
| **Proprietario** | — | decide, autorizza il live, dà gli OK |

## Canali
- **Bridge DSH**: `/home/sergio/hermes_bridge/dsh/` — `requests.md` (io→DSH) ↔ `results.md` (DSH→io). Protocollo in `PROTOCOLLO_DSH.md`. Mai silenzio: ogni richiesta ha un ACK/DONE/FAILED.
- **Coda di ricerca**: `money/coda_catena/` — una spec per nodo, presa visibile ("STATO: PRESA_DA …" pushata subito), esiti in `money/prove/`.
- **Questo vault**: la vista umana del progetto. La verità sta nei file citati.
- **Dashboard flotta**: https://denaro.grivetto.eu

## Regole non negoziabili
- Nessun ordine reale senza autorizzazione esplicita del proprietario.
- Un solo bot per conto, mai due.
- Mai dichiarare "fatto" o "guadagnato" senza la prova (output reale, riconciliazione exchange).
- "Fatto" significa: test verdi + numeri misurati + prove scritte. Il resto è fumo.
