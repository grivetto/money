#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fabbrica — worker di nodo («shard»): esegue i controlli LOCALI di UN nodo e li
pubblica verso il master (mc2) in `fabbrica/shards/<nodo>.json`.

Nato dalla direttiva «3 macchine, suddividi i bot» (01/10): i controlli remoti
(ssh verso MARCODG1, curl verso A0-PC via tailscale) NON devono bloccare il tick
del master — il worker li fa dove ha senso (in locale) e il master legge lo shard
insieme al resto. Solo stdlib; nessun accesso a exchange/ordini.

Gira via `fabbrica-worker.timer` (ogni 10s) sui nodi MARCODG1 e nuvola.
Uso:  python3 worker.py <marcodg1|nuvola>
"""
import json
import os
import socket
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

NODE = (sys.argv[1] if len(sys.argv) > 1 else socket.gethostname()).lower()
LOCAL_DIR = Path.home() / ".fabbrica"
LOCAL_OUT = LOCAL_DIR / ("shard_%s.json" % NODE)

# --- push verso il master (mc2), comando ssh per nodo --------------------------
DEST = "/home/sergio/money/fabbrica/shards/%s.json" % NODE
PUSH = {
    "marcodg1": ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=6", "-p", "2222",
                 "sergio@127.0.0.1"],                       # tunnel inverso mc2
    "nuvola": ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=6",
               "sergio@100.87.24.42"],                      # tailscale
}


_BIN_AMMESSI = frozenset({"systemctl", "curl", "ssh", "ls", "du", "df",
                          "date", "hostname", "pgrep", "ss"})
_METACARATTERI = frozenset(";|&<>`$")


def sh(cmd, timeout=12, cwd=None):
    """Comando SENZA shell (shlex.split + allowlist). Vedi fabbrica.py per la
    motivazione (revisione Manus 06/10). rc 98 = comando rifiutato."""
    if isinstance(cmd, str):
        try:
            parti = shlex.split(cmd)
        except ValueError as exc:
            return 98, "RIFIUTATO: comando non parsabile (%s)" % exc
    else:
        parti = [str(x) for x in cmd]
    if not parti:
        return 98, "RIFIUTATO: comando vuoto"
    if any(c in _METACARATTERI for p in parti for c in p):
        return 98, "RIFIUTATO: metacaratteri di shell"
    if parti[0] not in _BIN_AMMESSI:
        return 98, "RIFIUTATO: binario %r fuori allowlist" % parti[0]
    try:
        r = subprocess.run(parti, shell=False, capture_output=True, text=True,
                           timeout=timeout, cwd=cwd)
        return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()
    except Exception as e:  # noqa: BLE001
        return 99, type(e).__name__


def sysd(unit, prop=None):
    """Stato unit systemd: is-active o una proprietà `systemctl show`."""
    if prop:
        rc, out = sh("systemctl show %s -p %s --value" % (unit, prop))
    else:
        rc, out = sh("systemctl is-active %s" % unit)
    return out if out else ("rc=%d" % rc)


def checks_marcodg1(st):
    """Banco a secco (controllo locale, niente ssh dal master) + servizi del nodo."""
    st["banco_timer"] = sysd("money-banco-secco.timer")
    st["banco_rc"] = sysd("money-banco-secco.service", "ExecMainStatus")
    st["banco_last"] = sysd("money-banco-secco.timer", "LastTriggerUSec")
    st["svc"] = {u: sysd(u) for u in (
        "denaro-aggregator-marcodg1", "denaro-dashboard-marcodg1",
        "denaro-health-marcodg1", "denaro-landing", "cloudflared-denaro")}


def checks_nuvola(st):
    """A0-PC (via tailscale) + servizi del nodo."""
    rc, out = sh("curl -s -m 6 -o /dev/null -w '%{http_code}' "
                 "http://100.76.22.119:50080/api/health", timeout=10)
    st["a0win"] = out if rc == 0 else "DOWN"
    st["svc"] = {u: sysd(u) for u in (
        "denaro-node-nuvola-trade", "denaro-health-nuvola",
        "zabbix-agent", "zabbix-tunnel")}


def main():
    st = {"node": NODE, "ts": time.time(),
          "iso": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    if NODE == "marcodg1":
        checks_marcodg1(st)
    elif NODE == "nuvola":
        checks_nuvola(st)
    else:
        print("nodo sconosciuto: %s" % NODE)
        return 2

    payload = json.dumps(st, ensure_ascii=False, sort_keys=True) + "\n"
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    LOCAL_OUT.write_text(payload)

    cmd = PUSH.get(NODE)
    if not cmd:
        print("push non configurato per %s" % NODE)
        return 2
    remote = "mkdir -p %s && cat > %s.new && mv %s.new %s" % (
        os.path.dirname(DEST), DEST, DEST, DEST)
    try:
        r = subprocess.run(cmd + [remote], input=payload.encode(),
                           capture_output=True, timeout=20)
    except Exception as e:  # noqa: BLE001
        print("PUSH ECCEZIONE: %s" % type(e).__name__)
        return 1
    if r.returncode == 0:
        print("shard %s pubblicato (%s)" % (NODE, DEST))
        return 0
    print("PUSH FALLITO (%d): %s" % (r.returncode, (r.stderr or b"").decode()[:180]))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
