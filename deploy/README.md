# Deploy — mc2 (Hermes)

Unita' e cron VERSIONATI della Fabbrica Denaro (repo `money`). Da un checkout su mc2:

## Timer del tick (systemd user, linger ON)
```
cp deploy/systemd/fabbrica-tick.service ~/.config/systemd/user/
cp deploy/systemd/fabbrica-tick.timer   ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now fabbrica-tick.timer
```
Verifica: `systemctl --user list-timers fabbrica-tick.timer` e
`journalctl --user -u fabbrica-tick.service -n 20 --no-pager`.
Cadenza: 15s (x20 dal 30/09/2026; il check del banco resta ogni ~5' nel codice).

## Watchdog anti-silenzio (cron, ogni minuto)
Aggiungere la riga di `deploy/cron/fabbrica-watchdog` a `crontab -e`.
Allarme (tick fermi > 5') in `fabbrica/log/watchdog.log` + syslog (`logger`).

## Note
- Il tick gira col python del venv `alpha-omega-trading` (host): niente dipendenze extra.
- Il tick non tocca exchange: stato/log/health soltanto.
