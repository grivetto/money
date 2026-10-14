#!/usr/bin/env python3
"""Kitchen Lab — genera /var/www/kitchen-lab/status.json per la home di mc2.

Eseguito dal cron (utente sergio, ogni minuto): /etc/cron.d/kitchen-lab
Solo stdlib, nessuna dipendenza esterna. Scrittura atomica.
"""
import json
import os
import re
import socket
import subprocess
import time
from datetime import datetime

os.environ["PATH"] = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

OUT = "/var/www/kitchen-lab/status.json"

SERVICES = {
    "nginx": "nginx",
    "docker": "docker",
    "zabbix": "zabbix-agent",
    "tailscale": "tailscaled",
    "ssh": "ssh",
}


def sh(cmd, timeout=8):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "").strip()
    except Exception:
        return ""


def human_uptime(secs):
    secs = int(secs)
    d, secs = divmod(secs, 86400)
    h, secs = divmod(secs, 3600)
    m = secs // 60
    if d:
        return f"{d}g {h}h {m}m"
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


def main():
    out = {
        "ts": int(time.time()),
        "time": datetime.now().strftime("%H:%M:%S"),
        "date": datetime.now().strftime("%d/%m/%Y"),
        "host": socket.gethostname(),
    }

    # uptime
    try:
        up = float(open("/proc/uptime").read().split()[0])
        out["uptime"] = human_uptime(up)
    except Exception:
        out["uptime"] = None

    # load
    try:
        out["load"] = " ".join(open("/proc/loadavg").read().split()[:3])
    except Exception:
        out["load"] = None

    # RAM
    try:
        mem = {}
        for line in open("/proc/meminfo"):
            k, v = line.split(":", 1)
            mem[k] = int(v.strip().split()[0])  # kB
        total_gb = mem["MemTotal"] / 1048576
        avail_kb = mem.get("MemAvailable", mem.get("MemFree", 0))
        used_gb = (mem["MemTotal"] - avail_kb) / 1048576
        out["mem"] = {
            "used_gb": round(used_gb, 1),
            "total_gb": round(total_gb, 1),
            "pct": round(100 * used_gb / total_gb),
        }
    except Exception:
        out["mem"] = None

    # disco /
    try:
        st = os.statvfs("/")
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        used = total - free
        out["disk"] = {
            "used_pct": round(100 * used / total),
            "free_gb": round(free / 2**30),
            "total_gb": round(total / 2**30),
        }
    except Exception:
        out["disk"] = None

    # servizi systemd
    services = {}
    for label, unit in SERVICES.items():
        services[label] = sh(f"systemctl is-active {unit}") == "active"
    out["services"] = services
    out["services_ok"] = sum(1 for v in services.values() if v)
    out["services_total"] = len(services)

    # container docker
    try:
        names = [n for n in sh("docker ps --format '{{.Names}}'").splitlines() if n.strip()]
        out["containers"] = {"count": len(names), "names": names}
    except Exception:
        out["containers"] = None

    # rete
    try:
        ips = sh("hostname -I").split()
        lan = next((i for i in ips if re.match(r"^(192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.)", i)), None)
        ts_ip = sh("tailscale ip -4").split()
        out["net"] = {"lan": lan, "tailscale": ts_ip[0] if ts_ip else None}
    except Exception:
        out["net"] = None

    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(out, f, ensure_ascii=False)
    os.replace(tmp, OUT)


if __name__ == "__main__":
    main()
