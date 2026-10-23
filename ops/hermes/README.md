# Hermes Daily Update — ops/hermes/

Script e configurazione per l'aggiornamento giornaliero di Hermes
su tutti e 4 i nodi Linux del progetto Denaro.

## Nodi

| Nodo | SSH alias | Utente | Hermes home |
|------|-----------|--------|-------------|
| mc2 | local | sergio | /home/sergio/.hermes |
| nuvola | nuvola | sergio | /home/sergio/.hermes |
| MARCODG1 | MARCODG1 | marco | /home/marco/.hermes |
| omarchy | omarchy | sergio | /home/sergio/.hermes |

## Script

- `daily_update.sh` — script principale (versionato qui)
- `~/.hermes/scripts/daily_update.sh` — wrapper per il cron (chiama questo file)

## Cron

- Job: `hermes-daily-update` (id: 13c2a534759b)
- Schedule: ogni giorno alle 04:00 CEST
- Modo: `no_agent` (esecuzione diretta dello script, senza LLM)
- Log: `~/.hermes/logs/daily_update/summary_YYYYMMDD_HHMMSS.log`
- Backup config: `~/.hermes/logs/daily_update/<nodo>_YYYYMMDD_HHMMSS/`

## Operazioni eseguite per ogni nodo

1. **Backup** config.yaml, skills (SKILL.md), profili, git HEAD, crontab
2. **hermes update** (con versione pre/post nel log)
3. **MOA anti-refusal patch** (solo mc2, dopo l'update)

## Modifiche

Per modificare lo script, editare questo file (`~/money/ops/hermes/daily_update.sh`).
Il cron usa il wrapper in `~/.hermes/scripts/daily_update.sh` che punta qui
tramite `exec`, quindi le modifiche prendono effetto al prossimo giro.

## Ripristino cron dopo rebuild

```bash
# Il job va ricreato se il gateway viene resettato
hermes cron create --name hermes-daily-update --schedule "every day at 4am" \
  --script daily_update.sh --no-agent --deliver local --workdir /home/sergio
```