#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Watchdog della Fabbrica — se il nastro non batte, lo dice (mai silenzio).

Ogni minuto (cron): legge `state.json`; se l'ultimo tick e' piu' vecchio di
SOGLIA_S secondi scrive l'allarme su stdout (che cron appende a `log/watchdog.log`)
e in syslog via `logger -t fabbrica-watchdog`. Altrimenti: silenzio.

Perche' esiste: la fabbrica x75 fa un tick ogni 4s (master) + un worker di nodo ogni 10s —
un'assenza oltre SOGLIA_S e' inequivocabile e va dichiarata, non aspettata. Controlla anche
la freschezza degli shard dei worker (fabbrica distribuita su 3 macchine).
(Lezione "MC2 Offline": un componente giu' senza alert E' un incidente.)
"""
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
STATE = BASE / "state.json"
SHARDS = BASE / "shards"
SOGLIA_S = 300  # 5 minuti di silenzio del master: allarme franco, niente falsi positivi


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
        # fabbrica distribuita: shard dei worker (silenzio > 10 min = allarme)
        for nodo in ("marcodg1", "nuvola"):
            try:
                d = json.loads((SHARDS / ("%s.json" % nodo)).read_text())
                age = time.time() - float(d.get("ts") or 0)
            except Exception:
                age = None
            if age is None or age > 600:
                msg = ("worker %s: shard %s — verificare fabbrica-worker.timer sul nodo" % (
                    nodo, "assente" if age is None else "fermo da %ds" % int(age)))
                break
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
