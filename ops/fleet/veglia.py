#!/usr/bin/env python3
"""veglia.py — veglia della flotta Denaro (Trade + ops): controlli meticolosi e auto-riparazione.

Ogni ~2 minuti su ciascun nodo (systemd timer, utente del nodo):
  1) CONTROLLA — unit systemd, unit utente, endpoint HTTP locali, container docker,
     freschezza dei file vitali (snapshot, banco a secco, canary, carry).
  2) RIPARA   — unit giu' -> restart (cooldown 15'); container giu' -> start. Poi RIVERIFICA.
  3) NOTIFICA — rosso persistente / rientri sul canale Telegram del progetto, se disponibile
     sul nodo (oggi: mc2); altrimenti solo log locale.
  4) SCRIVE   — ~/.veglia/last.json + una riga di log su ~/.veglia/veglia.log.

Leggera e onesta: nessuna azione oltre restart/start; niente sul percorso del denaro;
nessun segreto stampato. Un componente giu' senza accorgersene e' un incidente.

Uso:  veglia.py check              # sola lettura (nessun heal, nessuna notifica)
      veglia.py run                # check + heal + notifica (usato dal timer)
      veglia.py run --no-heal --no-alert
Exit: 0 tutto ok/riparato · 1 qualcosa rosso (dopo il tentativo) · 2 errore d'ambiente.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DIR = Path.home() / ".veglia"
LAST = DIR / "last.json"
LOG = DIR / "veglia.log"

HEAL_COOLDOWN = 900      # 15': non restartare la stessa cosa piu' di una volta ogni 15'
NOTIF_COOLDOWN = 3600    # 1h per chiave in rosso

# --- profili per nodo --------------------------------------------------------------------

PROFILI: dict[str, dict] = {
    "mc2": {
        "unita": [
            "money-aggregator-mc2", "money-health-mc2", "money-dashboard-mc2",
            "denaro-feeder-mc2", "denaro-exporter-mc2", "cloudflared-home",
            "mc2-hardening", "zabbix-agent", "tailscaled", "docker", "cron",
        ],
        "unita_utente": ["denaro-node-mc2", "hermes-gateway", "fabbrica-tick.timer"],
        "http": [
            ("http://127.0.0.1:8911/health", (200,), 15),
            ("http://127.0.0.1:8912/api/infra.json", (200,), 30),
            ("http://127.0.0.1:8913/", (200,), 15),
            ("http://127.0.0.1:4080/", (401,), 10),     # DSH-mc2: 401 = atteso (login)
            ("http://127.0.0.1:50080/", (200,), 15),    # A0-mc2
        ],
        "docker": ["agent-zero", "zabbix-server", "zabbix-web", "zabbix-db"],
        "file": [("/home/sergio/denaro/health/infra_snapshot.json", 300)],
    },
    "marcodg1": {
        "unita": [
            "money-aggregator-marcodg1", "money-dashboard-marcodg1", "money-health-marcodg1",
            "money-landing-marcodg1", "money-watchdog-marcodg1.timer",
            "money-banco-secco.timer", "fabbrica-worker.timer",
            "money-ricerca-raccolta.timer", "money-ricerca-scansione.timer",
            "cloudflared", "zabbix-agent", "tailscaled",
        ],
        "unita_utente": [],
        "http": [
            ("http://127.0.0.1:8911/health", (200,), 15),
            ("http://127.0.0.1:8912/api/infra.json", (200,), 90),   # collect live: lento
            ("http://127.0.0.1:8913/", (200,), 30),
            ("http://127.0.0.1:8914/", (200,), 15),
        ],
        "docker": [],
        "file": [
            ("/home/marco/denaro/health/infra_snapshot.json", 300),
            ("/home/marco/money/logs/banco_secco.jsonl", 900),
            ("/home/marco/canary/canary.log", 2400),
            ("/home/marco/money/data/carry_stato.json", 3600),
        ],
    },
    "nuvola": {
        "unita": ["denaro-node-nuvola-trade", "money-health-nuvola", "denaro-exporter", "zabbix-agent", "tailscaled"],
        "unita_utente": [],
        "http": [
            ("http://127.0.0.1:8911/health", (200,), 15),
            ("http://127.0.0.1:9100/metrics", (200,), 10),
        ],
        "docker": [],
        "file": [],
    },
}


def profilo_per_host(h: str | None = None) -> tuple[str | None, dict | None]:
    h = (h or socket.gethostname()).lower()
    for nome in ("marcodg1", "nuvola", "mc2"):
        if nome in h:
            return nome, PROFILI[nome]
    return None, None


# --- motore ------------------------------------------------------------------------------

def esegui_bash(cmd: str, timeout: int = 40) -> tuple[int, str, str]:
    try:
        r = subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except Exception as e:  # noqa: BLE001
        return 1, "", e.__class__.__name__


class Esito:
    __slots__ = ("chiave", "tipo", "bersaglio", "ok", "dettaglio", "heal", "riparato")

    def __init__(self, chiave: str, tipo: str, bersaglio: str, ok: bool, dettaglio: str,
                 heal: str | None = None):
        self.chiave = chiave
        self.tipo = tipo
        self.bersaglio = bersaglio
        self.ok = ok
        self.dettaglio = dettaglio
        self.heal = heal
        self.riparato = False


def controlla_unita(nome: str, utente: bool, esegui) -> Esito:
    pref = "systemctl --user" if utente else "systemctl"
    rc, out, _ = esegui(f"{pref} is-active {nome}")
    ok = out == "active"
    heal = None
    if not ok:
        azione = "start" if nome.endswith(".timer") else "restart"
        heal = f"{pref} {azione} {nome}" if utente else f"sudo -n systemctl {azione} {nome}"
    return Esito(f"unit:{nome}", "unit-utente" if utente else "unit", nome, ok,
                 out or f"rc={rc}", heal)


def controlla_http(url: str, codici: tuple[int, ...], timeout: int, esegui) -> Esito:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            code = r.status
            r.read(256)
        return Esito(f"http:{url}", "http", url, code in codici, f"http {code}")
    except urllib.error.HTTPError as e:
        return Esito(f"http:{url}", "http", url, e.code in codici, f"http {e.code}")
    except Exception as e:  # noqa: BLE001
        return Esito(f"http:{url}", "http", url, False, f"ko {e.__class__.__name__}")


def controlla_docker(nome: str, esegui) -> Esito:
    rc, out, _ = esegui(f"docker inspect -f '{{{{.State.Running}}}}' {nome}")
    ok = out == "true"
    return Esito(f"docker:{nome}", "docker", nome, ok, out or f"rc={rc}",
                 None if ok else f"docker start {nome}")


def controlla_file(path: str, max_age_s: int, adesso: float | None = None) -> Esito:
    adesso = adesso or time.time()
    try:
        age = int(adesso - Path(path).stat().st_mtime)
        return Esito(f"file:{path}", "file", path, age <= max_age_s,
                     f"{age}s fa (max {max_age_s}s)")
    except OSError:
        return Esito(f"file:{path}", "file", path, False, "non leggibile")


def valuta(profilo: dict, esegui=esegui_bash) -> list[Esito]:
    esiti: list[Esito] = []
    for u in profilo.get("unita", []):
        esiti.append(controlla_unita(u, False, esegui))
    for u in profilo.get("unita_utente", []):
        esiti.append(controlla_unita(u, True, esegui))
    for tup in profilo.get("http", []):
        url, codici = tup[0], tup[1]
        timeout = tup[2] if len(tup) > 2 else 15
        esiti.append(controlla_http(url, codici, timeout, esegui))
    for n in profilo.get("docker", []):
        esiti.append(controlla_docker(n, esegui))
    for path, age in profilo.get("file", []):
        esiti.append(controlla_file(path, age))
    return esiti


# --- stato e notifiche --------------------------------------------------------------------

def _leggi_json(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def _invia(attivo: bool):
    if not attivo:
        return None
    try:
        sys.path.insert(0, str(REPO / "ops" / "alerts"))
        import notifica_tg  # noqa: PLC0415  # pyright: ignore[reportMissingImports]
        return notifica_tg.invia
    except Exception:  # noqa: BLE001
        return None


def run_veglia(profilo: dict, host: str, stato_path: Path, esegui=esegui_bash,
               heal: bool = True, alert: bool = True) -> tuple[int, list[Esito], str]:
    """Esegue un giro completo. Ritorna (exit_code, esiti, riassunto_umano)."""
    ts = time.time()
    stato = _leggi_json(stato_path, {})
    stato.setdefault("heal", {})
    stato.setdefault("notif", {})
    esiti = valuta(profilo, esegui)
    log_azioni: list[str] = []

    # 1) riparazione + riverifica
    if heal:
        for e in esiti:
            if e.ok or not e.heal:
                continue
            if ts - float(stato["heal"].get(e.chiave, 0) or 0) <= HEAL_COOLDOWN:
                log_azioni.append(f"cooldown {e.chiave}")
                continue
            rc, _, err = esegui(e.heal, timeout=60)
            stato["heal"][e.chiave] = ts
            log_azioni.append(f"HEAL {e.heal} rc={rc}")
            if rc == 0:
                if e.tipo in ("unit", "unit-utente"):
                    rc2, out2, _ = esegui((("systemctl --user" if e.tipo == "unit-utente"
                                            else "systemctl") + f" is-active {e.bersaglio}"))
                    if out2 == "active":
                        e.ok, e.riparato, e.dettaglio = True, True, f"riparato (era {e.dettaglio})"
                elif e.tipo == "docker":
                    rc2, out2, _ = esegui(f"docker inspect -f '{{{{.State.Running}}}}' {e.bersaglio}")
                    if out2 == "true":
                        e.ok, e.riparato, e.dettaglio = True, True, "riparato (era fermo)"

    # 2) notifiche (rossi persistenti + rientri)
    invia = _invia(alert)
    for e in esiti:
        if not e.ok:
            if invia and ts - float(stato["notif"].get(e.chiave, 0) or 0) > NOTIF_COOLDOWN:
                rc = invia(f"\U0001F534 VEGLIA {host}: {e.chiave} KO — {e.dettaglio}")
                stato["notif"][e.chiave] = ts
                log_azioni.append(f"notifica inviata={rc}")
        elif e.chiave in stato["notif"]:
            if invia:
                invia(f"\u2705 VEGLIA {host}: {e.chiave} rientrato")
            stato["notif"].pop(e.chiave, None)
            log_azioni.append("rientro")

    # 3) persistenza
    ko = [e for e in esiti if not e.ok]
    riassunto = (f"VEGLIA {host}: {len(esiti) - len(ko)}/{len(esiti)} ok"
                 + (f" · ROSSI: {', '.join(e.chiave for e in ko)}" if ko else ""))
    try:
        DIR.mkdir(parents=True, exist_ok=True)
        LAST.write_text(json.dumps({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)),
            "host": host, "tot": len(esiti), "ko": len(ko),
            "riparati": [e.chiave for e in esiti if e.riparato],
            "rossi": [e.chiave for e in esiti if not e.ok],
            "esiti": [{"chiave": e.chiave, "ok": e.ok, "dettaglio": e.dettaglio} for e in esiti],
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        with LOG.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%F %T')} {riassunto}"
                    + (f" | {'; '.join(log_azioni)}" if log_azioni else "") + "\n")
    except Exception:  # noqa: BLE001
        pass
    try:
        stato_path.parent.mkdir(parents=True, exist_ok=True)
        stato_path.write_text(json.dumps(stato, ensure_ascii=False), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    return (1 if ko else 0), esiti, riassunto


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Veglia flotta Denaro (check + auto-heal)")
    ap.add_argument("comando", choices=["check", "run"])
    ap.add_argument("--no-heal", action="store_true")
    ap.add_argument("--no-alert", action="store_true")
    ap.add_argument("--state", default=str(DIR / "state.json"))
    args = ap.parse_args(argv)

    if not os.environ.get("XDG_RUNTIME_DIR"):
        cand = Path(f"/run/user/{os.getuid()}")
        if cand.exists():
            os.environ["XDG_RUNTIME_DIR"] = str(cand)

    host = socket.gethostname()
    nome, profilo = profilo_per_host(host)
    if nome is None or profilo is None:
        print(f"VEGLIA: nodo sconosciuto ({host}) — nessun profilo")
        return 2

    heal = args.comando == "run" and not args.no_heal
    alert = args.comando == "run" and not args.no_alert
    codice, esiti, riassunto = run_veglia(profilo, nome, Path(args.state), heal=heal, alert=alert)

    for e in esiti:
        stato = "FIX " if e.riparato else ("ok  " if e.ok else "KO  ")
        print(f"  [{stato}] {e.chiave} — {e.dettaglio}")
    print(riassunto)
    return codice


if __name__ == "__main__":
    raise SystemExit(main())
