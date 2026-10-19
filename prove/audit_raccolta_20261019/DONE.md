# DONE — Comandi Esatti Usati per l'Audit (READ-ONLY)

Tutti i comandi seguenti sono stati eseguiti in sola lettura su `MARCODG1` in data `2026-10-19T19:59:53Z – 2026-10-19T20:03:06Z`.

## 1. Verifica Timer, Unit Systemd e Script
```bash
date -u; date
systemctl list-timers --all --no-pager | grep -i money
ls -la ~/money/deploy/scripts/cron_ricerca_*.sh
systemctl status money-ricerca-raccolta.timer money-ricerca-raccolta.service money-ricerca-scansione.timer money-ricerca-scansione.service --no-pager
systemctl cat money-ricerca-raccolta.timer money-ricerca-raccolta.service money-ricerca-scansione.timer money-ricerca-scansione.service --no-pager
```

## 2. Ispezione Log Journald (Ultime 72h, utente e sudo)
```bash
id
sudo -n true
journalctl -u money-ricerca-raccolta.service --since "3 days ago" --no-pager | tail -40
journalctl -u money-ricerca-scansione.service --since "3 days ago" --no-pager | tail -40
journalctl -u money-ricerca-raccolta.service --since "3 days ago" --no-pager -q | grep -c "=== raccolta ricerca edge"
journalctl -u money-ricerca-raccolta.service --since "3 days ago" --no-pager -q | grep -c "=== raccolta completata ==="
journalctl -u money-ricerca-raccolta.service --since "3 days ago" --no-pager -q | grep -v -E "^Oct .* (===|--- \[|  xlm:|  trx:|fatto|raccolta 7g: scritti=0 duplicati=210 errori=0)"
journalctl -u money-ricerca-scansione.service --since "3 days ago" --no-pager -q | grep -c "=== scansione ricerca edge"
journalctl -u money-ricerca-scansione.service --since "3 days ago" --no-pager -q | grep -c "=== scansione completata ==="
journalctl -u money-ricerca-scansione.service --since "3 days ago" --no-pager -q | grep -E "=== scansione|\[!\]|ERRORE|Traceback"
sudo journalctl -u money-ricerca-raccolta.service --no-pager | head -15
sudo journalctl -u money-ricerca-scansione.service --no-pager | head -25
sudo journalctl -u money-ricerca-raccolta.service --since "3 days ago" --no-pager | grep -E "Starting|Finished|Failed|=== raccolta|raccolta 7g:|DOGEUSDT" | head -35
```

## 3. Verifica Freschezza e Integrità Dati Prodotti
```bash
# Directory e timestamp di modifica (mtime)
ls -la --time-style=full-iso /home/marco/money/data/ /home/marco/money/data/esterni/ /home/marco/money/data/tick/
ls -la --time-style=full-iso /home/marco/money/logs/ /home/marco/money/logs/tick_watch/ /home/marco/money/prove/scansioni/ /home/marco/money/data/carry_multi/ /home/marco/money/data/cache/

# 3.1 Archivio Funding (data/funding_xperp.jsonl)
wc -l /home/marco/money/data/funding_xperp.jsonl
tail -15 /home/marco/money/data/funding_xperp.jsonl
/home/marco/money/.venv/bin/python3 /home/marco/money/scripts/raccogli_funding.py --report 7

# 3.2 On-Chain & Sentiment (data/esterni/*.json)
/home/marco/money/.venv/bin/python3 -c '
import json, glob, datetime as dt
for p in sorted(glob.glob("/home/marco/money/data/esterni/*.json")):
    d = json.load(open(p))
    name = p.split("/")[-1]
    if name == "sentiment_fng.json":
        ts = max(int(k) for k in d.keys())
        print(f"{name:22s}: entries={len(d):5d} max_ts={ts} ({dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat()})")
    elif name == "defi_tvl.json":
        ts = max(int(k) for k in d.keys())
        print(f"{name:22s}: entries={len(d):5d} max_ts={ts} ({dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat()})")
    else:
        max_dates = {m: max(v.keys()) for m, v in d.items() if v}
        overall_max = max(max_dates.values())
        px_max = max_dates.get("PriceUSD", "N/A")
        print(f"{name:22s}: metrics={len(d):3d} max_date={overall_max} PriceUSD_max={px_max}")
'

# 3.3 Tick Bybit (data/tick/*.csv.gz)
gzip -t /home/marco/money/data/tick/*.csv.gz && echo "gzip integrity: ALL OK"
zcat /home/marco/money/data/tick/DOGEUSDT_2026-10-18.csv.gz | head -2
zcat /home/marco/money/data/tick/DOGEUSDT_2026-10-18.csv.gz | tail -3

# 3.4 Log accessori e artefatti scansione
cat /home/marco/money/data/ricerca_stato.json
cat /home/marco/money/logs/tick_watch/cron.log
tail -20 /home/marco/money/logs/genera_ricerca.log
tail -20 /home/marco/money/prove/funding_scan_20261019.txt
```

## 4. File Sorgente Ispezionati (sola lettura)
- `/home/marco/money/deploy/scripts/cron_ricerca_raccolta.sh`
- `/home/marco/money/deploy/scripts/cron_ricerca_scansione.sh`
- `/home/marco/money/scripts/raccogli_funding.py`
- `/home/marco/money/scripts/scarica_esterni.py`
- `/home/marco/money/scripts/funding_scan.py`
- `/home/marco/money/scripts/setaccia_onchain.py`
- `/home/marco/money/scripts/analisi_orderflow.py`
