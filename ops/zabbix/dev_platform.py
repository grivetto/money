#!/usr/bin/env python3
"""dev_platform.py — «Operai di sviluppo» (A0 · DSH · agy · opencode) su Zabbix.

Un unico host Zabbix `dev-platform` (gruppo Money) con item trapper + trigger per gli
operai di sviluppo sui nodi mc2 · omarchy · nuvola · MARCODG1 · win. Il collector gira
SU MC2 (cron ogni minuto — vede tutti i nodi): legge lo stato locale e via ssh (una
connessione per nodo), crea al volo host/item/trigger mancanti (idempotente, come
zabbix_bots.py) e pusha i valori via history.push. API Zabbix su 127.0.0.1:1080
(locale su mc2); credenziali SOLO in ~/.zbx_cred, mai nel repo.

Semantica: 1 = operaio su, 0 = giù. Una lettura DEFINITIVA di stato giù (docker
exited, unit inactive, porta assente) pusha 0 subito; se il check NON è eseguibile
(ssh giù) il valore resta l'ultimo buono e solo dopo 3 giri consecutivi di cecità
si pusha 0 (anche l'osservabilità morta è un problema). Heartbeat dedicato:
`dev.collector.heartbeat` (nodata >10m = collector fermo).

Uso:   .venv/bin/python ops/zabbix/dev_platform.py          # giro completo (cron)
       .venv/bin/python ops/zabbix/dev_platform.py --dry    # sola raccolta, niente API
Nessun ordine, nessun exchange: sola lettura di stato + push su Zabbix.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.request
from pathlib import Path

API = "http://127.0.0.1:1080/api_jsonrpc.php"
CRED = Path.home() / ".zbx_cred"
HOST = "dev-platform"
HOST_NAME = "dev-platform — operai di sviluppo (A0 · DSH · agy · opencode)"
GROUP_MONEY = "28"  # gruppo Money (stesso dei bot / nodi)
STATE_FILE = Path("/tmp/dev_platform_state.json")
CIECHI_MAX = 3  # giri consecutivi di check non eseguibile prima di dichiarare giù

#: Gli operai monitorati: chiave item -> (nome, nodo, strumento)
OPERAIO_ITEMS = (
    ("dev.a0.mc2", "A0 su mc2", "mc2", "a0"),
    ("dev.a0.omarchy", "A0 su omarchy", "omarchy", "a0"),
    ("dev.a0.win", "A0 su win", "win", "a0"),
    ("dev.dsh.mc2", "DSH web su mc2", "mc2", "dsh"),
    ("dev.dsh.omarchy", "DSH web su omarchy", "omarchy", "dsh"),
    ("dev.dsh.win", "DSH web su win", "win", "dsh"),
    ("dev.opencode.mc2", "opencode su mc2", "mc2", "opencode"),
    ("dev.opencode.omarchy", "opencode su omarchy", "omarchy", "opencode"),
    ("dev.opencode.nuvola", "opencode su nuvola", "nuvola", "opencode"),
    ("dev.opencode.marcodg1", "opencode su MARCODG1", "marcodg1", "opencode"),
    ("dev.agy.mc2", "agy su mc2", "mc2", "agy"),
    ("dev.agy.omarchy", "agy su omarchy", "omarchy", "agy"),
    ("dev.agy.nuvola", "agy su nuvola", "nuvola", "agy"),
    ("dev.agy.marcodg1", "agy su MARCODG1", "marcodg1", "agy"),
)
ITEM_EXTRA = (
    ("dev.workers_up", "Operai su (conteggio)"),
    ("dev.workers_total", "Operai totali"),
    ("dev.collector.heartbeat", "Collector dev-platform attivo (1 per giro)"),
)

#: Nodi Linux: alias ssh (None = locale su mc2), porta dsh-web, quali operai ha
NODI = {
    "mc2": {"alias": None, "porta_dsh": 4080, "dsh": True, "a0": True},
    "omarchy": {"alias": "omarchy", "porta_dsh": 5080, "dsh": True, "a0": True},
    "nuvola": {"alias": "nuvola", "porta_dsh": None, "dsh": False, "a0": False},
    "marcodg1": {"alias": "MARCODG1", "porta_dsh": None, "dsh": False, "a0": False},
}
WIN_ALIAS = "winpc"


def rpc(method, params, auth=None):
    body = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    if auth:
        body["auth"] = auth
    req = urllib.request.Request(API, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            out = json.loads(resp.read())
    except Exception as e:  # noqa: BLE001
        print(f"RPC {method} error: {e}")
        return None
    if "error" in out:
        print(f"RPC {method} error: {out['error'].get('data', out['error'])}")
        return None
    return out.get("result")


# --- raccolta stato -------------------------------------------------------------------

def _snippet(cfg: dict) -> str:
    righe = []
    if cfg.get("a0"):
        righe.append("echo a0=$( (docker inspect agent-zero --format '{{.State.Status}}' "
                     "2>/dev/null || sudo -n docker inspect agent-zero --format "
                     "'{{.State.Status}}' 2>/dev/null) | grep -v '^$' | tail -n1 )")
        righe.append("echo a0_http=$(curl -s -o /dev/null -w '%{http_code}' --max-time 6 "
                     "http://127.0.0.1:50080/ 2>/dev/null)")
    if cfg.get("dsh"):
        porta = cfg["porta_dsh"]
        righe.append("echo dsh=$(systemctl is-active dsh-web 2>/dev/null)")
        righe.append(f"echo dsh_http=$(curl -s -o /dev/null -w '%{{http_code}}' --max-time 5 "
                     f"http://127.0.0.1:{porta}/ 2>/dev/null)")
    righe.append("echo opencode=$(systemctl is-active opencode 2>/dev/null)")
    righe.append("echo opencode_port=$(ss -ltn 2>/dev/null | grep -q ':49374' && echo 1 || echo 0)")
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


def raccogli_nodo_linux(nome: str, cfg: dict) -> dict | None:
    """Ritorna {letture} o None se il check non è eseguibile (ssh/exec fallita)."""
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
    """Due probe su winpc: porta 3080 (dsh) e stato container agent-zero."""
    try:
        r1 = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                             WIN_ALIAS, "netstat -ano | findstr :3080 | findstr /I LISTENING"],
                            capture_output=True, text=True, timeout=60)
        r2 = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                             WIN_ALIAS, "docker inspect agent-zero --format {{.State.Status}}"],
                            capture_output=True, text=True, timeout=60)
        r3 = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                             WIN_ALIAS, "curl.exe -s -o NUL --max-time 8 http://127.0.0.1:50080/ "
                                        "&& echo UP || echo DOWN"],
                            capture_output=True, text=True, timeout=60)
        if r1.returncode != 0 and r2.returncode != 0:
            return None
        return {"dsh_win": r1.stdout.strip(),
                "a0_win": (r2.stdout or "").strip().splitlines()[-1].strip() if r2.stdout.strip() else "",
                "a0_win_http": "UP" if "UP" in (r3.stdout or "") else "DOWN"}
    except Exception:  # noqa: BLE001
        return None


def valuta(nodo: str, lett: dict | None) -> dict:
    """Letture grezze -> {strumento: True/False/None} (None = non osservabile)."""
    fuori = {}
    if lett is None:
        return {s: None for s in ("a0", "dsh", "opencode", "agy")}
    if nodo == "win":
        fuori["dsh"] = 1 if ":3080" in lett.get("dsh_win", "") else 0
        stato_a0 = lett.get("a0_win", "")
        if not stato_a0:
            fuori["a0"] = None
        else:
            fuori["a0"] = 1 if (stato_a0 == "running"
                                and lett.get("a0_win_http") == "UP") else 0
        return fuori
    stato_a0 = lett.get("a0", "")
    if "a0" in lett:
        if not stato_a0:
            fuori["a0"] = None
        else:
            fuori["a0"] = 1 if (stato_a0 == "running"
                                and lett.get("a0_http") == "200") else 0
    if "dsh" in lett:
        dsh, http = lett.get("dsh", ""), lett.get("dsh_http", "")
        if not dsh:
            fuori["dsh"] = None
        else:
            fuori["dsh"] = 1 if (dsh == "active" and http in ("200", "401", "302")) else 0
    op, porta = lett.get("opencode", ""), lett.get("opencode_port", "")
    if not op:
        fuori["opencode"] = None
    else:
        fuori["opencode"] = 1 if (op == "active" and porta == "1") else 0
    agy = lett.get("agy", "")
    fuori["agy"] = 1 if agy == "active" else (0 if agy else None)
    return fuori


# --- stato anti-cecità ------------------------------------------------------------------

def carica_stato() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:  # noqa: BLE001
        return {}


def salva_stato(st: dict) -> None:
    try:
        STATE_FILE.write_text(json.dumps(st))
    except Exception:  # noqa: BLE001
        pass


# --- entità Zabbix (idempotenti) --------------------------------------------------------

def ensure_host(auth) -> str:
    tro = rpc("host.get", {"filter": {"host": HOST}, "output": ["hostid"]}, auth) or []
    if tro:
        return tro[0]["hostid"]
    res = rpc("host.create", {
        "host": HOST, "name": HOST_NAME, "groups": [{"groupid": GROUP_MONEY}],
        "tags": [{"tag": "tipo", "value": "dev-platform"}],
        "description": "Operai di sviluppo (auto-sync dev_platform.py su mc2). "
                       "Item trapper: 1=su, 0=giù.",
    }, auth)
    if not res:
        raise RuntimeError("host.create fallita")
    print(f"host creato: {HOST}")
    return res["hostids"][0]


def ensure_items(auth, hostid: str) -> int:
    got = rpc("item.get", {"hostids": [hostid], "output": ["key_"]}, auth) or []
    have = {i["key_"] for i in got}
    mancanti = [{"name": nome, "key_": k, "hostid": hostid, "type": 2,
                 "value_type": 3, "history": "30d", "trends": "365d"}
                for k, nome in ([(k, n) for k, n, _, _ in OPERAIO_ITEMS] + list(ITEM_EXTRA))
                if k not in have]
    fatti = 0
    for m in mancanti:
        if rpc("item.create", [m], auth):
            fatti += 1
    return fatti


def ensure_triggers(auth, hostid: str) -> int:
    got = rpc("trigger.get", {"hostids": [hostid], "output": ["description"]}, auth) or []
    have = {t["description"] for t in got}
    defs = []
    for k, nome, _, _ in OPERAIO_ITEMS:
        defs.append((f"Operaio giù: {nome}", f"last(/{HOST}/{k})=0"))
    defs.append(("dev-platform: collector muto (nessun push da 10m)",
                 f"nodata(/{HOST}/dev.collector.heartbeat,10m)=1"))
    defs.append(("dev-platform: almeno un operaio giù",
                 f"last(/{HOST}/dev.workers_up)<last(/{HOST}/dev.workers_total)"))
    fatti = 0
    for desc, expr in defs:
        if desc in have:
            continue
        if rpc("trigger.create", {"description": desc, "expression": expr, "priority": 2}, auth):
            fatti += 1
    return fatti


# --- giro ------------------------------------------------------------------------------

def raccogli_tutto() -> dict:
    """{chiave_item: True/False/None} per i 14 operai (None = non osservabile)."""
    esiti = {}
    for nodo, cfg in NODI.items():
        lett = raccogli_nodo_linux(nodo, cfg)
        val = valuta(nodo, lett)
        for k, _, n, s in OPERAIO_ITEMS:
            if n == nodo:
                esiti[k] = val.get(s)
    wal = raccogli_win()
    val = valuta("win", wal)
    for k, _, n, s in OPERAIO_ITEMS:
        if n == "win":
            esiti[k] = val.get(s)
    return esiti


def risolvi(esiti: dict, stato: dict) -> tuple[dict, list, list]:
    """Applica l'anti-cecità: ritorna (valori_da_pushare, giù, ciechi)."""
    valori, giu, ciechi = {}, [], []
    for k, _nome, _nodo, _s in OPERAIO_ITEMS:
        e = esiti.get(k)
        if e is None:
            streak = int(stato.get(k, 0)) + 1
            stato[k] = streak
            if streak >= CIECHI_MAX:
                valori[k] = 0
                giu.append(f"{k}(cieco)")
                ciechi.append(k)
            else:
                ciechi.append(f"{k}({streak})")
            continue
        stato[k] = 0
        valori[k] = 1 if e else 0
        if not e:
            giu.append(k)
    return valori, giu, ciechi


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="sola raccolta, niente API")
    args = ap.parse_args()

    t0 = time.time()
    esiti = raccogli_tutto()
    stato = carica_stato()
    valori, giu, ciechi = risolvi(esiti, stato)

    if args.dry:
        for k in sorted(esiti):
            v = esiti[k]
            print(f"  {k:26} {'?' if v is None else v}")
        print(f"giù: {giu or '-'} | ciechi: {ciechi or '-'}")
        return 0

    salva_stato(stato)
    try:
        user, password = CRED.read_text().strip().split(":", 1)
    except Exception as e:  # noqa: BLE001
        print(f"CREDENZIALI: impossibile leggere {CRED}: {e}")
        return 1
    auth = rpc("user.login", {"username": user, "password": password})
    if not auth:
        print("LOGIN FALLITO")
        return 1
    try:
        hostid = ensure_host(auth)
        ic = ensure_items(auth, hostid)
        tc = ensure_triggers(auth, hostid)
    except Exception as e:  # noqa: BLE001
        print(f"ENSURE fallita: {e}")
        return 1
    if ic or tc:
        # race della config-cache: item creati in QUESTO giro non sono subito
        # accettati da history.push (visto al primo run: 17/17 scartati in silenzio)
        time.sleep(3)

    up = sum(1 for k in valori if k in {i[0] for i in OPERAIO_ITEMS} and valori[k] == 1)
    data = [{"host": HOST, "key": k, "value": v, "clock": int(time.time())}
            for k, v in sorted(valori.items())]
    data += [{"host": HOST, "key": "dev.workers_up", "value": up, "clock": int(time.time())},
             {"host": HOST, "key": "dev.workers_total", "value": len(OPERAIO_ITEMS),
              "clock": int(time.time())},
             {"host": HOST, "key": "dev.collector.heartbeat", "value": 1,
              "clock": int(time.time())}]
    res = rpc("history.push", data, auth)
    ok = res is not None and res.get("response") == "success"
    print(f"{'PUSH OK' if ok else 'PUSH FALLITO'}: {len(data)} valori | up={up}/{len(OPERAIO_ITEMS)} "
          f"| giù: {' '.join(giu) or '-'} | ciechi: {' '.join(ciechi) or '-'} "
          f"| item+{ic} trig+{tc} | {time.time() - t0:.1f}s")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
