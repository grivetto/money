# 35 — Lezioni dai framework open-source: Freqtrade · Jesse · Backtesting.py

Data: 2026-10-18 · Autore: Artù (ingegnere capo) · Stato: studio read-only in scratch — nessuna adozione

Mandato: direttiva owner 18/10 («non reinventare la ruota sull'infrastruttura di esecuzione: routing ordini, persistenza, calcolo base — studiare i framework Python maturi»). Metodo: clone shallow in scratch (jetable, mai nel venv canonico), ispezione mirata ai punti del mandato, verdetti con la skill `trading-tool-scouting`.

## Verdetti rapidi

| Repo | ★ | Licenza | Verdetto | Perché |
| --- | ---: | --- | --- | --- |
| freqtrade/freqtrade | 55,5k | GPL-3.0 | **panchina** | second-opinion engine quando esisterà una candidata; GPL: non incorporare codice nel nostro repo |
| jesse-ai/jesse | 8,7k | MIT | **estrai (lezioni)** | `research/` con rule-significance bootstrap + Monte Carlo; MIT = assorbibile |
| kernc/backtesting.py | 9,1k | AGPL-3.0 | **studio** | vettorizzazione + stats; AGPL: standalone, non integrare in servizi esposti |

## Cosa ho visto (fatti, dal codice)

- **Freqtrade** — persistenza SQLAlchemy in `persistence/` (`trade_model.py`, `key_value_store.py`, `pairlock.py`, `wallet_history.py`, migrazioni); **lookahead-analysis automatica** (`optimize/analysis/lookahead_helpers.py` + `recursive_helpers.py`); RPC/Telegram disaccoppiato dal core (engine ≠ UI); retry/rate-limit in gran parte delegati a ccxt.
- **Jesse** — `research/` con `rule_significance_testing/` (bootstrap + simulator: verifica se una REGOLA ha potere predittivo genuino), `monte_carlo/` (su trade E su candele), `ml.py`, `optimize/`; separazione netta research/live (`modes/`, `services/`, `repositories/`, `store/`); server MCP incluso.
- **Backtesting.py** — core vettorizzato numpy/pandas (~1.800 righe), `compute_stats` (Sharpe/Sortino/Calmar/DD), `random_ohlc_data` (random control), `SignalStrategy` / `TrailingStrategy` / `FractionalBacktest`.

## Lezioni per money (selettive — backlog, non adozione)

1. **Rule-significance bootstrap (Jesse)**: il nostro DSR corregge i risultati dei backtest; il loro test verifica la regola su ingressi simulati PRIMA del backtest — complementare. → backlog: valutare come filtro pre-backtest nel protocollo, coi numeri, quando ci sarà la prossima candidata.
2. **Monte Carlo su trade (Jesse)**: bootstrap delle sequenze di trade per distribuzione del DD — oggi non lo facciamo. → backlog: candidato a secondaria obbligatoria dei verdetti.
3. **Random control esplicito (Backtesting.py / Vibe-Trading)**: da verificare se il protocollo attuale lo copre già (criterio 8 / DSR); se assente, candidato a criterio aggiuntivo.
4. **Lookahead-analysis automatica (Freqtrade)**: noi abbiamo test anti-lookahead per modulo; un check generico in CI è un possibile upgrade — bassa priorità.
5. **Vettorizzazione (Backtesting.py)**: rilevante se/quando faremo screening su tick grandi (scansione microstruttura ~15/11). Nota per il futuro.

## Cosa NON facciamo

- Nessuna adozione di framework interi (secondo sistema in parallelo = vietato dal metodo).
- Nessun codice GPL/AGPL incorporato; nessuna dipendenza nuova nel venv canonico.
- Nessuna decisione su questi punti senza passare da una voce di coda.

## Riferimenti

Clone jetable: `~/.hermes/cache/scratch/fw/{freqtrade,jesse,backtesting.py}` (si butta). Skill: `trading-tool-scouting`. Direttiva owner 2026-10-18.
