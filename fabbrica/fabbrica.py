#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fabbrica Denaro — il nastro: candidato -> test -> cancello -> (produzione su promozione).

Un tick ogni 5 minuti (cron). Un tick esegue/avanza UNA azione utile e aggiorna lo stato.
NON lancia ordini, NON tocca exchange, NON inventa numeri: le azioni che richiedono
giudizio o dati nuovi vengono MARCATE come AZIONE in STATO.md.

Vedi README.md per le regole (test prima dei numeri; cancello decide; produzione solo su promozione).
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent          # ~/money/fabbrica
REPO = BASE.parent
STATE = BASE / "state.json"
STATEDOC = BASE / "STATO.md"
LOG = BASE / "log" / "fabbrica.log"
PY = "/home/sergio/alpha-omega-trading/venv/bin/python"
DSH = Path("/home/sergio/hermes_bridge/dsh")
HANDOFF = DSH / "handoff"
A0WIN = "http://100.76.22.119:50080"


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write("[%s] %s\n" % (now(), msg))
    print("[%s] %s" % (now(), msg))


def load(p, default):
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return default


def save(p, obj):
    Path(p).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def sh(cmd, timeout=20):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return 99, "%s: %s" % (type(e).__name__, e)


def check_dsh(st):
    try:
        txt = (DSH / "results.md").read_text(errors="replace")
        heads = sum(1 for l in txt.splitlines() if l.startswith("## "))
        if "dsh_heads_seen" not in st:
            st["dsh_heads_seen"] = heads
            log("canale DSH: baseline inizializzata (%d voci)" % heads)
        st["dsh_heads"] = heads
        st["dsh_new"] = heads - int(st["dsh_heads_seen"])
        if st["dsh_new"] > 0:
            log("CANALE DSH: %d voci nuove in results.md -> AZIONE per Hermes (leggere)" % st["dsh_new"])
    except Exception:
        st["dsh_new"] = -1


def check_handoff_p2(st):
    d = HANDOFF / "P2"
    files = sorted([p.name for p in d.glob("*") if p.is_file()]) if d.exists() else []
    st["p2_handoff_files"] = files
    if files:
        man = d / "MANIFEST.sha256"
        if man.exists():
            rc, out = sh("cd %s && sha256sum -c MANIFEST.sha256" % d, timeout=30)
            st["p2_handoff_manifest"] = "OK" if rc == 0 else "FALLITO"
            if rc != 0:
                log("HANDOFF P2: MANIFEST FALLITO -> %s" % out.strip()[-200:])
        else:
            st["p2_handoff_manifest"] = "assente"
        if not st.get("p2_handoff_notified"):
            st["p2_handoff_notified"] = True
            log("HANDOFF P2: artefatti presenti -> AZIONE Hermes: review + commit + misura")


def check_p2(st):
    runner = REPO / "scripts" / "misura_p2.py"
    if st.get("p2_done"):
        st["p2"] = "misurata/fatta"
    elif runner.exists():
        st["p2"] = "runner presente -> AZIONE: lanciare la misura P2"
        if not st.get("p2_runner_notified"):
            st["p2_runner_notified"] = True
            log("P2: runner scripts/misura_p2.py presente -> AZIONE Hermes: misurare")
    else:
        st["p2"] = "in attesa (implementazione/handoff dsh)"


def check_a0win(st):
    rc, out = sh("curl -s -m 8 -o /dev/null -w '%{http_code}' " + A0WIN + "/api/health", timeout=15)
    code = out.strip() if rc == 0 else "DOWN"
    st["a0win"] = code
    if code != "200" and st.get("a0win_last") == "200":
        log("A0-PC: NON raggiungibile (%s) -> AZIONE: verificare" % code)
    st["a0win_last"] = code


def check_a0mc2(st):
    rc, out = sh("curl -s -m 6 -o /dev/null -w '%{http_code}' http://127.0.0.1:50080/api/health", timeout=12)
    st["a0mc2"] = out.strip() if rc == 0 else "DOWN"


def check_banco(st):
    cmd = ("ssh -o BatchMode=yes -o ConnectTimeout=6 MARCODG1 "
           "'A=$(systemctl is-active money-banco-secco.timer 2>/dev/null); "
           "B=$(systemctl show money-banco-secco.service -p ExecMainStatus --value 2>/dev/null); "
           "C=$(systemctl show money-banco-secco.timer -p LastTriggerUSec --value 2>/dev/null); "
           "echo timer=$A rc=$B ultimo=$C'")
    rc, out = sh(cmd, timeout=20)
    st["banco"] = out.strip().replace(chr(10), " | ") or ("rc=%d" % rc)


def check_specgen(st):
    cand = load(BASE / "candidati.json", [])
    nxt = None
    for c in cand:
        spec = REPO / c.get("spec", "")
        if not spec.exists():
            nxt = c
            break
    st["spec_next"] = (nxt or {}).get("id")
    if nxt:
        st["spec_next_desc"] = nxt.get("desc", "")
        if not st.get("spec_notified_%s" % nxt.get("id")):
            st["spec_notified_%s" % nxt.get("id")] = True
            log("SPECGEN: prossima spec da materializzare: %s (%s)" % (nxt.get("id"), nxt.get("desc", "")))


def check_inbox(st):
    inbox = BASE / "inbox"
    files = sorted([p.name for p in inbox.glob("*") if p.is_file() and p.name != ".gitkeep"]) if inbox.exists() else []
    st["inbox"] = files
    seen = set(st.get("inbox_notified") or [])
    fresh = [f for f in files if f not in seen]
    if fresh:
        st["inbox_notified"] = sorted(seen | set(files))
        log("INBOX: nuovi file da lavorare: %s" % ", ".join(fresh))


def write_stato(st):
    lines = [
        "# Fabbrica — stato",
        "",
        "- ultimo tiro: %s (tiro n. %s, cadenza 5 min via cron)" % (now(), st.get("ticks", 0)),
        "- canale DSH: %s voci totali, nuove dall'ultimo tiro: %s" % (st.get("dsh_heads"), st.get("dsh_new")),
        "- handoff P2: %s | manifest: %s" % (", ".join(st.get("p2_handoff_files") or []) or "(vuoto)",
                                             st.get("p2_handoff_manifest", "-")),
        "- P2: %s" % st.get("p2"),
        "- A0-PC: HTTP %s" % st.get("a0win"),
        "- A0-MC2: HTTP %s" % st.get("a0mc2"),
        "- banco MARCODG1: %s" % st.get("banco"),
        "- prossima spec da materializzare: %s %s" % (st.get("spec_next") or "(nessuna)",
                                                      "— " + st.get("spec_next_desc", "") if st.get("spec_next") else ""),
        "- inbox: %s" % (", ".join(st.get("inbox") or []) or "(vuoto)"),
        "",
        "## Azioni in attesa (per owner)",
        "- Hermes: review handoff P2 appena arriva; misure; commit",
        "- DSH: handoff P2 (implementazione) + risposta al ponte-dsh sul PC",
        "- A0-MC2: P8 in corso (brief in /a0/usr/workdir, deliverable in p8/) | A0-PC: disponibile",
        "",
        "_Regole: test prima dei numeri; il cancello decide; produzione solo su promozione._",
    ]
    STATEDOC.write_text("\n".join(lines) + "\n")


def main():
    st = load(STATE, {})
    st["ticks"] = int(st.get("ticks", 0)) + 1
    st["last_ts"] = now()
    check_dsh(st)
    check_handoff_p2(st)
    check_p2(st)
    check_a0win(st)
    check_a0mc2(st)
    check_banco(st)
    check_specgen(st)
    check_inbox(st)
    save(STATE, st)
    write_stato(st)
    log("tick completato (n. %d)" % st["ticks"])


if __name__ == "__main__":
    main()
