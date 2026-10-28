#!/usr/bin/env python3
"""Guardiano dei canali squadra (Artù <-> nodi). «La comunicazione è l'asso nella manica.»

Ogni ora (cron, mc2): per ogni canale in ~/hermes_bridge/<nodo>/ misura l'età dell'ultima
attività (mtime massimo tra requests.md e results.md) e individua le REQ ancora PENDING
senza esito in results.md.
- Alert (Telegram + log) se un canale è muto da più di SOGLIA_MUTO_S (default 7 giorni).
- Alert (Telegram + log) se una REQ PENDING ha più di SOGLIA_REQ_S (default 24h) dall'header.
Sempre: riga di stato in log (append) — il silenzio del guardiano stesso è verificabile.

Stdlib only. Nessuna chiave, nessuna scrittura fuori dal log.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOME = Path.home()
BRIDGE = HOME / "hermes_bridge"
CANALI = ["merlino", "marcodg1", "nuvola", "dsh-mc2", "dsh"]
SOGLIA_MUTO_S = 7 * 86400
SOGLIA_REQ_S = 24 * 3600
LOG = HOME / "money" / "logs" / "channels_watch.log"
NOTIFICA_TG = HOME / "money" / "ops" / "alerts" / "notifica_tg.py"
REQ_RE = re.compile(r"^##\s+(REQ-[\w-]+)\s*\|\s*(\d{4}-\d{2}-\d{2})[\sT]?(\d{2}:\d{2})?.*\|\s*PENDING\b", re.I)
ESITO_RE = re.compile(r"^##\s+(REQ-[\w-]+)", re.I)


def _notifica_tg(testo: str) -> bool:
    try:
        import subprocess
        if not NOTIFICA_TG.exists():
            return False
        r = subprocess.run([sys.executable, str(NOTIFICA_TG), testo], timeout=30, capture_output=True)
        return r.returncode == 0
    except Exception:
        return False


def eta_canale(dir_canale: Path, now: float) -> float | None:
    """Età (s) dell'ultima attività del canale; None se il canale non esiste."""
    if not dir_canale.is_dir():
        return None
    mtimes = []
    for f in ("requests.md", "results.md"):
        p = dir_canale / f
        if p.is_file():
            mtimes.append(p.stat().st_mtime)
    return (now - max(mtimes)) if mtimes else None  # type: ignore[return-value]


def req_pendenti(dir_canale: Path, now: float) -> list[tuple[str, float]]:
    """REQ PENDING senza esito: [(id, età_s)] ordinate per età decrescente."""
    req = dir_canale / "requests.md"
    res = dir_canale / "results.md"
    if not req.is_file():
        return []
    esiti: set[str] = set()
    if res.is_file():
        for riga in res.read_text(encoding="utf-8", errors="replace").splitlines():
            m = ESITO_RE.match(riga.strip())
            if m:
                esiti.add(m.group(1).upper())
    out: list[tuple[str, float]] = []
    for riga in req.read_text(encoding="utf-8", errors="replace").splitlines():
        m = REQ_RE.match(riga.strip())
        if not m or m.group(1).upper() in esiti:
            continue
        ts = datetime.strptime(
            "%sT%s" % (m.group(2), m.group(3) or "00:00"), "%Y-%m-%dT%H:%M"
        ).replace(tzinfo=timezone.utc)
        out.append((m.group(1), now - ts.timestamp()))
    out.sort(key=lambda x: -x[1])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--canali", default=",".join(CANALI), help="lista canali separata da virgola")
    ap.add_argument("--dry", action="store_true", help="non invia Telegram (solo log/stdout)")
    args = ap.parse_args()
    now = time.time()
    canali = [c.strip() for c in args.canali.split(",") if c.strip()]
    alert = []
    stato = []
    for nome in canali:
        d = BRIDGE / nome
        eta = eta_canale(d, now)
        if eta is None:
            stato.append("%s: canale ASSENTE" % nome)
            alert.append("CANALI: canale '%s' assente in ~/hermes_bridge/" % nome)
            continue
        pend = req_pendenti(d, now)
        stato.append("%s: attivita' %.1fh fa, %d REQ pendenti" % (nome, eta / 3600, len(pend)))
        if eta > SOGLIA_MUTO_S:
            alert.append("CANALI: canale '%s' muto da %.1f giorni (ultima attivita' %.1fh fa)" % (
                nome, eta / 86400, eta / 3600))
        for rid, reta in pend:
            if reta > SOGLIA_REQ_S:
                alert.append("CANALI: %s PENDING da %.1fh senza esito in results.md" % (rid, reta / 3600))
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    riga = "[%s] %s" % (ts, " | ".join(stato))
    print(riga)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(riga + (" | ALERT: %s" % "; ".join(alert) if alert else "") + "\n")
    except OSError:
        pass
    if alert and not args.dry:
        stato_tg = _leggi_stato_alert()
        for a in alert:
            ultimo = float(stato_tg.get(a, 0))
            if now - ultimo < 86400:  # max 1 messaggio/giorno per alert
                continue
            if _notifica_tg("⚠️ " + a):
                stato_tg[a] = now
        _scrivi_stato_alert(stato_tg)
    return 0


def _leggi_stato_alert() -> dict:
    try:
        p = LOG.parent / "channels_watch_state.json"
        import json as _json
        return _json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _scrivi_stato_alert(d: dict) -> None:
    try:
        import json as _json
        LOG.parent.mkdir(parents=True, exist_ok=True)
        (LOG.parent / "channels_watch_state.json").write_text(_json.dumps(d), encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":
    raise SystemExit(main())
