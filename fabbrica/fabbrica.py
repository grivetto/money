#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fabbrica Denaro — il nastro: candidato -> test -> cancello -> (produzione su promozione).

Un tick ogni 3 secondi (timer systemd; cadenza x100 dal 02/10 su direttiva del proprietario).
Fabbrica DISTRIBUITA (direttiva "3 macchine, suddividi i bot"): il master gira qui (mc2);
i worker di nodo (MARCODG1, nuvola) eseguono i controlli LOCALI ogni 10s e li pubblicano in
`shards/<nodo>.json` — il master li legge, quindi nessun controllo remoto blocca il tick.
NON lancia ordini, NON tocca exchange, NON inventa numeri: le azioni che richiedono
giudizio o dati nuovi vengono MARCATE come AZIONE in STATO.md.

Kill-switch: creare il file `STOP` in questa cartella per bloccare i nuovi job
(specgen, gate JEV e lint saltati; il job-store non accoda nuovi job; la coda resta
intatta). Rimuovere `STOP` per ripartire.
Metriche: `metrics.prom` (formato Prometheus) riscritto ad ogni tick.

Vedi README.md per le regole (test prima dei numeri; cancello decide; produzione solo su promozione).
"""
import json
import os
import subprocess
import sys
import time
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
STOP = BASE / "STOP"
METRICS = BASE / "metrics.prom"
SHARDS = BASE / "shards"


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


def read_shard(name):
    """Shard del worker di nodo (fabbrica distribuita). Ritorna (dict|None, eta_s|None)."""
    try:
        d = json.loads((SHARDS / ("%s.json" % name)).read_text())
        return d, time.time() - float(d.get("ts") or 0)
    except Exception:
        return None, None


def shard_summary(name, soglia=180):
    d, age = read_shard(name)
    if age is None:
        return "assente"
    return ("ok %ds" % int(age)) if age <= soglia else ("STALE %ds" % int(age))


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
    """A0-PC: dallo shard del worker nuvola; fallback diretto raro (la rete non blocca il tick)."""
    d, age = read_shard("nuvola")
    code = d.get("a0win") if (d is not None and age is not None and age <= 180) else None
    if code is None:
        if st["ticks"] % 15 == 1:
            rc, out = sh("curl -s -m 3 -o /dev/null -w '%{http_code}' " + A0WIN + "/api/health", timeout=8)
            code = out if rc == 0 else "DOWN"
        else:
            code = "shard-nuvola-stale"
    st["a0win"] = code
    if code == "200":
        (st.setdefault("hb", {}))["a0win"] = time.time()
    if code != "200" and st.get("a0win_last") == "200":
        log("A0-PC: NON raggiungibile (%s) -> AZIONE: verificare" % code)
    st["a0win_last"] = code


def check_a0mc2(st):
    rc, out = sh("curl -s -m 2 -o /dev/null -w '%{http_code}' http://127.0.0.1:50080/api/health", timeout=5)
    code = out.strip() if rc == 0 else "DOWN"
    st["a0mc2"] = code
    if code == "200":
        (st.setdefault("hb", {}))["a0mc2"] = time.time()


def check_banco(st):
    """Banco a secco (MARCODG1): letto dallo shard del worker locale — niente ssh nel tick."""
    d, age = read_shard("marcodg1")
    if d is not None and age is not None and age <= 180:
        st["banco"] = "timer=%s rc=%s ultimo=%s (worker %ds)" % (
            d.get("banco_timer"), d.get("banco_rc"), d.get("banco_last"), int(age))
        if str(d.get("banco_rc")) == "0":
            (st.setdefault("hb", {}))["banco"] = time.time()
    else:
        st["banco"] = "shard worker non aggiornato (%s) — verificare fabbrica-worker su MARCODG1" % (
            "assente" if age is None else "%ds" % int(age))


def check_specgen(st):
    cand = load(BASE / "candidati.json", [])
    nxt = None
    for c in cand:
        spec = REPO / c.get("spec", "")
        if not spec.exists():
            nxt = c
            break
    st["spec_next"] = (nxt or {}).get("id")
    sid = st["spec_next"]
    if sid != st.get("spec_next_id"):
        st["spec_next_id"] = sid
        if sid:
            st["spec_next_since"] = time.time()
        else:
            st.pop("spec_next_since", None)
    if nxt:
        st["spec_next_desc"] = nxt.get("desc", "")
        if not st.get("spec_notified_%s" % nxt.get("id")):
            st["spec_notified_%s" % nxt.get("id")] = True
            log("SPECGEN: prossima spec da materializzare: %s (%s)" % (nxt.get("id"), nxt.get("desc", "")))


def check_jev_gate(st):
    """Gate JEV sulle spec attive (advisory, fail-open): una valutazione per versione (hash).

    Chiave: TYPESAFE_API_KEY dall'ambiente o da ~/.hermes/.env (mai stampata/committata).
    Direzione futura: il verdetto orienta la sistemazione delle spec PRIMA del dispatch.
    """
    import hashlib

    try:
        if "TYPESAFE_API_KEY" not in os.environ:
            envf = Path.home() / ".hermes" / ".env"
            if envf.exists():
                for ln in envf.read_text(errors="replace").splitlines():
                    if ln.startswith("TYPESAFE_API_KEY="):
                        os.environ["TYPESAFE_API_KEY"] = ln.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        sys.path.insert(0, str(REPO / "src"))
        from money.jev import spec_gate  # lazy: se non importabile -> fail-open
    except Exception as e:  # noqa: BLE001
        st["jev_gate"] = "non disponibile (%s)" % type(e).__name__
        return

    concluse = _spec_concluse()
    results = st.get("jev_gate_results") or {}
    for sp in sorted((REPO / "coda_catena").glob("P*.md")):
        if sp.name in concluse:
            results.pop(sp.name, None)  # spec conclusa: fuori dal gate (retrofit 06/10)
            continue
        try:
            raw = sp.read_bytes()
        except Exception:
            continue
        h = hashlib.sha256(raw).hexdigest()[:16]
        if (results.get(sp.name) or {}).get("hash") == h:
            continue
        out = spec_gate(raw.decode("utf-8", "replace"))
        if out is None:
            continue  # fail-open: si ritenta al prossimo tick
        flags = []
        if out.get("self_contained") is not None and out["self_contained"] < 0.80:
            flags.append("spec non autosufficiente")
        if out.get("test_falsifiable") is not None and out["test_falsifiable"] < 0.80:
            flags.append("accettazione debole")
        if out.get("non_trading") is not None and out["non_trading"] < 0.50:
            flags.append("possibile impatto trading")
        if out.get("gap") and out.get("gap") != "none":
            flags.append("gap:%s" % out["gap"])
        results[sp.name] = {
            "hash": h, "ts": now(),
            "sc": out.get("self_contained"), "tf": out.get("test_falsifiable"), "flags": flags,
        }
        log("GATE JEV %s: sc=%s tf=%s -> %s" % (
            sp.name, _fmt(out.get("self_contained")), _fmt(out.get("test_falsifiable")),
            ("DA SISTEMARE: " + "; ".join(flags)) if flags else "ok"))
    st["jev_gate_results"] = results


_JOBSTORE = None


def _jobstore():
    """Classe JobStore da fabbrica/jobs.py (import per percorso, lazy + cached).

    Fail-open sul monitoraggio: se il modulo manca, il tick resta vivo — il job-store
    NON e' sul percorso ordini.
    """
    global _JOBSTORE
    if _JOBSTORE is None:
        import importlib.util
        sp = importlib.util.spec_from_file_location("fabbrica_jobs", BASE / "jobs.py")
        assert sp is not None and sp.loader is not None
        mod = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(mod)
        _JOBSTORE = mod.JobStore
    return _JOBSTORE


def _spec_concluse():
    """Spec fuori dal gate di dispatch (concluse o non-esperimenti): `coda_catena/CONCLUSE.md`.

    Una riga per spec, formato `- <file>.md — motivo`. Le righe non riconosciute vengono
    ignorate. Fail-open: file assente -> insieme vuoto (il comportamento di prima).
    """
    out = set()
    try:
        txt = (REPO / "coda_catena" / "CONCLUSE.md").read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return out
    for ln in txt.splitlines():
        ln = ln.strip()
        if ln.startswith("- "):
            nome = ln[2:].split(" ", 1)[0].strip()
            if nome.endswith(".md"):
                out.add(nome)
    return out


def _inbox_size(name):
    p = BASE / "inbox" / name
    try:
        return p.stat().st_size if p.is_file() else None
    except Exception:  # noqa: BLE001
        return None


def _fmt_jobs(j):
    if not isinstance(j, dict):
        return str(j or "(in attesa)")
    parts = ["queued %d" % j.get("queued", 0), "running %d" % j.get("running", 0),
             "failed %d" % j.get("failed", 0), "done %d totali" % j.get("done", 0)]
    age = j.get("oldest_queued_age_s")
    if age:
        parts[0] += " (piu' vecchio %ds)" % age
    return " · ".join(parts)


def _fmt_lint(results):
    if not results:
        return "(in attesa)"
    bad = sorted(k for k, r in results.items() if r.get("missing"))
    ok = len(results) - len(bad)
    if not bad:
        return "%d/%d ok" % (ok, len(results))
    return "%d/%d ok (da sistemare: %s)" % (ok, len(results), ", ".join(b[:-3] for b in bad))


def check_jobs(st):
    """Job-store nel tick (Incremento 1 del piano hardening, 03/10/2026).

    - accoda le AZIONI rilevate dal nastro (spec da materializzare, fix spec flaggate
      da gate JEV/lint, file in inbox) con idempotency_key STABILE: la dedup vive nel
      job-store e sopravvive ai riavvii (mai doppioni);
    - chiude da solo i job VERIFICABILI: spec materializzata, spec aggiornata (hash
      nuovo), file inbox rimosso, spec in `coda_catena/CONCLUSE.md` (fuori dal gate);
    - espone le statistiche in state.json e metrics.prom (factory_jobs_*).
    Kill-switch: con STOP presente NON accoda nuovi job (la coda resta intatta).
    """
    try:
        store = _jobstore()(str(BASE / "jobs.db"))
    except Exception as e:  # noqa: BLE001
        st["jobs"] = "non disponibile (%s)" % type(e).__name__
        return
    try:
        now_ms = int(time.time() * 1000)
        concluse = _spec_concluse()
        if not st.get("kill_switch"):
            sid = st.get("spec_next")
            if sid:
                store.enqueue("spec_materialize",
                              {"spec_id": sid, "desc": st.get("spec_next_desc", "")},
                              "spec_materialize:%s" % sid, now_ms=now_ms)
            for name, r in (st.get("jev_gate_results") or {}).items():
                if r.get("flags") and name not in concluse:
                    store.enqueue("spec_fix",
                                  {"spec": name, "hash": r.get("hash"), "via": "jev",
                                   "flags": r.get("flags")},
                                  "spec_fix:jev:%s:%s" % (name, r.get("hash")), now_ms=now_ms)
            for name, r in (st.get("lint_results") or {}).items():
                if r.get("missing") and name not in concluse:
                    store.enqueue("spec_fix",
                                  {"spec": name, "hash": r.get("hash"), "via": "lint",
                                   "missing": r.get("missing")},
                                  "spec_fix:lint:%s:%s" % (name, r.get("hash")), now_ms=now_ms)
            inbox = BASE / "inbox"
            if inbox.exists():
                for p in sorted(inbox.glob("*")):
                    if p.is_file() and p.name != ".gitkeep":
                        store.enqueue("inbox_file", {"file": p.name, "size": p.stat().st_size},
                                      "inbox:%s:%s" % (p.name, p.stat().st_size), now_ms=now_ms)
        for j in store.pending(now_ms=now_ms):
            p = j.get("payload") or {}
            done = False
            if j["kind"] == "spec_materialize":
                for c in load(BASE / "candidati.json", []):
                    if c.get("id") == p.get("spec_id"):
                        done = (REPO / str(c.get("spec", ""))).exists()
                        break
                else:
                    done = True  # voce sparita dalla coda: il job non ha piu' oggetto
            elif j["kind"] == "spec_fix":
                if p.get("spec") in concluse:
                    done = True  # spec conclusa (retrofit 06/10): il fix non ha piu' oggetto
                else:
                    if p.get("via") == "jev":
                        cur = (st.get("jev_gate_results") or {}).get(p.get("spec")) or {}
                    else:
                        cur = (st.get("lint_results") or {}).get(p.get("spec")) or {}
                    done = cur.get("hash") != p.get("hash")  # spec aggiornata (o sparita)
            elif j["kind"] == "inbox_file":
                size = _inbox_size(p.get("file"))
                done = size is None or size != p.get("size")
            if done:
                store.complete(j["job_id"], now_ms=now_ms)
        stats = store.stats(now_ms=now_ms)
        age = stats.get("oldest_queued_age_ms")
        st["jobs"] = {
            "queued": stats["queued"], "running": stats["running"],
            "done": stats["done"], "failed": stats["failed"],
            "oldest_queued_age_s": int(age / 1000) if age is not None else None,
        }
    except Exception as e:  # noqa: BLE001
        st["jobs"] = "errore (%s: %s)" % (type(e).__name__, e)
    finally:
        try:
            store.close()
        except Exception:  # noqa: BLE001
            pass


def check_lint(st):
    """Lint strutturale deterministico delle spec (7 blocchi del formato-contratto).

    Offline (src/money/spec_lint.py): un esito per versione (hash). Advisory: orienta
    la SISTEMAZIONE delle spec prima del dispatch a un esecutore 'freddo'.
    """
    import hashlib
    try:
        sys.path.insert(0, str(REPO / "src"))
        from money.spec_lint import lint_text, missing
    except Exception as e:  # noqa: BLE001
        st["lint"] = "non disponibile (%s)" % type(e).__name__
        return
    concluse = _spec_concluse()
    results = st.get("lint_results") or {}
    for sp in sorted((REPO / "coda_catena").glob("*.md")):
        if sp.name in ("README.md", "CONCLUSE.md"):
            results.pop(sp.name, None)  # non sono spec: fuori anche dal lint
            continue
        if sp.name in concluse:
            results.pop(sp.name, None)  # spec conclusa: fuori dal gate (retrofit 06/10)
            continue
        try:
            raw = sp.read_bytes()
        except Exception:  # noqa: BLE001
            continue
        h = hashlib.sha256(raw).hexdigest()[:16]
        if (results.get(sp.name) or {}).get("hash") == h:
            continue
        miss = missing(lint_text(raw.decode("utf-8", "replace")))
        results[sp.name] = {"hash": h, "ts": now(), "ok": not miss, "missing": miss}
        log("LINT %s: %s" % (sp.name, "7/7 ok" if not miss else "mancano: " + ", ".join(miss)))
    st["lint_results"] = results


def kill_switch_active():
    """True se il freno d'emergenza della fabbrica e' inserito (file STOP presente)."""
    return STOP.exists()


def write_metrics(st):
    """Scrive metrics.prom (formato Prometheus) con le metriche minime del nastro.

    Consumo previsto (prossimo cantiere): scrape da Prometheus/Zabbix su MARCODG1.
    """
    now_ts = time.time()
    lines = [
        "# Fabbrica Denaro — metriche del nastro (riscritte ad ogni tick)",
        "factory_last_successful_tick_timestamp %d" % int(now_ts),
        "factory_kill_switch %d" % (1 if kill_switch_active() else 0),
    ]
    hb = st.get("hb") or {}
    for comp in ("a0win", "a0mc2", "banco"):
        ts = hb.get(comp)
        if ts:
            lines.append('factory_heartbeat_age_seconds{component="%s"} %d' % (comp, int(now_ts - float(ts))))
    for nodo in ("marcodg1", "nuvola"):
        _d, _age = read_shard(nodo)
        if _age is not None:
            lines.append('factory_shard_age_seconds{node="%s"} %d' % (nodo, int(_age)))
    for k, r in sorted((st.get("jev_gate_results") or {}).items()):
        ts = r.get("ts") or ""
        try:
            t = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
            lines.append('factory_gate_age_seconds{spec="%s"} %d' % (k.replace(".md", ""), int(now_ts - t)))
        except Exception:
            continue
    q = st.get("spec_next_since")
    if q:
        lines.append('factory_queue_oldest_age_seconds{kind="spec"} %d' % int(now_ts - float(q)))
    jobs = st.get("jobs")
    if isinstance(jobs, dict):
        lines.append("factory_jobs_queued %d" % jobs.get("queued", 0))
        lines.append("factory_jobs_running %d" % jobs.get("running", 0))
        lines.append("factory_jobs_done_total %d" % jobs.get("done", 0))
        lines.append("factory_jobs_failed %d" % jobs.get("failed", 0))
        if jobs.get("oldest_queued_age_s") is not None:
            lines.append("factory_jobs_oldest_queued_age_seconds %d" % jobs["oldest_queued_age_s"])
    lint = st.get("lint_results") or {}
    if lint:
        lines.append("factory_specs_lint_bad %d" % sum(1 for r in lint.values() if r.get("missing")))
    METRICS.write_text("\n".join(lines) + "\n")


def _fmt(x):
    return "n/d" if x is None else ("%.2f" % float(x))


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
        "- ultimo tiro: %s (tiro n. %s, cadenza 3s via timer — x100 dal 02/10; master + worker nodi @5s)" % (now(), st.get("ticks", 0)),
        "- kill-switch: %s" % ("ATTIVO — nuovi job bloccati (file STOP presente)" if st.get("kill_switch") else "off"),
        "- canale DSH: %s voci totali, nuove dall'ultimo tiro: %s" % (st.get("dsh_heads"), st.get("dsh_new")),
        "- handoff P2: %s | manifest: %s" % (", ".join(st.get("p2_handoff_files") or []) or "(vuoto)",
                                             st.get("p2_handoff_manifest", "-")),
        "- P2: %s" % st.get("p2"),
        "- A0-PC: HTTP %s" % st.get("a0win"),
        "- A0-MC2: HTTP %s" % st.get("a0mc2"),
        "- banco MARCODG1: %s" % st.get("banco"),
        "- worker nodi (shard @10s): MARCODG1 %s | nuvola %s" % (shard_summary("marcodg1"), shard_summary("nuvola")),
        "- prossima spec da materializzare: %s %s" % (st.get("spec_next") or "(nessuna)",
                                                      "— " + st.get("spec_next_desc", "") if st.get("spec_next") else ""),
        "- gate JEV: %s" % ("; ".join(
            "%s %s/%s%s" % (k[:-3], _fmt(r.get("sc")), _fmt(r.get("tf")),
                            "" if not r.get("flags") else " DA SISTEMARE (" + ", ".join(r["flags"]) + ")")
            for k, r in sorted((st.get("jev_gate_results") or {}).items())) or "(in attesa)"),
        "- lint spec: %s" % _fmt_lint(st.get("lint_results")),
        "- job-store: %s" % _fmt_jobs(st.get("jobs")),
        "- control-plane: money@%s · STATO derivato, non fonte di verità" % st.get("control_rev", "?"),
        "- inbox: %s" % (", ".join(st.get("inbox") or []) or "(vuoto)"),
        "",
        "## Azioni in attesa (per owner)",
        "- Lane 03/10: P14 misurata e **archiviata** (universo ampio, 7/8 KO) | C1REV consegnato e integrato (`scripts/canary_review.py`, 5 test; deploy MARCODG1) | protocollo di consegna → DSH-win (attesa turno owner) | **CANARY C1 in validazione** (review 15/10)",
        "- P10 insufficiente | P14 archiviata | P2/P6/P11/P13 archiviate | E1/P9 integrati | job-store + lint cablati nel tick",
        "- DSH-win: REQ protocollo di consegna inviato (requests.md) — in attesa di turno owner; A0-win e A0-mc2: consegne 03/10 integrate (review Hermes)",
        "",
        "_Regole: test prima dei numeri; il cancello decide; produzione solo su promozione. Kill-switch: file fabbrica/STOP._",
    ]
    STATEDOC.write_text("\n".join(lines) + "\n")


def main():
    st = load(STATE, {})
    st["ticks"] = int(st.get("ticks", 0)) + 1
    st["last_ts"] = now()
    st["kill_switch"] = kill_switch_active()
    check_dsh(st)
    check_handoff_p2(st)
    check_p2(st)
    check_a0win(st)
    check_a0mc2(st)
    # [01/10 sera] banco: continuo dallo shard del worker MARCODG1 (niente ssh nel tick).
    check_banco(st)
    if st["kill_switch"]:
        log("KILL-SWITCH attivo: nuovi job bloccati (specgen + gate JEV + lint saltati, coda intatta)")
    else:
        check_specgen(st)
        check_jev_gate(st)
        check_lint(st)
    check_jobs(st)
    check_inbox(st)
    rc, out = sh("git -C %s rev-parse --short HEAD" % REPO, timeout=5)
    st["control_rev"] = out.strip() if rc == 0 else "?"
    save(STATE, st)
    write_metrics(st)
    write_stato(st)
    log("tick completato (n. %d)" % st["ticks"])


if __name__ == "__main__":
    main()
