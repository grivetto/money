# legacy/ — QUARANTENA

> **Stato: NON ESEGUIBILE, NON RIPARABILE PER RIUSO. Solo memoria storica.**
> Creato il 2026-09-28 dall'audit radicale (`docs/11`). Non si cancella: la storia di cosa e'
> stato provato vale piu' del codice che l'ha provata. Ma non si esegue, e non si importa.

## Perche' e' in quarantena

Questi bot hanno bruciato capitale per **aritmetica**, non per sfortuna. Il conto che chiude il
caso, misurato dal progetto stesso: la griglia su 10 EUR di nozionale con spaziatura 0,25%
incassava **0,025 EUR lordi** per ciclo e pagava **0,055 EUR di commissioni**. Netto
**-0,030 EUR per ciclo**, centinaia di cicli al giorno, su tre macchine.

Accanto all'aritmetica, l'audit ha trovato questi fatti verificati:

| Difetto | Prova |
| :--- | :--- |
| Il ledger non e' mai stato scritto | `denaro_core.py:77` logga invece di persistere; `trades.db` = **0 righe in 4 tabelle** |
| Il PnL era una costante scritta a mano | `momentum_scalper.py:186,195`: `profit = invested * PROFIT_TARGET`; fee mai sottratte |
| Payoff invertito con fee ignorate | `scalper_v2.py:17-18`: TP 0,5% vs SL 0,8% |
| Filtro anti-rumore disattivato | `momentum_scalper.py:33`: `MIN_VOLUME_MULT = 0.0` (condizione sempre vera) |
| Martingala nel senso che perde | `denaro_strategies.py:109-113`, fattore 1,12-1,15 |
| Correlazione calcolata e mai letta | `correlation_guard.py:25` scrive `correlation_state.json`; **nessun lettore** |
| Risk manager con input inesistente | `risk_manager.py:15` legge `exposure.json`; **nessun writer** |
| Kill switch che non puo' scattare | `tools/kill_switch.py:16` definisce `DRAWDOWN_THRESHOLD` e non lo confronta mai |
| Nessuno stop exchange-side | grep `stopPrice` / `STOP_MARKET` in `legacy/`: **zero occorrenze** |
| Controllo remoto non autenticato | `orchestrator.py:387` su `0.0.0.0:8899`, rotte di start/stop |
| Stato condiviso fra due bot | `momentum_scalper.py:17` e `momentum_scalper_sol.py:17`: stessa riga `id=1` |
| Ordini duplicati a ogni riavvio | `grid_bot_v3.py:152` usa `keep_sells` mai definito, ingoiato da `except` |
| Segreti esfiltrati come feature | `hermes_cron_report.py:7-14` (hex dump di `.env`) |

## Le regole della quarantena

1. **Vietato eseguire.** Nessun file di `legacy/` va lanciato, in nessuna forma, su nessuna
   macchina. Non "solo per provare": a 100x il capitale e' lo stesso sistema che **non puo'
   accorgersi di perdere**.
2. **Vietato importare.** Nessun modulo di `src/`, `scripts/` o `tests/` puo' importare da
   `legacy/`. Lo verifica `tests/test_quarantena_legacy.py`.
3. **Vietato riparare per riuso.** Il codice non e' "quasi giusto": manca di ledger, di stop
   exchange-side, di idempotenza e di riconciliazione. Si riscrive, non si rammenda.
4. **Ammesso leggere.** E' memoria: serve a non ripetere gli errori, non a riusare le soluzioni.

## Cosa sostituisce cosa

| problema legacy | modulo nuovo |
| :--- | :--- |
| nessun ledger, PnL fabbricato | `money/contabilita.py` |
| risk manager decorativo, soglie su costanti | `money/rischio.py` |
| molteplicita' non corretta, i.i.d. falso | `money/statistica.py` |
| tariffa scritta a mano senza data | `money/costi.py` (`verifica_freschezza`) |
| verdetto senza criterio statistico | `money/cancello.py` |

## Firmato

`[dsh]` 2026-09-28 — audit `docs/11_audit_radicale_2026-09-28.md`.
