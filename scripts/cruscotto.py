#!/usr/bin/env python3
"""cruscotto.py — genera il cruscotto "andamento progetto" (widget HTML per la chat).

Raccoglie le fonti vive e produce report/cruscotto.html: un file autonomo
(dati incorporati, nessuna richiesta di rete al momento della visualizzazione).

Fonti (sola lettura):
  - fabbrica/state.json, fabbrica/STATO.md, fabbrica/jobs.db, fabbrica/log/watchdog.log
  - prove/REGISTRO_ESPERIMENTI.md (esperimenti: stato + note)
  - fabbrica/candidati.json
  - MARCODG1 via ssh: aggregatore /api/infra.json + ultima riga canary.log (con cache locale)

Uso:
    python3 scripts/cruscotto.py            # genera report/cruscotto.html
    python3 scripts/cruscotto.py --print    # in piu', riassunto testuale su stdout

Solo lettura: non tocca capitale, servizi o repo. Scrive SOLO in report/ e data/ (gitignored).
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

MONEY = Path(__file__).resolve().parent.parent
FABBRICA = MONEY / "fabbrica"
PROVE = MONEY / "prove"
BRIDGE = Path("/home/sergio/hermes_bridge/dsh")
OUT = MONEY / "report" / "cruscotto.html"
CACHE = MONEY / "data" / "_cruscotto_remote.json"
REMOTE = "MARCODG1"

# ---------------------------------------------------------------- utilities


def load_json(path, attempts=3, delay=0.4):
    for i in range(attempts):
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            if i == attempts - 1:
                raise
            time.sleep(delay)


def read_text(p, default=""):
    try:
        return Path(p).read_text(encoding="utf-8")
    except Exception:
        return default


def it(x, dec=2):
    """Numero in formato italiano: 1.100,31"""
    s = f"{x:,.{dec}f}"
    return s.replace(",", "\u00a7").replace(".", ",").replace("\u00a7", ".")


def age_str(sec):
    if sec is None:
        return "n/d"
    sec = max(0, int(sec))
    if sec < 60:
        return f"{sec}s"
    if sec < 3600:
        return f"{sec // 60}m"
    if sec < 86400:
        return f"{sec // 3600}h{(sec % 3600) // 60:02d}m"
    return f"{sec // 86400}g{(sec % 86400) // 3600:02d}h"


def md_mini(s):
    s = html.escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return s


def clean(s):
    s = s.replace("*", "").replace("`", "")
    return re.sub(r"\s+", " ", s).strip()


def dot(cls):
    return f'<span class="dot {cls}"></span>'


# ---------------------------------------------------------------- remote fetch


def fetch_remote():
    """Ritorna (data, stale). Prova ssh -> cache; se fallisce del tutto, (None, True)."""
    cmd = (
        "curl -s -m 12 http://127.0.0.1:8912/api/infra.json; "
        "echo; echo '===CANARY==='; tail -n 2 /home/marco/canary/canary.log 2>/dev/null"
    )
    try:
        p = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=8", "-o", "BatchMode=yes", REMOTE, cmd],
            capture_output=True, text=True, timeout=35,
        )
        head, _, tail = p.stdout.partition("===CANARY===")
        infra = json.loads(head)
        cache = {"infra": infra, "canary_tail": tail.strip(), "fetched_at": time.time()}
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cache), encoding="utf-8")
        return cache, False
    except Exception:
        try:
            return json.loads(CACHE.read_text(encoding="utf-8")), True
        except Exception:
            return None, True


# ---------------------------------------------------------------- registro


def classify(rest: str) -> str:
    r = rest.lower()
    # Il verdetto esplicito (es. "verdetto 'archiviato'") ha la priorita': il resto
    # della nota puo' citare altri esperimenti con parole-verdetto diverse.
    m = re.search(r"verdetto\s*\*\*?'?\s*([a-z]+)", r)
    if m:
        v = m.group(1)
        return {"archiviato": "archiviata", "archiviata": "archiviata"}.get(v, v)
    if "insufficiente" in r:
        return "insufficiente"
    if "descr" in r and "solida" in r:
        return "descrittiva"
    if "parcheggiata" in r:
        return "parcheggiata"
    if "chiusa" in r:
        return "chiusa"
    if "archiviat" in r:
        return "archiviata"
    if "integrato" in r or "integrata" in r:
        return "integrata"
    if "n/d" in r:
        return "esito n/d"
    if "misurata" in r:
        return "misurata"
    return "in corso"


def parse_registro():
    txt = read_text(PROVE / "REGISTRO_ESPERIMENTI.md")
    sections = {}
    cur = None
    for line in txt.splitlines():
        if line.startswith("## "):
            cur = line[3:].strip()
            sections.setdefault(cur, [])
            continue
        if cur is None or not line.startswith("- **"):
            continue
        m = re.match(r"- \*\*(.+?)\*\*(.*)$", line)
        if not m:
            continue
        id_title, rest = m.group(1), m.group(2)
        if " \u2014 " in id_title:
            rid, title = id_title.split(" \u2014 ", 1)
        else:
            rid, title = id_title, ""
        note = rest.split("\u2192", 1)[1] if "\u2192" in rest else rest
        note = clean(note)
        if len(note) > 150:
            note = note[:147].rstrip() + "\u2026"
        sections[cur].append({
            "id": rid.strip(), "title": title.strip(),
            "status": classify(rest), "note": note,
        })
    mvn = re.search(r"dal 2026-09-30 in poi:\s*\*\*(\d+)\*\*", txt, re.S)
    varianti = int(mvn.group(1)) if mvn else None
    return sections, varianti


# ---------------------------------------------------------------- fabbrica


def fabbrica_data(now_epoch):
    st = {}
    try:
        st = load_json(FABBRICA / "state.json")
    except Exception:
        pass

    age = None
    last = st.get("last_ts")
    if last:
        try:
            dt = datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            age = now_epoch - dt.timestamp()
        except Exception:
            pass

    jobs = {}
    oldest_job = None
    try:
        con = sqlite3.connect(f"file:{FABBRICA / 'jobs.db'}?mode=ro", uri=True)
        jobs = dict(con.execute("SELECT state, COUNT(*) FROM jobs GROUP BY state").fetchall())
        row = con.execute("SELECT MIN(created_at) FROM jobs WHERE state='queued'").fetchone()
        oldest_job = (row[0] / 1000.0) if row and row[0] else None
        con.close()
    except Exception:
        pass

    stato = read_text(FABBRICA / "STATO.md")
    m = re.search(r"worker nodi.*?:\s*(.+)", stato)
    workers = clean(m.group(1)) if m else "n/d"
    m = re.search(r"lint spec:\s*(\d+/\d+) ok", stato)
    lint = m.group(1) if m else "n/d"

    azioni = []
    mm = re.search(r"## Azioni in attesa \(per owner\)\n(.*?)\n_Regole", stato, re.S)
    if mm:
        azioni = [l[2:].strip() for l in mm.group(1).splitlines() if l.strip().startswith("- ")]

    wlog = [l for l in read_text(FABBRICA / "log" / "watchdog.log").splitlines() if l.strip()]
    wlast = wlog[-1] if wlog else ""
    wn = len(wlog)

    banco = st.get("banco") or ""
    mb = re.search(r"timer=(\w+)\s+rc=(-?\d+).*?worker\s+(\d+s)", banco)
    banco_short = f"timer {mb.group(1)} \u00b7 rc={mb.group(2)} \u00b7 worker {mb.group(3)}" if mb else (banco or "n/d")

    hb = st.get("hb") or {}
    a0win_age = (now_epoch - hb["a0win"]) if hb.get("a0win") else None

    dsh = {}
    for name in ("results.md", "requests.md"):
        p = BRIDGE / name
        try:
            dsh[name] = p.stat().st_mtime
        except Exception:
            dsh[name] = None

    return {
        "st": st, "tick_age": age, "jobs": jobs, "oldest_job": oldest_job,
        "workers": workers, "lint": lint, "azioni": azioni,
        "wlast": wlast, "wn": wn, "banco_short": banco_short,
        "a0win_age": a0win_age, "dsh_files": dsh,
    }


def git_head(repo):
    try:
        return subprocess.run(
            ["git", "-C", str(repo), "log", "-1", "--format=%h %s"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
    except Exception:
        return ""


# ---------------------------------------------------------------- svg sparkline


def sparkline(points, w=620, h=56, pad=3):
    if len(points) < 2:
        return ""
    lo, hi = min(points), max(points)
    rng = (hi - lo) or 1e-9
    step = (w - 2 * pad) / (len(points) - 1)
    pts = " ".join(
        f"{pad + i * step:.1f},{h - pad - ((v - lo) / rng) * (h - 2 * pad):.1f}"
        for i, v in enumerate(points)
    )
    return (
        f'<svg class="sp" width="100%" height="{h}" viewBox="0 0 {w} {h}" '
        f'preserveAspectRatio="none"><polyline fill="none" stroke="var(--accent)" '
        f'stroke-width="2" points="{pts}"/></svg>'
    )


# ---------------------------------------------------------------- render

BADGE = {
    "integrata":    ("b-prod", "in produzione"),
    "archiviata":   ("b-arch", "archiviata"),
    "insufficiente": ("b-ins", "insufficiente"),
    "descrittiva":  ("b-desc", "descrittiva"),
    "parcheggiata": ("b-park", "parcheggiata"),
    "chiusa":       ("b-park", "chiusa"),
    "esito n/d":    ("b-cur", "esito n/d"),
    "misurata":     ("b-desc", "misurata"),
    "in corso":     ("b-cur", "in corso"),
}


def badge(status):
    cls, label = BADGE.get(status, ("b-cur", status))
    return f'<span class="badge {cls}">{label}</span>'


CSS = """
*{box-sizing:border-box}
.wrap{max-width:940px}
.hd{display:flex;align-items:baseline;gap:10px;margin:0 0 10px;flex-wrap:wrap}
.hd .t{font-size:15px;font-weight:700;letter-spacing:.02em}
.hd .ts{color:var(--muted-foreground);font-size:12px}
.hd button{margin-left:auto;font:inherit;font-size:12px;color:var(--foreground);background:color-mix(in srgb,var(--accent) 12%,transparent);border:1px solid var(--border);border-radius:8px;padding:4px 12px;cursor:pointer}
.hd button:hover{border-color:var(--accent)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(285px,1fr));gap:10px;align-items:start}
.card{border:1px solid var(--border);border-radius:12px;padding:12px 14px;background:var(--card)}
.card.wide{grid-column:1/-1}
.card h2{font-size:11px;letter-spacing:.09em;text-transform:uppercase;color:var(--muted-foreground);margin:0 0 8px;font-weight:600}
.big{font-size:27px;font-weight:700;line-height:1.1}
.sub{color:var(--muted-foreground);font-size:11.5px;margin-top:3px;line-height:1.45}
.row{display:flex;justify-content:space-between;gap:8px;font-size:12.5px;padding:3.5px 0;border-bottom:1px dashed var(--border)}
.row:last-child{border-bottom:0}
.row .k{color:var(--muted-foreground)}
.row .v{text-align:right}
.dot{width:7px;height:7px;border-radius:50%;display:inline-block;margin-right:5px;vertical-align:middle}
.d-ok{background:#3fb950}.d-warn{background:#d29922}.d-bad{background:#f85149}.d-off{background:#8b949e}
.spark{margin:6px 0 2px}
.spark .lab{display:flex;justify-content:space-between;color:var(--muted-foreground);font-size:10.5px;gap:6px}
.sp{display:block}
table{width:100%;border-collapse:collapse;font-size:12.5px}
td{padding:5px 8px 5px 0;border-bottom:1px solid var(--border);vertical-align:top}
tr:last-child td{border-bottom:0}
.t2{font-weight:600;line-height:1.3}
.n{color:var(--muted-foreground);font-size:11.5px;margin-top:1px;line-height:1.4}
.st{white-space:nowrap;text-align:right}
th{color:var(--muted-foreground);font-weight:500;font-size:10.5px;text-transform:uppercase;letter-spacing:.07em;text-align:left;padding:2px 8px 4px 0;border-bottom:1px solid var(--border)}
.badge{display:inline-block;padding:0 7px;border-radius:999px;font-size:10.5px;border:1px solid;line-height:17px;white-space:nowrap}
.b-prod{color:#3fb950;border-color:color-mix(in srgb,#3fb950 45%,transparent)}
.b-arch{color:var(--muted-foreground);border-color:var(--border)}
.b-ins{color:#d29922;border-color:color-mix(in srgb,#d29922 45%,transparent)}
.b-desc{color:#58a6ff;border-color:color-mix(in srgb,#58a6ff 45%,transparent)}
.b-park{color:#bc8cff;border-color:color-mix(in srgb,#bc8cff 45%,transparent)}
.b-cur{color:var(--accent);border-color:color-mix(in srgb,var(--accent) 45%,transparent)}
.chip{display:inline-flex;align-items:center;gap:5px;padding:1px 9px;border-radius:999px;border:1px solid var(--border);font-size:11.5px;margin:0 5px 5px 0;white-space:nowrap;color:var(--foreground)}
.cols{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:6px}
.col{flex:1 1 240px;min-width:200px}
.k2{color:var(--muted-foreground);font-size:10.5px;text-transform:uppercase;letter-spacing:.07em;margin-bottom:4px;font-weight:600}
ul.az{margin:2px 0 0;padding-left:16px}
ul.az li{font-size:12.5px;margin:4px 0;line-height:1.45}
.foot{color:var(--muted-foreground);font-size:10.5px;margin-top:10px;line-height:1.5}
sect{display:block}
.mid{font-size:12.5px;line-height:1.5}
"""


def render(now, now_epoch, cache, stale, fab, sections, varianti, money_head, aot_head):
    infra = (cache or {}).get("infra") or {}
    canary_tail = (cache or {}).get("canary_tail") or ""
    fetched_age = (now_epoch - cache["fetched_at"]) if cache and cache.get("fetched_at") else None

    # ---- soldi
    tot = infra.get("total_equity")
    eb = infra.get("equity_breakdown") or {}
    main_eur = (eb.get("OKX main") or {}).get("eur")
    sub_eur = (eb.get("OKX mc2sub1") or {}).get("eur")
    tot_s = it(tot) if isinstance(tot, (int, float)) else "n/d"

    trend = [p for p in (infra.get("trend") or []) if isinstance(p.get("equity"), (int, float))]
    pts = [p["equity"] for p in trend]
    if len(pts) > 170:
        step = len(pts) // 170
        pts = pts[::step]
        if pts[-1] != trend[-1]["equity"]:
            pts.append(trend[-1]["equity"])
    if len(pts) >= 2:
        delta = pts[-1] - pts[0]
        dur = (trend[-1]["ts"] - trend[0]["ts"])
        spark = sparkline(pts)
        lab = (
            f'<div class="lab"><span>{it(pts[0])} \u20ac</span>'
            f'<span>\u0394 {("+" if delta >= 0 else "")}{it(delta)} \u20ac su {age_str(dur)}</span>'
            f'<span>{it(pts[-1])} \u20ac ora</span></div>'
        )
    else:
        spark, lab = "", ""
        delta = None

    # canary net
    net = funding = upl = None
    lines = [l for l in canary_tail.splitlines() if l.strip()]
    if lines:
        l = lines[-1]
        m = re.search(r"net stimato.*?([+-]?\d+\.\d+)\s*USDC", l)
        if m:
            net = float(m.group(1))
        m = re.search(r"funding\s*([+-]?\d+\.\d+)", l)
        if m:
            funding = float(m.group(1))
        m = re.search(r"upl\s*([+-]?\d+\.\d+)", l)
        if m:
            upl = float(m.group(1))
    can = infra.get("canary") or {}
    if funding is None and isinstance(can.get("funding"), (int, float)):
        funding = can["funding"]
    net_dot = "d-ok" if isinstance(net, (int, float)) and net >= 0 else ("d-bad" if isinstance(net, (int, float)) else "d-off")
    net_s = f"{net:+.4f} USDC" if isinstance(net, (int, float)) else "n/d"
    fund_s = f"{funding:+.4f}" if isinstance(funding, (int, float)) else "n/d"
    mark_s = f"{can.get('mark'):.5f}" if isinstance(can.get("mark"), (int, float)) else "n/d"
    can_sub = (
        f"{net_dot and dot(net_dot)}net stimato {net_s} \u00b7 funding {fund_s} USDC<br>"
        f"mark {mark_s} \u00b7 aperto dal 30/09 \u2014 review 15/10"
    )

    soldi_card = f"""
<div class="card">
 <h2>Soldi \u00b7 live (OKX)</h2>
 <div class="big">{tot_s} \u20ac</div>
 <div class="sub">OKX main {it(main_eur) if isinstance(main_eur,(int,float)) else 'n/d'} \u20ac \u00b7 mc2sub1 {it(sub_eur,2) if isinstance(sub_eur,(int,float)) else 'n/d'} \u20ac \u00b7 resto 0,00</div>
 <div class="spark">{spark}{lab}</div>
 <div class="row"><span class="k">Canary C1 \u00b7 DOGE spot+perp</span><span class="v">{net_s.split(' ')[0]} USDC net</span></div>
 <div class="row"><span class="k">funding cumulato</span><span class="v">{fund_s} USDC</span></div>
 <div class="sub">Contributi esterni (deposito +1.000 \u20ac del 03/10) esclusi dal \u0394. Paper escluso da equity e P&amp;L.</div>
</div>"""

    # ---- fabbrica
    st = fab["st"]
    onoff = st.get("kill_switch")
    ks = (dot("d-off") + "OFF", "d-ok") if onoff is False else (dot("d-bad") + "ON", "d-bad")
    tick_age_s = age_str(fab["tick_age"]) if fab["tick_age"] is not None else "n/d"
    tick_dot = "d-ok" if (fab["tick_age"] or 999) < 30 else "d-warn"
    a0mc2 = st.get("a0mc2") or "n/d"
    a0win = st.get("a0win") or "n/d"
    a0win_dot = "d-ok" if a0win == "200" else "d-bad"
    dsh_heads = st.get("dsh_heads")
    dsh_new = st.get("dsh_new")
    dsh_res = fab["dsh_files"].get("results.md")
    dsh_req = fab["dsh_files"].get("requests.md")
    dsh_mt = ""
    if dsh_res:
        dsh_mt = f"ultimo {datetime.fromtimestamp(dsh_res).strftime('%d/%m %H:%M')}"
    queued = fab["jobs"].get("queued", 0)
    runj = fab["jobs"].get("running", 0)
    okj = fab["jobs"].get("done", 0)
    failj = fab["jobs"].get("failed", 0)
    oldest_s = age_str(now_epoch - fab["oldest_job"]) if fab["oldest_job"] else "n/d"
    wlast_s = clean(fab["wlast"])
    if wlast_s:
        mw = re.match(r"\[(.+?Z)\]\s*(.*)", wlast_s)
        if mw:
            try:
                dt = datetime.strptime(mw.group(1), "%Y-%m-%dT%H:%M:%SZ")
                wlast_s = f"{dt.strftime('%d/%m %H:%M')}Z \u00b7 {mw.group(2)[:64]}"
            except Exception:
                pass
        wdot = "d-warn" if "illeggibile" in wlast_s or "DOWN" in wlast_s else "d-ok"
        wshow = f"{dot(wdot)}{wlast_s}"
    else:
        wshow = f"{dot('d-ok')}nessuna anomalia registrata"
    a0win_s = f"{a0win}"
    if a0win != "200" and fab["a0win_age"]:
        a0win_s += f" (da {age_str(fab['a0win_age'])})"
    workers_s = html.escape(fab["workers"].replace("|", "\u00b7")) if fab["workers"] != "n/d" else "n/d"

    fab_card = f"""
<div class="card">
 <h2>Fabbrica \u00b7 il nastro</h2>
 <div class="row"><span class="k">Ultimo tiro</span><span class="v">{dot(tick_dot)}n. {st.get('ticks','?')} \u00b7 {tick_age_s} fa</span></div>
 <div class="row"><span class="k">Kill-switch</span><span class="v">{ks[0]}</span></div>
 <div class="row"><span class="k">Canale DSH</span><span class="v">{dsh_heads if dsh_heads is not None else '?'} voci \u00b7 {dsh_new if dsh_new is not None else '?'} nuove</span></div>
 <div class="row"><span class="k">A0-mc2 / A0-win</span><span class="v">{dot('d-ok')}{a0mc2} \u00b7 {dot(a0win_dot)}{a0win_s}</span></div>
 <div class="row"><span class="k">Banco MARCODG1</span><span class="v">{banco_dot(fab)} {fab['banco_short']}</span></div>
 <div class="row"><span class="k">Worker nodi</span><span class="v">{workers_s}</span></div>
 <div class="row"><span class="k">Job-store</span><span class="v">{queued} in coda \u00b7 {runj} in corso \u00b7 pi\u00f9 vecchio {oldest_s}</span></div>
 <div class="row"><span class="k">Lint spec</span><span class="v">{fab['lint']} ok</span></div>
 <div class="row"><span class="k">Watchdog</span><span class="v" style="max-width:62%">{wshow}</span></div>
</div>"""

    # ---- ricerca
    counts = {}
    for secname, entries in sections.items():
        for e in entries:
            counts[e["status"]] = counts.get(e["status"], 0) + 1
    # chips
    order = ["integrata", "archiviata", "insufficiente", "descrittiva", "parcheggiata", "chiusa", "esito n/d", "misurata", "in corso"]
    chips = ""
    for sname in order:
        if counts.get(sname):
            cls, label = BADGE.get(sname, ("b-cur", sname))
            chips += f'<span class="chip"><span class="badge {cls}">{counts[sname]}</span>{label}</span>'
    if varianti is not None:
        chips += f'<span class="chip">var. dichiarate 30/09\u2192: <b>{varianti}</b></span>'

    spec_section = next((v for k, v in sections.items() if k.startswith("Voci con spec")), [])
    infra_section = next((v for k, v in sections.items() if k.startswith("Infrastruttura")), [])
    stor_section = next((v for k, v in sections.items() if k.startswith("Voci storiche")), [])

    rows = ""
    for e in reversed(spec_section):
        t = f"{e['id']} \u00b7 {e['title']}" if e["title"] else e["id"]
        rows += (
            f'<tr><td><div class="t2">{html.escape(t)}</div><div class="n">{html.escape(e["note"])}</div></td>'
            f'<td class="st">{badge(e["status"])}</td></tr>'
        )
    if infra_section:
        rows += '<tr><td colspan="2" style="padding-top:9px"><span class="k2">Infrastruttura (strumenti \u2014 non strategie)</span></td></tr>'
        for e in infra_section:
            t = f"{e['id']} \u00b7 {e['title']}" if e["title"] else e["id"]
            rows += (
                f'<tr><td><div class="t2">{html.escape(t)}</div><div class="n">{html.escape(e["note"])}</div></td>'
                f'<td class="st">{badge(e["status"])}</td></tr>'
            )
    if stor_section:
        arcs = sum(1 for e in stor_section if e["status"] == "archiviata")
        ins = sum(1 for e in stor_section if e["status"] == "insufficiente")
        rows += (
            f'<tr><td><div class="t2">Voci storiche (pre-registro)</div>'
            f'<div class="n">{len(stor_section)} voci: {arcs} archiviate \u00b7 {ins} insufficienti \u00b7 resto vario</div></td>'
            f'<td class="st">{badge("archiviata")}</td></tr>'
        )

    ric_card = f"""
<div class="card wide">
 <h2>Ricerca \u00b7 esperimenti</h2>
 <div>{chips}</div>
 <table><tbody>{rows}</tbody></table>
</div>"""

    # ---- coda & governance
    spec_next = st.get("spec_next_desc") or "n/d"
    repo = infra.get("repo") or {}
    dirty = " \u00b7 ".join(
        f"{k} {(v or {}).get('dirty', '?')}" for k, v in repo.items()
    ) if repo else "n/d"
    az_html = "".join(f"<li>{md_mini(a)}</li>" for a in fab["azioni"]) or "<li>n/d</li>"
    coda_card = f"""
<div class="card wide">
 <h2>Coda &amp; governance</h2>
 <div class="cols">
  <div class="col"><div class="k2">Prossima spec da materializzare</div><div class="mid">{html.escape(spec_next)}</div></div>
  <div class="col"><div class="k2">Repo / commit</div><div class="mid">
    money <b>{html.escape(money_head.split(' ',1)[0])}</b> \u00b7 AOT mc2 <b>{html.escape(aot_head.split(' ',1)[0])}</b><br>
    <span class="sub">dirty (AOT): {html.escape(dirty)}</span></div></div>
 </div>
 <div class="k2">In attesa (per owner)</div>
 <ul class="az">{az_html}</ul>
</div>"""

    # ---- header/footer
    stale_note = ""
    if stale:
        stale_note = f'<span class="ts">\u26a0 dati remoti da cache (et\u00e0 {age_str(fetched_age) if fetched_age else "?"})</span>'
    else:
        stale_note = f'<span class="ts">remoto: aggregatore aggiornato {age_str(fetched_age) if fetched_age else "?"} fa</span>'
    foot = (
        "fonti: fabbrica/state.json \u00b7 STATO.md \u00b7 jobs.db \u00b7 watchdog.log \u00b7 "
        "prove/REGISTRO_ESPERIMENTI.md \u00b7 MARCODG1 infra.json \u00b7 canary.log \u00b7 generato da "
        "<code>money/scripts/cruscotto.py</code> \u2014 premi Aggiorna per rigenerare."
    )

    body = f"""
<div class="wrap">
 <div class="hd">
  <span class="t">\u25c9 CRUSCOTTO DENARO</span>
  <span class="ts">aggiornato {now.strftime('%d/%m %H:%M')}</span>
  {stale_note}
  <button data-hermes-send="aggiorna il cruscotto">\u21bb Aggiorna</button>
 </div>
 <div class="grid">
  {soldi_card}
  {fab_card}
  {ric_card}
  {coda_card}
 </div>
 <div class="foot">{foot}</div>
</div>"""

    return (
        "<!doctype html><html lang=\"it\"><head><meta charset=\"utf-8\">"
        f"<style>{CSS}</style></head><body>{body}</body></html>"
    )


def banco_dot(fab):
    b = fab["banco_short"]
    if "rc=0" in b or "rc=-0" in b:
        return dot("d-ok")
    if "rc=2" in b:
        return dot("d-warn")
    return dot("d-warn")


# ---------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--print", dest="do_print", action="store_true")
    args = ap.parse_args()

    now = time.time()
    cache, stale = fetch_remote()
    sections, varianti = parse_registro()
    fab = fabbrica_data(now)
    money_head = git_head(MONEY)
    aot_head = git_head(Path("/home/sergio/alpha-omega-trading"))

    doc = render(
        datetime.now(), now, cache, stale, fab, sections, varianti, money_head, aot_head
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(doc, encoding="utf-8")

    if args.do_print:
        infra = (cache or {}).get("infra") or {}
        print(f"cruscotto -> {OUT} ({len(doc)} byte)")
        print(f"equity: {infra.get('total_equity')} | stale={stale}")
        print(f"tick: {fab['st'].get('ticks')} (eta' {age_str(fab['tick_age'])}) | kill_switch={fab['st'].get('kill_switch')}")
        print(f"job queued: {fab['jobs'].get('queued')} | azioni owner: {len(fab['azioni'])}")
        cnt = {}
        for entries in sections.values():
            for e in entries:
                cnt[e['status']] = cnt.get(e['status'], 0) + 1
        print("esperimenti:", cnt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
