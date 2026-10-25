#!/usr/bin/env python3
"""agents_status.py — pannello «Agenti»: stato dei daemon di sviluppo sul campo.

Raccoglie, in sola lettura, lo stato degli agenti sui nodi del progetto e lo
scrive in un JSON servito dalla dashboard (/api/agenti.json + pagina /agenti):

  · Hermes gateway    — mc2, omarchy                        (unit utente hermes-gateway)
  · Agent Zero (A0)   — mc2, omarchy, win                   (container docker agent-zero + http :50080)
  · opencode          — mc2, omarchy, nuvola, MARCODG1      (unit opencode + porta :49374)
  · agy (antigravity) — mc2, omarchy, nuvola, MARCODG1      (unit utente antigravity-cli-daemon)
  · DSH web           — mc2 (:4080), omarchy (:5080), win   (unit dsh-web / porta)

Gira SU MC2 (cron ogni minuto; vede tutti i nodi via ssh). Sola lettura: nessun
ordine, nessuna chiave, nessuna mutazione. Se un nodo non è raggiungibile i suoi
operai restano "ignoti" (up: null) e la pagina lo mostra — l'osservabilità morta
è un dato, non un silenzio. Il file viene copiato su MARCODG1 dal cron (la
dashboard pubblica denaro.grivetto.eu parte da lì).

Nota ingegneristica: il probe layer duplica — di proposito, per ora — quello di
ops/zabbix/dev_platform.py (che resta la via d'allarme). Consolidamento previsto
come refactor dedicato, non dentro modifiche di monitoraggio.

Uso:  .venv/bin/python ops/agents/agents_status.py            # raccolta + scrittura JSON
      .venv/bin/python ops/agents/agents_status.py --dry      # stampa tabella, non scrive
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "dashboard" / "agenti.json"

#: nodi linux: alias ssh (None = locale su mc2), operai presenti, porta dsh-web
NODI = {
    "mc2":      {"alias": None,       "operai": ["hermes", "a0", "dsh", "opencode", "agy"], "porta_dsh": 4080},
    "omarchy":  {"alias": "omarchy",  "operai": ["hermes", "a0", "dsh", "opencode", "agy"], "porta_dsh": 5080, "host_dsh": "192.168.1.98"},
    "nuvola":   {"alias": "nuvola",   "operai": ["hermes", "a0", "opencode", "agy"], "porta_dsh": None},
    "marcodg1": {"alias": "MARCODG1", "operai": ["hermes", "a0", "opencode", "agy"], "porta_dsh": None},
}
WIN_ALIAS = "winpc"
WIN_OPERAI = ("a0", "dsh")
PORT_OPENCODE = 49374
VERSIONE = 1

#: ordine di visualizzazione nodi nella pagina
ORDINE_NODI = ["mc2", "omarchy", "win", "nuvola", "marcodg1"]


# --- raccolta ---------------------------------------------------------------------------

def _snippet(cfg: dict) -> str:
    righe = []
    ops = cfg["operai"]
    if "hermes" in ops:
        righe.append("echo hermes=$(XDG_RUNTIME_DIR=/run/user/$(id -u) "
                     "systemctl --user is-active hermes-gateway 2>/dev/null)")
    if "a0" in ops:
        righe.append("echo a0=$( (docker inspect agent-zero --format '{{.State.Status}}' "
                     "2>/dev/null || sudo -n docker inspect agent-zero --format "
                     "'{{.State.Status}}' 2>/dev/null) | grep -v '^$' | tail -n1 )")
        righe.append("echo a0_http=$(curl -s -o /dev/null -w '%{http_code}' --max-time 6 "
                     "http://127.0.0.1:50080/ 2>/dev/null)")
    if "dsh" in ops:
        porta = cfg["porta_dsh"]
        righe.append("echo dsh=$(systemctl is-active dsh-web 2>/dev/null)")
        host_dsh = cfg.get("host_dsh", "127.0.0.1")
        righe.append(f"echo dsh_http=$(curl -s -o /dev/null -w '%{{http_code}}' --max-time 5 "
                     f"http://{host_dsh}:{porta}/ 2>/dev/null)")
    if "opencode" in ops:
        righe.append("echo opencode=$(systemctl is-active opencode 2>/dev/null)")
        righe.append(f"echo opencode_port=$(ss -ltn 2>/dev/null | grep -q ':{PORT_OPENCODE}' "
                     "&& echo 1 || echo 0)")
    if "agy" in ops:
        righe.append("echo agy=$(XDG_RUNTIME_DIR=/run/user/$(id -u) "
                     "systemctl --user is-active antigravity-cli-daemon 2>/dev/null)")
    return "\n".join(righe)


def _parse(testo: str) -> dict:
    out = {}
    for ln in (testo or "").splitlines():
        if "=" in ln:
            k, v = ln.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def raccogli_nodo_linux(cfg: dict) -> dict | None:
    """Ritorna {letture} o None se il nodo non è raggiungibile/eseguibile."""
    sn = _snippet(cfg)
    try:
        if cfg["alias"] is None:
            r = subprocess.run(["bash", "-c", sn], capture_output=True, text=True, timeout=60)
        else:
            r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
                                cfg["alias"], sn],
                               capture_output=True, text=True, timeout=90)
        if r.returncode != 0:
            return None
        lett = _parse(r.stdout)
        return lett if lett else None
    except Exception:  # noqa: BLE001
        return None


def raccogli_win() -> dict | None:
    """Due probe su winpc: porta :3080 (ds) e container agent-zero + http."""
    try:
        r1 = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                             WIN_ALIAS, "netstat -ano | findstr :3080 | findstr /I LISTENING"],
                            capture_output=True, text=True, timeout=60)
        r2 = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                             WIN_ALIAS, "docker inspect agent-zero --format {{.State.Status}}"],
                            capture_output=True, text=True, timeout=60)
        r3 = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                             WIN_ALIAS, "curl.exe -s -o NUL --max-time 8 http://127.0.0.1:48080/ "
                                        "&& echo UP || echo DOWN"],
                            capture_output=True, text=True, timeout=60)
        if r1.returncode != 0 and r2.returncode != 0:
            return None
        return {"dsh_win": r1.stdout.strip(),
                "a0_win": (r2.stdout or "").strip().splitlines()[-1].strip() if (r2.stdout or "").strip() else "",
                "a0_win_http": "UP" if "UP" in (r3.stdout or "") else "DOWN"}
    except Exception:  # noqa: BLE001
        return None


def _voce(up: bool | None, dettaglio: str) -> dict:
    return {"up": up, "dettaglio": dettaglio}


def valuta_linux(lett: dict | None, cfg: dict) -> dict:
    """Letture grezze -> {operaio: {up: True/False/None, dettaglio}}."""
    fuori = {}
    ops = cfg["operai"]
    if lett is None:
        return {s: _voce(None, "nodo non raggiungibile") for s in ops}
    if "hermes" in ops:
        st = lett.get("hermes", "")
        if st:
            fuori["hermes"] = _voce(st == "active", f"unit utente hermes-gateway: {st}")
        else:
            fuori["hermes"] = _voce(None, "unit hermes-gateway non osservabile")
    if "a0" in ops:
        st, http = lett.get("a0", ""), lett.get("a0_http", "")
        if not st:
            fuori["a0"] = _voce(None, "container agent-zero non osservabile")
        else:
            fuori["a0"] = _voce(st == "running" and http in ("200", "302", "401", "403"),
                                f"container {st} · http {http or '—'}")
    if "dsh" in ops:
        st, http = lett.get("dsh", ""), lett.get("dsh_http", "")
        if not st:
            fuori["dsh"] = _voce(None, "unit dsh-web non osservabile")
        else:
            fuori["dsh"] = _voce(st == "active" and http in ("200", "302", "401", "403"),
                                 f"{st} · http {http or '—'}")
    if "opencode" in ops:
        st, porta = lett.get("opencode", ""), lett.get("opencode_port", "")
        if not st:
            fuori["opencode"] = _voce(None, "unit opencode non osservabile")
        else:
            fuori["opencode"] = _voce(st == "active" and porta == "1",
                                      f"{st} · :{PORT_OPENCODE} {'in ascolto' if porta == '1' else 'ASSENTE'}")
    if "agy" in ops:
        st = lett.get("agy", "")
        if st:
            fuori["agy"] = _voce(st == "active", f"unit utente antigravity-cli-daemon: {st}")
        else:
            fuori["agy"] = _voce(None, "unit antigravity-cli-daemon non osservabile")
    return fuori


def valuta_win(lett: dict | None) -> dict:
    if lett is None:
        return {s: _voce(None, "nodo non raggiungibile") for s in WIN_OPERAI}
    fuori = {}
    st = lett.get("a0_win", "")
    http = lett.get("a0_win_http", "")
    if not st:
        fuori["a0"] = _voce(None, "container agent-zero non osservabile")
    else:
        fuori["a0"] = _voce(st == "running" and http == "UP", f"container {st} · http {http}")
    dsh = lett.get("dsh_win", "")
    fuori["dsh"] = _voce(bool(dsh), "porta :3080 in ascolto" if dsh else "porta :3080 NON in ascolto")
    return fuori


def raccogli_tutto() -> dict:
    t0 = time.time()
    nodi = {}
    for nome, cfg in NODI.items():
        lett = raccogli_nodo_linux(cfg)
        nodi[nome] = {"ok": lett is not None, "errore": None if lett else "ssh/exec non eseguibile",
                      "operai": valuta_linux(lett, cfg)}
    w = raccogli_win()
    nodi["win"] = {"ok": w is not None, "errore": None if w else "ssh/exec non eseguibile",
                   "operai": valuta_win(w)}
    nodi = {n: nodi[n] for n in ORDINE_NODI if n in nodi}

    su = giu = ignoti = 0
    per: dict[str, dict[str, int]] = {}
    for n in nodi.values():
        for k, v in n["operai"].items():
            d = per.setdefault(k, {"su": 0, "giu": 0})
            if v["up"] is True:
                su += 1
                d["su"] += 1
            elif v["up"] is False:
                giu += 1
                d["giu"] += 1
            else:
                ignoti += 1

    return {
        "versione": VERSIONE,
        "generated_at": time.time(),
        "generated_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "durata_s": round(time.time() - t0, 1),
        "nodi": nodi,
        "riepilogo": {
            "su": su, "giu": giu, "ignoti": ignoti, "attesi": su + giu,
            "per_strumento": {k: per[k] for k in ("hermes", "a0", "dsh", "opencode", "agy") if k in per},
        },
    }


# --- output -----------------------------------------------------------------------------

def stampa_dry(payload: dict) -> None:
    for nome, n in payload["nodi"].items():
        for k, v in n["operai"].items():
            stato = "?" if v["up"] is None else ("su " if v["up"] else "giu")
            print(f"  {nome:9} {k:9} {stato}  {v['dettaglio']}")
    r = payload["riepilogo"]
    per = " · ".join(f"{k} {v['su']}/{v['su'] + v['giu']}" for k, v in r["per_strumento"].items())
    print(f"riepilogo: su={r['su']} giu={r['giu']} ignoti={r['ignoti']} | {per} | {payload['durata_s']}s")


def scrivi(payload: dict, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, out)  # atomico


def main() -> int:
    ap = argparse.ArgumentParser(description="Pannello agenti — raccolta stato (read-only)")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--dry", action="store_true", help="stampa tabella, non scrive")
    ap.add_argument("--json", action="store_true", help="stampa il payload JSON su stdout")
    args = ap.parse_args()

    payload = raccogli_tutto()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=1))
    if args.dry:
        stampa_dry(payload)
        return 0
    try:
        scrivi(payload, Path(args.out))
    except Exception as e:  # noqa: BLE001
        print(f"SCRITTURA FALLITA {args.out}: {e}")
        return 1
    r = payload["riepilogo"]
    giu = ["%s.%s" % (n, k) for n, nd in payload["nodi"].items()
           for k, v in nd["operai"].items() if v["up"] is False]
    print(f"AGENTI su={r['su']}/{r['attesi']} giu={r['giu']} ignoti={r['ignoti']}"
          f"{' | giu: ' + ' '.join(giu) if giu else ''} | {payload['durata_s']}s -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
