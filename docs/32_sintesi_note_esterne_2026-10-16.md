# 32 — Note esterne (Manus AI + audit): stato e adozione (2026-10-16)

Autore: hermes · Stato: sintesi di tracciabilità — ogni proposta ha un esito dichiarato.
Regola: nessuna proposta esterna entra in produzione senza spec pre-registrata, test prima dei numeri, cancello, e approvazione owner per il capitale.

## Da dove arrivano (corpus 09–16/10)
- `docs/31_proposta_miglioramenti_2026-10-16.md` — audit CI/assert → branch `improvement/ci-and-runtime-hardening` (account grivetto).
- «Analisi tecnica e proposta di trasformazione» (09/10, docx) — architettura esecuzione/riconciliazione.
- «Suggerimenti per Hermes» (09/10, docx) — 12 punti operativi.
- «MOSAICO-4» (09/10, docx) → già materializzato: `coda_catena/MOSAICO4_v1.md` + `src/money/mosaico/` + simulatore.
- «Ulteriori suggerimenti per arrivare alla redditività» (15/10, docx) — economia unitaria, no-trade filter, capacità, sub-account.
- «Architettura migliorata della Fabbrica» (15/10, docx) — job-store/lease/metriche/secrets.
- Contesto interno (non Manus): `docs/27` P0 coordinator, `docs/28` mosaico4 impl, `docs/29` audit interno, `docs/30` siti.

## Fatto (verificato 16/10)
- **Audit CI/assert**: MERGIATO (`4db0846d`) — CI fail-fast + `pip check`; 4 `assert` runtime → `RuntimeError` fail-closed; guardia AST `tests/test_no_runtime_assert.py`. Verifica: 741 test verdi anche con `-O`, ruff/compileall OK; **CI GitHub verde** (run 38969811681). `src/` ora a zero assert.
- **Punto unico di invio** (`src/money/esecuzione/invio.py` + guard `tests/esecuzione/test_punto_unico_invio.py`): esiste; `canary_carry` passa da `invia_gamba` e da `gate_pre_trade` a ogni apertura (docs/27).
- **MOSAICO-4**: spec congelata + nucleo (model/economics/signal/state_machine) + simulatore fault-injected + test. Non ancora in validazione shadow.
- **Fabbrica**: job-store SQLite con lease/retry/dedup, `STATO.md` derivato, kill-switch file, metrics, watchdog — buona parte dell'«Architettura migliorata» è già in campo.
- **8 fix audit interno 13/10** (docs/29 §6): banco a secco (Earn), criterio 8 doppio pedaggio, DSR finestra, rischio unificato, rumore spento → tutti applicati.

## Parziale / aperto (adottato nel backlog)
| Proposta | Stato | Nota |
|---|---|---|
| Coordinator con kill-switch+gate+preflight dentro | parziale | invio unico fatto; da verificare che il Coordinatore controlli `MONEY_KILL_SWITCH`, `gate_pre_trade`, `preflight` (lacuna 6 audit interno) |
| ReconciliationRun continuo con cursori (ledger = fonte di verità) | aperto | `contabilita.py` esiste ma poco cablato; aggregator parziale |
| RiskGovernor esecutivo (kill-switch come servizio testato) | aperto | oggi azioni dichiarate + alert; da rendere eseguibile con test d'incidente |
| PromotionArtifact (hash + TTL + firma) | aperto | si lega alla scala D3 e al gate live |
| SQLite WAL nel percorso live (oltre job-store) | valutare | oggi file+flock; non urgente a questa taglia |
| cost-to-edge / scheda economica per trade | adottato | P23 misura il pedaggio reale; metrica da aggiungere ai report |
| No-trade filter pre-registrato | adottato | candidato P24/P25 dopo l'onda S5 |
| Capacity gate (profondità, ADV, slippage per size) | adottato | da integrare nel gate live |
| Confronto 1 vs 3 sub-account (frammentazione) | adottato | a questa taglia NON frammentare; confronto quantitativo prima di ogni split |
| Benchmark / test di incrementalità | adottato | il metodo lo applica già (baseline dichiarate in P21) |
| Fabbrica: worker contract `/healthz` `/readyz`, secrets inventory, `.env.example` | parziale | incrementi 2–3 del doc; non bloccanti |
| Freeze nuove famiglie (max 2–3 tesi) | rispettato | onda S5 = funding + esecuzione; nessuna nuova famiglia OHLCV |

## Cosa cambia oggi
Niente nel percorso del denaro: le note confermano la direzione (carry come operazione di esecuzione market-neutral, costi reali prima di tutto, scala lenta, un solo percorso live). I due elementi nuovi adottati subito: **confronto sub-account prima di ogni frammentazione** e **cost-to-edge nei report**. Gli altri entrano nel backlog tecnico in ordine di impatto sulla sicurezza operativa.
