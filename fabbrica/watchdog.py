#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Watchdog della Fabbrica — se il nastro non batte, lo dice (mai silenzio).

Ogni minuto (cron): legge `state.json`; se l'ultimo tick e' piu' vecchio di
SOGLIA_S secondi scrive l'allarme su stdout (che cron appende a `log/watchdog.log`)
e in syslog via `logger -t fabbrica-watchdog`. Altrimenti: silenzio.

Perche' esiste: la fabbrica a 20x fa un tick ogni 15s — un'assenza di 5 minuti e'
inequivocabile e va dichiarata, non aspettata. (Lezione "MC2 Offline": un componente
giu' senza alert E' un incidente.)
"""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
STATE = BASE / "state.json"
SOGLIA_S = 300  # 5 minuti = 20 tick saltati: allarme franco, niente falsi positivi


def main() -> int:
    msg = None
    try:
        st = json.loads(STATE.read_text())
        t = datetime.strptime(st["last_ts"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - t).total_seconds()
        if age > SOGLIA_S:
            msg = (f"nessun tick da {age:.0f}s (ultimo n. {st.get('ticks')}) — "
                   f"verificare: systemctl --user status fabbrica-tick.timer")
    except Exception as e:  # state assente/illeggibile = allarme anche questo
        msg = f"state.json illeggibile ({type(e).__name__}: {e})"
    if msg is None:
        return 0
    linea = f"[{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}] FABBRICA WATCHDOG: {msg}"
    print(linea)
    try:
        subprocess.run(["logger", "-t", "fabbrica-watchdog", msg], timeout=5)
    except Exception:
        pass
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
