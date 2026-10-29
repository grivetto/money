#!/usr/bin/env python3
"""postino.py — postino automatico della squadra Denaro (mc2, cron ogni minuto).

Perche': la chat dei 4 (Artù <-> Merlino/Morgana/Lancillotto) deve essere
sempre attiva e istantanea: un messaggio scritto in requests.md deve svegliare
da solo il nodo destinatario (senza intervento manuale), e ogni ACK/DONE in
results.md deve arrivare (a) nell' inbox di Artù su mc2 e (b) su Telegram.

Modello (v1, prudente e testabile):
- Scansiona i canali `~/hermes_bridge/<canale>/{requests,results}.md`.
- requests.md: il blocco NUOVO piu' recente diventa "pending" alla prima
  vista; dopo GRACE_S di attesa (default 120s, per non pestare il lancio
  manuale di Artù) e con lock del nodo LIBERO e nodo raggiungibile -> lancia
  `lancia_turno.sh` con il prompt di wake (una volta sola: lo stato e' la
  memoria). Lock occupato a eta' >= GRACE -> il turno esiste gia' (Artù o
  altro): il blocco si marca "noop", MAI doppio lancio. Blocchi piu' vecchi
  mai visti (arrivati mentre il postino era giu') -> marcati "storico" e
  loggati, non rilanciati alla cieca.
- results.md: ogni blocco nuovo -> riga pointer nell' inbox di Artù
  (`hermes_bridge/artu/inbox.md`) + UNA notifica Telegram riassuntiva per run.
- Fusibile: max MAX_LANCI_ORA auto-sveglie per canale all' ora (antiloop).
- Stato in `~/.squadra_postino/state.json` (dedup; pota voci > 14 giorni).
  `--seed` marca tutto come visto senza agire (installazione). `--dry` non
  scrive, non lancia, non notifica.

Uso:  postino.py [--dry] [--seed] [--canali merlino,marcodg1,nuvola]
Exit: 0 sempre (gli errori di rete/lancio vanno nel log, non bloccano gli altri).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
BRIDGE = HOME / "hermes_bridge"
ARTU_INBOX = BRIDGE / "artu" / "inbox.md"
LAUNCHER = BRIDGE / "lancia_turno.sh"
NOTIFICA_TG = HOME / "money" / "ops" / "alerts" / "notifica_tg.py"
STATO = HOME / ".squadra_postino" / "state.json"
DIR_LOG = HOME / ".hermes" / "cache" / "scratch" / "nodi"

GRACE_S = 120.0
MAX_LANCI_ORA = 3
POTA_S = 14 * 86400

# canale -> (nodo ssh/lock, nome display, path del prompt di wake SUL nodo)
NODI = {
    "merlino": {"nodo": "omarchy", "nome": "MERLINO", "wake": "/home/sergio/wake_postino.txt"},
    "marcodg1": {"nodo": "MARCODG1", "nome": "LANCILLOTTO", "wake": "/home/marco/wake_postino.txt"},
    "nuvola": {"nodo": "nuvola", "nome": "MORGANA", "wake": "/home/sergio/wake_postino.txt"},
}
CANALI = ["merlino", "marcodg1", "nuvola"]
HEADER_RE = re.compile(r"^##\s+\S")


def _ora_iso(ts: float | None = None) -> str:
    return datetime.fromtimestamp(ts or time.time(), timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _sha(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8", errors="replace")).hexdigest()[:16]


def leggi_blocchi(path: Path) -> list[tuple[str, int]]:
    """[(header, offset)] dei blocchi '## ' del file, in ordine di apparizione."""
    blocchi: list[tuple[str, int]] = []
    try:
        testo = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return blocchi
    for m in re.finditer(r"^##\s+.*$", testo, flags=re.M):
        blocchi.append((m.group(0).strip(), m.start()))
    return blocchi


def _notifica_tg(testo: str, dry: bool) -> bool:
    if dry:
        return False
    try:
        if not NOTIFICA_TG.exists():
            return False
        r = subprocess.run([sys.executable, str(NOTIFICA_TG), testo],
                           timeout=30, capture_output=True)
        return r.returncode == 0
    except Exception:
        return False


def lock_libero(nodo: str) -> bool:
    """True se il lock del nodo e' libero (nessun turno in corso)."""
    try:
        r = subprocess.run(["flock", "-n", "/tmp/agente_%s.lock" % nodo, "true"],
                           timeout=10, capture_output=True)
        return r.returncode == 0
    except Exception:
        return False


def nodo_raggiungibile(nodo: str) -> bool:
    try:
        r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
                            nodo, "true"], timeout=20, capture_output=True)
        return r.returncode == 0
    except Exception:
        return False


def lancia_wake(canale: str, dry: bool) -> bool:
    """Lancia il turno di wake per il canale. True se il processo e' partito."""
    cfg = NODI[canale]
    if dry:
        return False
    DIR_LOG.mkdir(parents=True, exist_ok=True)
    logpath = DIR_LOG / ("auto_%s_%s.log" % (canale, datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")))
    try:
        subprocess.Popen([str(LAUNCHER), cfg["nodo"], cfg["wake"], str(logpath)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        return True
    except Exception:
        return False


def _stato_carica() -> dict:
    try:
        d = json.loads(STATO.read_text(encoding="utf-8"))
        if isinstance(d, dict):
            d.setdefault("blocchi", {})
            d.setdefault("lanci", {})
            return d
    except Exception:
        pass
    return {"blocchi": {}, "lanci": {}}


def _stato_salva(stato: dict, dry: bool) -> None:
    if dry:
        return
    ora = time.time()
    # pota: blocchi vecchi > POTA_S, lanci vecchi > 1 giorno
    stato["blocchi"] = {k: v for k, v in stato["blocchi"].items()
                        if ora - float(v.get("first_seen", ora)) < POTA_S}
    if len(stato["blocchi"]) > 800:  # tetto di sicurezza
        stato["blocchi"] = dict(list(stato["blocchi"].items())[-800:])
    for c in list(stato["lanci"]):
        stato["lanci"][c] = [t for t in stato["lanci"][c] if ora - float(t) < 3600]
    STATO.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATO.with_suffix(".tmp")
    tmp.write_text(json.dumps(stato, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, STATO)


def _appendi_inbox(righe: list[str], dry: bool) -> None:
    if dry or not righe:
        return
    ARTU_INBOX.parent.mkdir(parents=True, exist_ok=True)
    nuovo = not ARTU_INBOX.exists()
    with ARTU_INBOX.open("a", encoding="utf-8") as f:
        if nuovo:
            f.write("# Inbox di Artù — messaggi dai nodi (scritto dal postino della squadra).\n"
                    "# Convenzione: a inizio sessione leggere; dopo la presa in carico appendere una riga `=== letto <ts> ===`.\n")
        for r in righe:
            f.write(r + "\n")


def processa_requests(canale: str, stato: dict, ora: float, dry: bool, seed: bool) -> list[str]:
    """Gestisce il/new block di requests.md del canale. Ritorna righe di report."""
    req = BRIDGE / canale / "requests.md"
    blocco = leggi_blocchi(req)
    if not blocco:
        return []
    out: list[str] = []
    visti = stato["blocchi"]
    # 0) seed: marca tutto come visto e non fare nulla (installazione)
    if seed:
        for hdr, _ in blocco:
            key = "%s|requests|%s" % (canale, _sha(hdr))
            visti.setdefault(key, {"first_seen": ora, "status": "seed", "sig": hdr[:90]})
        return out
    # 1) blocchi mai visti: l'ultimo diventa candidato; i piu' vecchi -> storico
    for hdr, _ in blocco[:-1]:
        key = "%s|requests|%s" % (canale, _sha(hdr))
        if key not in visti:
            visti[key] = {"first_seen": ora, "status": "storico", "sig": hdr[:90]}
            out.append("requests: blocco storico non gestito -> %s" % hdr[:90])
    hdr_last = blocco[-1][0]
    key_last = "%s|requests|%s" % (canale, _sha(hdr_last))
    if key_last not in visti:
        visti[key_last] = {"first_seen": ora, "status": "pending", "sig": hdr_last[:90]}
        out.append("requests: nuovo blocco in attesa (grace) -> %s" % hdr_last[:90])
    # 2) candidati pending: il piu' vecchio oltre la grazia
    pend = [(k, v) for k, v in visti.items()
            if k.startswith(canale + "|requests|") and v.get("status") == "pending"]
    pend.sort(key=lambda kv: float(kv[1].get("first_seen", ora)))
    if not pend:
        return out
    key, v = pend[0]
    eta = ora - float(v.get("first_seen", ora))
    if eta < GRACE_S:
        out.append("requests: in attesa da %.0fs (< grace %.0fs)" % (eta, GRACE_S))
        return out
    nodo = NODI[canale]["nodo"]
    if not lock_libero(nodo):
        v["status"] = "noop"
        out.append("requests: lock %s occupato (turno gia' in corso) -> noop %s" % (nodo, v["sig"][:70]))
        return out
    if not nodo_raggiungibile(nodo):
        out.append("requests: %s non raggiungibile, riprovo al prossimo giro" % nodo)
        return out
    lanci = stato["lanci"].setdefault(canale, [])
    if len(lanci) >= MAX_LANCI_ORA:
        v["status"] = "fuse"
        out.append("requests: FUSIBILE %d lanci/ora su %s -> fermo %s" % (MAX_LANCI_ORA, canale, v["sig"][:70]))
        return out
    ok = lancia_wake(canale, dry)
    if ok:
        lanci.append(ora)
        v["status"] = "dispatched"
        out.append("requests: WAKE lanciato su %s -> %s" % (nodo, v["sig"][:80]))
    else:
        out.append("requests: lancio FALLITO su %s (riprovo)" % nodo)
    return out


def processa_results(canale: str, stato: dict, ora: float, dry: bool, seed: bool) -> tuple[list[str], list[str]]:
    """Blocchi nuovi di results.md -> righe inbox (e report)."""
    res = BRIDGE / canale / "results.md"
    blocchi = leggi_blocchi(res)
    inbox: list[str] = []
    out: list[str] = []
    for hdr, _ in blocchi:
        key = "%s|results|%s" % (canale, _sha(hdr))
        if key in stato["blocchi"]:
            continue
        stato["blocchi"][key] = {"first_seen": ora,
                                 "status": "seed" if seed else "inbox", "sig": hdr[:90]}
        if not seed:
            inbox.append("- `%s` · **%s** · %s" % (_ora_iso(ora), canale, hdr[:150]))
    if inbox:
        _appendi_inbox(inbox, dry)
        out.append("results: %d nuovi blocchi -> inbox Artu'" % len(inbox))
    return inbox, out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry", action="store_true", help="non scrive, non lancia, non notifica")
    ap.add_argument("--seed", action="store_true", help="marca tutto come visto, nessuna azione")
    ap.add_argument("--canali", default=",".join(CANALI))
    args = ap.parse_args()
    ora = time.time()
    canali = [c.strip() for c in args.canali.split(",") if c.strip()]
    stato = _stato_carica()
    report: list[str] = []
    tg_righe: list[str] = []
    for canale in canali:
        if canale not in NODI:
            report.append("%s: canale sconosciuto" % canale)
            continue
        try:
            r = processa_requests(canale, stato, ora, args.dry, args.seed)
        except Exception as e:  # un canale rotto non ferma gli altri
            r = ["requests: ECCEZIONE %s: %s" % (type(e).__name__, e)]
        report += ["%s %s" % (canale, x) for x in r]
        try:
            inbox, r2 = processa_results(canale, stato, ora, args.dry, args.seed)
        except Exception as e:
            inbox, r2 = [], ["results: ECCEZIONE %s: %s" % (type(e).__name__, e)]
        report += ["%s %s" % (canale, x) for x in r2]
        for riga in inbox:
            tg_righe.append(riga.split("·")[-1].strip()[:80])
    _stato_salva(stato, args.dry)
    # Telegram: UNA notifica per run, solo se c'e' qualcosa
    if tg_righe and not args.seed:
        msg = "Squadra: %d nuovi dai nodi\n" % len(tg_righe) + "\n".join("· " + r for r in tg_righe[:6])
        ok = _notifica_tg(msg, args.dry)
        report.append("TG: notifica %s" % ("inviata" if ok else ("dry" if args.dry else "FALLITA")))
    pref = "[dry] " if args.dry else ("[seed] " if args.seed else "")
    for riga in report:
        print("%s%s | %s" % (pref, _ora_iso(ora), riga))
    if not report:
        print("%s%s | nessuna novita'" % (pref, _ora_iso(ora)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
