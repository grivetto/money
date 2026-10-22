#!/usr/bin/env python3
"""
Alpha-Omega Infra Aggregator — raccoglie lo stato di TUTTA l'infrastruttura
e lo espone come JSON per la dashboard web.

Dati raccolti:
- Bot trading (SOL/EUR, ADA/EUR) da health files
- Saldi OKX reali (entrambi i conti) via ccxt
- Prezzi correnti SOL/ADA
- Stato nodi (nuvola, mc2) via SSH ping
- Stato Zabbix (container + web)
- Stato tunnel Zabbix

Endpoints (HTTP):
  GET /infra.json  → tutto (usato dalla dashboard)
  GET /health      → stato aggregato bot (compatibile zabbix_fleet)
"""
import json
import os
import shlex
import socket
import subprocess
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from pathlib import Path

HEALTH_DIR = Path(os.getenv("HEALTH_DIR", "/home/marco/denaro/health"))
NODE_DIR = Path(os.getenv("NODE_DIR", "/home/marco/alpha-omega-trading/node_data"))
PORT = int(os.getenv("AGG_PORT", "8912"))
HOST = os.getenv("AGG_HOST", "127.0.0.1")

# Nodi remoti che eseguono il Node Denaro (paper/live). L'aggregator gira su
# MARCODG1 e li legge via SSH (stesso meccanismo di zabbix_state).
# remote_data_dir: cartella node_data sul nodo remoto.
REMOTE_NODES = {
    "nuvola": {
        # 19/10/26: via tailnet (il pubblico 87.106.3.15 resta fallback manuale).
        "ssh": ["sergio@100.103.169.99", "-p", "22"],
        "data_dir": "/home/sergio/alpha-omega-trading/node_data",
        "unit": "denaro-node-nuvola",
    },
    "mc2": {
        "ssh": ["sergio@127.0.0.1", "-p", "2222"],  # tunnel inverso
        "data_dir": "/home/sergio/denaro/health",
        "unit": "denaro-node-mc2",
    },
}

# Officina paper (01/10/26): i health *_paper.json dei node riconvertiti vivono
# in denaro/health su ogni nodo (su nuvola NON in node_data).
PAPER_SOURCES = {
    "nuvola": {"ssh": ["sergio@100.103.169.99", "-p", "22"],
               "dir": "/home/sergio/denaro/health"},
    "mc2": {"ssh": ["sergio@127.0.0.1", "-p", "2222"],
            "dir": "/home/sergio/denaro/health"},
}
# Officina paper locale su MARCODG1 (istanza xrp riconvertita)
LOCAL_PAPER = [
    ("marcodg1:paper:ADA/EUR", "/home/marco/denaro/health/ada_marcodg1_live_paper.json"),
    ("marcodg1:paper:ARB/EUR", "/home/marco/denaro/health/arb_marcodg1_live_paper.json"),
    ("marcodg1:paper:XLM/EUR", "/home/marco/denaro/health/xlm_marcodg1_live_paper.json"),
    ("marcodg1:paper:ALGO/EUR", "/home/marco/denaro/health/algo_marcodg1_live_paper.json"),
]

# Conti OKX. I .env stanno su macchine DIVERSE e le chiavi sono IP-bound, quindi
# ogni conto va letto SULLA macchina che lo possiede: vedi sorgenti_conti().
# Il prefisso seleziona le chiavi del subaccount (es. MARCOSUB1_OKX_API_KEY);
# senza prefisso si usano le chiavi del conto master.


def sorgenti_conti():
    """Sorgenti dei conti OKX, scelte in base alla MACCHINA su cui giriamo.

    Aggiornato il 2026-09-20: i path precedenti puntavano ai .env del sistema
    PRE-freeze, con chiavi ormai morte (50119 / ssh fallito): la dashboard
    mostrava 0-0.02 EUR invece del capitale reale. Ora si leggono i SEGRETI
    DEL RIDEPLOY (~/denaro/secrets, verificati il 19/09 da ccxt).
    Regola: ogni conto va letto SULLA macchina da cui la sua chiave funziona.
      - main    : whitelist 87.106.222.123 + 87.106.3.15 -> si legge da MARCODG1;
      - i 3 sub : verificati leggibili da mc2 -> si leggono da mc2
                  (l'aggregator di MARCODG1 li legge via tunnel inverso :2222);
      - nuvola  : non esegue l'aggregator; ramo tenuto minimo.

    Ritorna (locali, remoti):
      locali[label] = (path_env, prefisso)
      remoti[label] = (ssh_target, porta, path_env, python_remoto, prefisso)
    """
    _mc2_sub_py = "/home/sergio/denaro/venv/bin/python"
    subs_mc2 = {
        "OKX mc2sub1": ("sergio@127.0.0.1", 2222,
                        "/home/sergio/denaro/secrets/mc2sub1_okx.env", _mc2_sub_py, ""),
        "OKX marcosub1": ("sergio@127.0.0.1", 2222,
                          "/home/sergio/denaro/secrets/marcosub1_okx.env", _mc2_sub_py, ""),
        "OKX nuvolasub1": ("sergio@127.0.0.1", 2222,
                           "/home/sergio/denaro/secrets/nuvolasub1_okx.env", _mc2_sub_py, ""),
    }

    if Path("/home/marco/denaro/secrets/main_okx.env").exists():
        # ── MARCODG1 (dove gira l'aggregator della dashboard pubblica) ──
        locali = {"OKX main": ("/home/marco/denaro/secrets/main_okx.env", "")}
        remoti = dict(subs_mc2)
    elif Path("/home/sergio/denaro/secrets/mc2sub1_okx.env").exists():
        # ── mc2 (dashboard locale): i tre sub sono locali, main sta su MARCODG1 ──
        locali = {
            "OKX mc2sub1": ("/home/sergio/denaro/secrets/mc2sub1_okx.env", ""),
            "OKX marcosub1": ("/home/sergio/denaro/secrets/marcosub1_okx.env", ""),
            "OKX nuvolasub1": ("/home/sergio/denaro/secrets/nuvolasub1_okx.env", ""),
        }
        remoti = {"OKX main": ("MARCODG1", 22, "/home/marco/denaro/secrets/main_okx.env",
                               "/home/marco/denaro/venv/bin/python", "")}
    else:
        # ── nuvola: l'aggregator non gira qui; ramo minimo (main locale) ──
        locali = {"OKX main": ("/home/sergio/denaro/secrets/main_okx.env", "")}
        remoti = {}
    return locali, remoti

# Kraken: piu' chiavi API possono puntare allo STESSO conto -> si deduplica per
# fingerprint della chiave, altrimenti il capitale verrebbe contato piu' volte.
KRAKEN_ENV_FILES = [
    ("/home/marco/denaro/.env", "KRAKEN_API_KEY", "KRAKEN_API_SECRET"),
    ("/home/marco/alpha-omega-trading/.env", "TRENDSUB_KRAKEN_API_KEY", "TRENDSUB_KRAKEN_API_SECRET"),
    ("/home/marco/alpha-omega-trading/.env", "NUVOLASUB1_KRAKEN_API_KEY", "NUVOLASUB1_KRAKEN_API_SECRET"),
]

# Su quale macchina gira questa istanza? (mc2 = dashboard locale; MARCODG1 = master
# della dashboard pubblica). Serve per leggere in LOCALE cio' che altrove e' remoto.
_HOSTNAME = socket.gethostname().lower()
ON_MC2 = _HOSTNAME == "mc2"
ON_MARCODG1 = _HOSTNAME == "marcodg1" or Path("/home/marco/denaro/secrets/main_okx.env").exists()

NODES = {
    "nuvola": ("100.103.169.99", 22),
    # su MARCODG1 mc2 e' raggiungibile via tunnel inverso :2222; su mc2 e' locale.
    "mc2": (("127.0.0.1", 22) if ON_MC2 else ("127.0.0.1", 2222)),
    "marcodg1": (("127.0.0.1", 22) if ON_MARCODG1 else ("87.106.222.123", 22)),
}


def load_env(path):
    env = {}
    p = Path(path)
    if p.exists():
        for line in p.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


_remote_cache = {}
_extra_cache = {}   # bot live extra: ultima lettura buona
_REMOTE_TTL = 30.0  # secondi

# Dopo quanti secondi un health file e' considerato VECCHIO. Un bot ticka ogni
# 30 s: 5 minuti di silenzio significano che quel bot non sta lavorando.
# Serve a non presentare come "running" un nodo spento giorni prima.
BOT_STALE_S = 300.0

# Uno snapshot piu' vecchio di questo limite non e' rappresentativo: i flag di
# freschezza dei singoli bot si congelano al momento della generazione. Se il
# cron che lo rigenera si ferma, meglio tornare alla collect live (lenta ma
# onesta) invece di servire dati silenziosamente stantii.
SNAP_MAX_AGE_S = 300.0


def fetch_remote_json(host, remote_path, cmd=None):
    """Legge un JSON da una macchina remota via SSH, con cache TTL (30s)."""
    cache_key = f"{host}:{remote_path}:{cmd}"
    now = time.time()
    hit = _remote_cache.get(cache_key)
    if hit and now - hit[0] < _REMOTE_TTL:
        return hit[1]
    try:
        if cmd:
            full = f"ssh -o BatchMode=yes -o ConnectTimeout=5 {host} {cmd}"
            r = subprocess.run(["bash", "-c", full], capture_output=True, text=True, timeout=25)
            if r.returncode != 0 or not r.stdout.strip():
                return None
            val = json.loads(r.stdout.strip().splitlines()[-1])
        else:
            full = f"ssh -o BatchMode=yes -o ConnectTimeout=5 {host} cat {remote_path}"
            r = subprocess.run(["bash", "-c", full], capture_output=True, text=True, timeout=15)
            if r.returncode != 0 or not r.stdout.strip():
                return None
            val = json.loads(r.stdout.strip())
        _remote_cache[cache_key] = (now, val)
        return val
    except Exception:
        return None


_balance_cache = {}
_BAL_TTL = 20.0


def fetch_okx_balance(env):
    try:
        key = env.get("OKX_API_KEY", "")[:10]
        now = time.time()
        hit = _balance_cache.get(key)
        if hit and now - hit[0] < _BAL_TTL:
            return hit[1]
        import ccxt
        ex = ccxt.okx({
            "apiKey": env.get("OKX_API_KEY", ""),
            "secret": env.get("OKX_API_SECRET", ""),
            "password": env.get("OKX_PASSPHRASE", ""),
            "enableRateLimit": True,
            "hostname": "eea.okx.com",
        })
        # 2026-09-27: fetch_balance() di default legge SOLO il trading account.
        # I bonifici e i fondi fermi stanno nel FUNDING: la dashboard mostrava 0
        # con 100 EUR reali sul conto. Si leggono ENTRAMBI e si sommano.
        tot_merged, free_merged, letti = {}, {}, 0
        for tipo in ("trading", "funding"):
            try:
                b = ex.fetch_balance({"type": tipo}) or {}
                letti += 1
            except Exception:
                continue
            for k, v in (b.get("total") or {}).items():
                if v and float(v) > 0:
                    tot_merged[k] = tot_merged.get(k, 0.0) + float(v)
            for k, v in (b.get("free") or {}).items():
                if v and float(v) > 0:
                    free_merged[k] = free_merged.get(k, 0.0) + float(v)
        # 2026-10-11: i fondi in Simple Earn (savings) NON compaiono ne' in trading ne'
        # in funding: con ~1.097 USDC messi a rendita l'equity e' scivolata da ~1.100 a
        # ~120 EUR (bug visto dal vivo). Si sommano anche i saldi savings (retry 2x;
        # se fallisce, l'account resta leggibile su trading+funding e si annota l'errore).
        sav_tot, sav_detail, sav_err = {}, {}, None
        for _tent in range(2):
            sav_tot = {}
            sav_detail = {}
            try:
                sav = ex.privateGetFinanceSavingsBalance({}) or {}
                for r in (sav.get("data") or []):
                    ccy = r.get("ccy")
                    try:
                        amt = float(r.get("amt") or 0)
                    except (TypeError, ValueError):
                        continue
                    if ccy and amt > 0:
                        sav_tot[ccy] = sav_tot.get(ccy, 0.0) + amt
                        try:
                            _earn = float(r.get("earnings") or 0)
                        except (TypeError, ValueError):
                            _earn = None
                        try:
                            _rate = float(r.get("rate") or 0)
                        except (TypeError, ValueError):
                            _rate = None
                        sav_detail[ccy] = {"amt": round(amt, 6), "earnings": _earn, "rate": _rate}
                sav_err = None
                break
            except Exception as exc:
                sav_err = str(exc)[:120]
        for _ccy, _amt in sav_tot.items():
            tot_merged[_ccy] = tot_merged.get(_ccy, 0.0) + _amt
        if letti == 0:
            return {"ok": False, "error": "fetch_balance fallito su trading e funding"}
        total = {k: round(v, 6) for k, v in tot_merged.items()}
        free = {k: round(v, 6) for k, v in free_merged.items()}
        val = {"ok": True, "total": total, "free": free, "savings_ok": sav_err is None}
        if sav_detail:
            val["savings"] = sav_detail
        if sav_err:
            val["savings_error"] = sav_err
        _balance_cache[key] = (now, val)
        return val
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


_price_cache = {}
_PRICE_TTL = 15.0


def fetch_kraken_balance(env, key_attr="KRAKEN_API_KEY", secret_attr="KRAKEN_API_SECRET"):
    """Saldo Kraken LIVE (ccxt)."""
    try:
        key = env.get(key_attr, "")[:10]
        now = time.time()
        hit = _balance_cache.get("kraken:" + key)
        if hit and now - hit[0] < _BAL_TTL:
            return hit[1]
        import ccxt
        ex = ccxt.kraken({
            "apiKey": env.get(key_attr, ""),
            "secret": env.get(secret_attr, ""),
            "enableRateLimit": True,
        })
        b = ex.fetch_balance()
        total = {k: round(v, 6) for k, v in b.get("total", {}).items() if v and v > 0}
        val = {"ok": True, "total": total,
               "free": {k: round(v, 6) for k, v in b.get("free", {}).items() if v and v > 0}}
        _balance_cache["kraken:" + key] = (now, val)
        return val
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def _acct_fp(*parts):
    """Fingerprint non reversibile di una chiave API: serve a deduplicare gli account."""
    import hashlib
    return hashlib.md5("|".join(p or "" for p in parts).encode()).hexdigest()[:12]


def _remote_okx_snippet(env_path, prefix=""):
    """Snippet Python eseguito SUL nodo di origine per leggere il saldo OKX.

    `prefix` seleziona le chiavi di un SUBACCOUNT nello stesso file (es.
    MARCOSUB1_OKX_API_KEY): senza, si userebbero le chiavi master e si
    leggerebbe il conto sbagliato.
    """
    return (
        "import json\n"
        "env = {}\n"
        "for line in open(" + repr(env_path) + "):\n"
        "    if '=' in line and not line.strip().startswith('#'):\n"
        "        k, v = line.strip().split('=', 1)\n"
        "        env[k.strip()] = v.strip().strip(chr(34)).strip(chr(39))\n"
        "P = " + repr(prefix) + "\n"
        "g = lambda n: env.get(P + n)\n"
        "import ccxt\n"
        "ex = ccxt.okx({'apiKey': g('OKX_API_KEY'), 'secret': g('OKX_API_SECRET'),"
        " 'password': g('OKX_PASSPHRASE'), 'hostname': 'eea.okx.com'})\n"
        # 2026-09-27: come fetch_okx_balance locale — trading E funding, mai solo trading
        "tot = {}\nfre = {}\nnok = 0\n"
        "for tipo in ('trading', 'funding'):\n"
        "    try:\n"
        "        b = ex.fetch_balance({'type': tipo}) or {}\n"
        "        nok += 1\n"
        "    except Exception:\n"
        "        continue\n"
        "    for k, v in (b.get('total') or {}).items():\n"
        "        if v and float(v) > 0:\n            tot[k] = tot.get(k, 0.0) + float(v)\n"
        "    for k, v in (b.get('free') or {}).items():\n"
        "        if v and float(v) > 0:\n            fre[k] = fre.get(k, 0.0) + float(v)\n"
        # 2026-10-11: anche il saldo Simple Earn (savings), che trading/funding non vedono.
        # Senza questo, con ~1.097 USDC a rendita l'equity scende da ~1.100 a ~120 EUR.
        "sok = True\n"
        "try:\n"
        "    _sav = ex.privateGetFinanceSavingsBalance({}) or {}\n"
        "except Exception:\n"
        "    _sav = {}\n"
        "    sok = False\n"
        "for _r in (_sav.get('data') or []):\n"
        "    _c = _r.get('ccy')\n"
        "    try:\n"
        "        _a = float(_r.get('amt') or 0)\n"
        "    except Exception:\n"
        "        continue\n"
        "    if _c and _a > 0:\n"
        "        tot[_c] = tot.get(_c, 0.0) + _a\n"
        "print(json.dumps({'ok': nok > 0, 'total': tot, 'free': fre, 'savings_ok': sok}))\n"
    )


def fetch_remote_okx_balance(ssh_target, ssh_port, remote_env, remote_python="/usr/bin/python3",
                            prefix="", ttl=30.0):
    """Saldo OKX di un subaccount con chiavi IP-bound, letto sul nodo di origine."""
    cache_key = "remoteokx:%s:%s:%s" % (ssh_target, remote_env, prefix)
    now = time.time()
    hit = _balance_cache.get(cache_key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    try:
        # NB: niente "bash -c" locale: passando l'argv direttamente a ssh, il
        # quoting sopravvive al doppio parsing (locale + shell remota).
        cmd = ["ssh", "-p", str(ssh_port), "-o", "BatchMode=yes", "-o", "ConnectTimeout=6",
               ssh_target, remote_python, "-c",
               shlex.quote(_remote_okx_snippet(remote_env, prefix))]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        if r.returncode != 0 or not r.stdout.strip():
            return None
        val = json.loads(r.stdout.strip().splitlines()[-1])
        if val.get("ok"):
            val["total"] = {k: v for k, v in (val.get("total") or {}).items() if v and float(v) > 0}
            val["acct"] = _acct_fp(ssh_target, remote_env)
            _balance_cache[cache_key] = (now, val)
        return val
    except Exception:
        return None


_EUR_FIAT = {"EUR"}

#: Valute "derivate" che valgono quanto il sottostante (1:1).
#: OKX consegna gli acquisti di ETH come BETH (Beacon ETH / staking) in alcune
#: regioni: senza questo alias il BETH non ha un mercato EUR/USDT diretto,
#: finisce in `unpriced` e NON entra nell'equity (patrimonio sottostimato).
#: Trovato il 2026-10-16: 0,00203 BETH (4,95 USDC) non contati.
_ALIAS_VALUTA = {
    "BETH": "ETH",      # Beacon ETH
    "STETH": "ETH",     # Lido staked ETH
    "WSTETH": "ETH",    # wrapped staked ETH
    "CBBTC": "BTC",     # Coinbase wrapped BTC
    "WBTC": "BTC",      # wrapped BTC
}
_EUR_STABLES = {"USDC", "USDT", "USD", "DAI", "TUSD", "BUSD", "USDE"}
_rate_cache = {}
_RATE_TTL = 60.0


def fetch_eur_rate(cur, _depth=0):
    """Quanto vale 1 unita' della valuta indicata in EUR (cache 60s)."""
    if cur in _EUR_FIAT:
        return 1.0
    if cur in _ALIAS_VALUTA:
        return fetch_eur_rate(_ALIAS_VALUTA[cur], _depth + 1)
    now = time.time()
    hit = _rate_cache.get(cur)
    if hit and now - hit[0] < _RATE_TTL:
        return hit[1]
    rate = None
    pairs = [("%s/EUR" % cur, False), ("EUR/%s" % cur, True)]
    if cur not in _EUR_STABLES and _depth < 2:
        pairs += [("%s/USDT" % cur, False), ("%s/USDC" % cur, False)]
    try:
        import ccxt
        ex = ccxt.okx({"enableRateLimit": True, "hostname": "eea.okx.com"})
        for pair, invert in pairs:
            try:
                last = float(ex.fetch_ticker(pair)["last"])
            except Exception:
                continue
            if not last:
                continue
            if pair.endswith("/EUR"):
                rate = last
            elif invert:
                rate = 1.0 / last
            else:
                base_rate = fetch_eur_rate(pair.split("/")[1], _depth + 1)
                rate = last * base_rate if base_rate else None
            if rate:
                break
    except Exception:
        rate = None
    _rate_cache[cur] = (now, rate)
    return rate


def balance_eur(balances):
    """Valorizza in EUR i saldi reali deduplicando gli account identici.

    Ritorna (totale_eur, dettaglio_per_etichetta, quote_non_valutate).
    """
    seen = []
    detail = {}
    total = 0.0
    unpriced = []
    for label, bal in balances.items():
        if not isinstance(bal, dict) or not bal.get("ok"):
            err = bal.get("error", "") if isinstance(bal, dict) else "n/d"
            detail[label] = {"ok": False, "eur": None, "error": str(err)[:80]}
            continue
        fp = bal.get("acct") or label
        if fp in seen:
            detail[label] = {"ok": True, "eur": None, "dedup": True}
            continue
        seen.append(fp)
        tot = 0.0
        for cur, amt in (bal.get("total") or {}).items():
            try:
                amt = float(amt)
            except Exception:
                continue
            if amt <= 0:
                continue
            rate = fetch_eur_rate(cur)
            if rate is None:
                unpriced.append("%s:%s" % (label, cur))
                continue
            tot += amt * rate
        detail[label] = {"ok": True, "eur": round(tot, 2)}
        total += tot
    return round(total, 2), detail, unpriced


def fetch_prices():
    try:
        now = time.time()
        hit = _price_cache.get("prices")
        if hit and now - hit[0] < _PRICE_TTL:
            return hit[1]
        import ccxt
        ex = ccxt.okx({"enableRateLimit": True, "hostname": "eea.okx.com"})
        prices = {}
        # 2026-10-18: i prezzi che contano — mercato (BTC/ETH), carry (DOT/ADA/LTC/AVAX), canary (DOGE).
        for s in ("BTC/EUR", "ETH/EUR", "DOGE/EUR", "DOT/EUR", "ADA/EUR", "LTC/EUR", "AVAX/EUR"):
            try:
                t = ex.fetch_ticker(s)
                prices[s] = {"last": t["last"], "bid": t.get("bid"), "ask": t.get("ask"),
                             "pct24h": t.get("percentage")}
            except Exception:
                prices[s] = None
        _price_cache["prices"] = (now, prices)
        return prices
    except Exception as e:
        return {"error": str(e)[:200]}


def ping_host(host, port, timeout=4):
    """Raggiungibilita' VERA del nodo: TCP + banner SSH.

    Il solo connect TCP mente: con sshd vivo ma incapace di servire (fork/OOM,
    DNS inverso appeso) il kernel accetta la connessione e il nodo risulta
    "reachable" mentre e' di fatto morto (caso nuvola 21/10: nodo giu' ~24h,
    nessun alert). Porta 22/2222 -> pretendiamo il banner `SSH-`.
    """
    try:
        s = socket.create_connection((host, port), timeout=timeout)
    except Exception:
        return False
    try:
        if port in (22, 2222):
            s.settimeout(min(timeout, 3))
            return s.recv(64).startswith(b"SSH-")
        return True
    except Exception:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def docker_state():
    try:
        r = subprocess.run(["docker", "ps", "--format", "{{.Names}}|{{.Status}}"],
                           capture_output=True, text=True, timeout=10)
        containers = {}
        for line in r.stdout.strip().splitlines():
            if "|" in line:
                name, status = line.split("|", 1)
                containers[name] = status
        return containers
    except Exception as e:
        return {"error": str(e)[:200]}


def zabbix_state():
    """Stato dei container Zabbix — che girano su MC2, letti via tunnel SSH
    (127.0.0.1:2222 -> porta 22 di mc2). Fallback: web check via tunnel 1080."""
    z = {}
    try:
        r = subprocess.run(
            ["ssh", "-p", "2222", "-o", "BatchMode=yes", "-o", "ConnectTimeout=6",
             "-o", "StrictHostKeyChecking=accept-new", "sergio@127.0.0.1",
             "docker ps --format '{{.Names}}|{{.Status}}'"],
            capture_output=True, text=True, timeout=15)
        found = False
        for line in r.stdout.splitlines():
            if "|" in line:
                name, status = line.split("|", 1)
                if name in ("zabbix-web", "zabbix-server", "zabbix-db"):
                    z[name] = status
                    found = True
        if not found:
            z = {"tunnel": "nessun container zabbix da mc2",
                 "stderr": r.stderr.strip()[:100]}
    except Exception as e:
        z = {"ssh_error": str(e)[:100]}
    # Web reachable (tunnel 1080 su mc2)
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:1080/", timeout=5) as r:
            z["web_http"] = r.status
    except Exception as e:
        z["web_http"] = str(e)[:100]
    return z


def system_state():
    try:
        r = subprocess.run(["uptime"], capture_output=True, text=True, timeout=5)
        load = r.stdout.strip()
        mem = subprocess.run(["free", "-m"], capture_output=True, text=True, timeout=5)
        mem_line = [l for l in mem.stdout.splitlines() if l.startswith("Mem:")][0]
        parts = mem_line.split()
        return {"uptime": load, "mem_total_mb": parts[1], "mem_used_mb": parts[2],
                "mem_free_mb": parts[3]}
    except Exception as e:
        return {"error": str(e)[:200]}


def collect_node_bots():
    """Tutti i health del Node — paper (node_data/*_health.json) + live
    (health_path espliciti: health/ada.json, sol.json, sol_kraken.json)."""
    bots = {}
    try:
        for p in sorted(NODE_DIR.glob("*_health.json")):
            try:
                h = json.loads(p.read_text())
                h["mode"] = "paper"
                bots[h.get("symbol", p.stem)] = h
            except Exception:
                continue
    except Exception:
        pass
    # istanza TREND paper (MARCODG1): node_data_trend/paper_default_*
    try:
        trend_dir = NODE_DIR.parent / "node_data_trend"
        for p in sorted(trend_dir.glob("*_health.json")):
            try:
                h = json.loads(p.read_text())
                h["mode"] = "paper"
                bots[f"trend:{h.get('symbol', p.stem)}"] = h
            except Exception:
                continue
    except Exception:
        pass
    live = {
        "okx:ADA/EUR": HEALTH_DIR / "ada.json",
        "okx:SOL/EUR": HEALTH_DIR / "sol.json",
        "okx:DOGE/EUR": HEALTH_DIR / "doge.json",
        "okx:ETH/EUR": HEALTH_DIR / "eth.json",
        # KRAKEN RIMOSSO (2026-09-17): sol_kraken.json, trend_sol_kraken.json e
        # trend_xrp_kraken.json sono fossili della generazione precedente. Il
        # file esiste ancora, quindi il bot veniva aggiunto alla dashboard come
        # card VUOTA ("stale" non valorizzato) accanto ai 15 bot vivi.
        "mc2:okx:DOGE/EUR": HEALTH_DIR / "doge_mc2.json",
        "mc2:okx:SOL/EUR": HEALTH_DIR / "sol_mc2.json",
        # round 17: universo allargato da 15 a 19 asset
        "mc2:okx:TRX/EUR": HEALTH_DIR / "trx_mc2.json",
        "mc2:okx:CRV/EUR": HEALTH_DIR / "crv_mc2.json",
    }
    for key, p in live.items():
        try:
            h = json.loads(p.read_text())
            if h.get("timestamp"):
                h["mode"] = "live"
                bots[key] = h
        except Exception:
            continue
    # ── mc2 (LIVE OKX): i suoi health vivono su mc2, non su MARCODG1 ──────
    # Il glob generico dei nodi remoti perde questi file o li confonde con i
    # fossili (*_nuvola.json, stesso symbol ma fermi da giorni): li leggiamo
    # PER NOME, che e' l'unica cosa che distingue un bot vivo da un residuo.
    _mcfg = REMOTE_NODES.get("mc2")
    if _mcfg:
        _ssh = " ".join(_mcfg["ssh"])
        # 2026-09-17: mc2 e' passato dalla griglia al TREND GIORNALIERO su
        # 5 asset. I nomi sono espliciti perche' il glob generico perde
        # questi file o li confonde con i fossili.
        for _fn in ("btc_mc2.json", "eth_mc2.json", "sol_mc2.json",
                    "xrp_mc2.json", "doge_mc2.json"):
            _rp = _mcfg["data_dir"].rstrip("/") + "/" + _fn
            _cmd = ("ssh -o BatchMode=yes -o ConnectTimeout=5 " + _ssh +
                    " 'cat " + _rp + " 2>/dev/null'")
            try:
                _r = subprocess.run(["bash", "-c", _cmd], capture_output=True,
                                    text=True, timeout=15)
                if _r.returncode == 0 and _r.stdout.strip():
                    _h = json.loads(_r.stdout.strip().splitlines()[-1])
                    _sym = _h.get("symbol", "")
                    if _sym:
                        _h["mode"] = "live"
                        bots["mc2:okx:" + _sym] = _h
            except Exception:
                continue

    # ── Bot LIVE nuovi (2026-09-17) ────────────────────────────────────────
    # nuvola  : momentum SOL/EUR su nuvolasub1 -> health su nuvola
    # marcodg1: mean-reversion XRP/EUR su marcosub1 -> health locale
    # Ognuno scrive in una dir dedicata (node_data_trade / node_data_xrp) che
    # il collector generico non guarda: li leggiamo per path esplicito.
    _extra_live = [
        # 2026-10-06: le 10 voci nuvola/marcodg1 che stavano qui puntavano ai file
        # *_live.json del mondo pre-officina (fermi dal 30/09-01/10): erano la fonte
        # delle card "equity inattendibile"/"no_file" accanto alle card paper VIVE.
        # I bot sono stati riconvertiti a OFFICINA PAPER (01/10) e le loro card vivono
        # su "<nodo>:paper:<SYM>" (fetch_remote_paper, *_paper.json). Voci rimosse;
        # i file legacy sono archiviati in health/_archivio_pre_paper_20261006/.
    ]
    # UNA ssh per HOST, non una per bot: prima erano 10 connessioni per ciclo
    # e bastava che UNA fallisse per far sparire la card di quel bot dalla
    # dashboard per un ciclo intero (visto il 2026-09-17 su nuvola/AVAX). Se
    # la lettura fallisce si tiene l ultima buona per 300s: un singolo
    # timeout non deve spegnere un bot che sta lavorando.
    _per_host = {}
    for _k, _kind, _alias, _path in _extra_live:
        if _kind == "file":
            try:
                _blocchi = _parse_dump("===FILE===" + Path(_path).read_text())
                _h = json.loads(_blocchi[0])
                _h["mode"] = "live"
                bots[_k] = _h
                _extra_cache[_k] = (time.time(), _h)
            except Exception:
                pass
            continue
        _per_host.setdefault(_alias, []).append((_k, _path))

    for _alias, _voci in _per_host.items():
        _lista = " ".join(_pp for _, _pp in _voci)
        _q = chr(34)
        # niente [ -f ]: se un file manca, cat non stampa nulla e il blocco
        # resta vuoto. Un test malformato faceva uscire ssh con errore e
        # TUTTI i bot di quell host sparivano dalla dashboard.
        _cmd = ("for f in " + _lista + "; do echo ===FILE===; cat "
                + _q + "$f" + _q + " 2>/dev/null; echo; done")
        try:
            _pr = subprocess.run(["ssh", "-o", "BatchMode=yes",
                                  "-o", "ConnectTimeout=5", _alias, _cmd],
                                 capture_output=True, text=True, timeout=25)
            _blocchi = _parse_dump(_pr.stdout) if _pr.returncode == 0 else []
        except Exception:
            _blocchi = []
        for _i, (_k, _path) in enumerate(_voci):
            _raw = _blocchi[_i] if _i < len(_blocchi) else ""
            _h = None
            if _raw.strip():
                try:
                    _h = json.loads(_raw)
                except Exception:
                    _h = None
            if _h is None:
                _vecchio = _extra_cache.get(_k)
                if _vecchio and time.time() - _vecchio[0] <= 300:
                    _h = _vecchio[1]
            if _h is not None:
                _h = dict(_h)
                _h["mode"] = "live"
                bots[_k] = _h
                _extra_cache[_k] = (time.time(), _h)

    # ── Officina paper (01/10/26): health *_paper.json — chiavi
    #    "<nodo>:paper:<SYM>"; il live/l legacy resta su "<nodo>:okx:<SYM>".
    for _pk, _pp in LOCAL_PAPER:
        try:
            _h = json.loads(Path(_pp).read_text())
            _h["mode"] = "paper"
            bots[_pk] = _h
        except Exception:
            continue
    for _node_name in PAPER_SOURCES:
        try:
            for _sym, _h in fetch_remote_paper(_node_name).items():
                _h["mode"] = "paper"
                bots[f"{_node_name}:paper:{_sym}"] = _h
        except Exception:
            continue

    # Nodi remoti: chiavi "nuvola:paper:ADA/EUR", "mc2:paper:ADA/EUR" ecc.
    for node_name, cfg in REMOTE_NODES.items():
        for sym, h in fetch_remote_node_bots(node_name).items():
            h.setdefault("mode", "paper")
            bots[f"{node_name}:{sym}"] = h
    # Freschezza REALE: un health file vecchio non e' un bot che sta lavorando.
    # Prima la dashboard mostrava come "running" nodi spenti da giorni (es.
    # trend_sol_kraken.json fermo al 24 agosto, nuvola da 23 ore).
    now = time.time()
    for _key, h in bots.items():
        if not isinstance(h, dict):
            continue
        try:
            ts = float(h.get("timestamp") or 0.0)
        except (TypeError, ValueError):
            ts = 0.0
        age = (now - ts) if ts else None
        h["age_s"] = round(age, 1) if age is not None else None
        h["stale"] = (age is None) or (age > BOT_STALE_S)
        h.setdefault("mode", "paper")
    # 2026-10-18: niente doppioni legacy. "mc2:BTC/EUR" (dal glob dei file) e
    # "mc2:paper:BTC/EUR" (dalla lettura officina) sono lo STESSO bot: si tiene
    # solo la chiave ufficiale ":paper:" (o ":live:" quando esistera' un live).
    for _k in list(bots.keys()):
        _parts = _k.split(":")
        if len(_parts) == 2 and f"{_parts[0]}:paper:{_parts[1]}" in bots:
            del bots[_k]
    return bots


def _parse_dump(testo):
    """Estrae i JSON da un dump ===FILE===<json> (uno o piu file)."""
    fuori = []
    for blocco in (testo or "").split("===FILE===")[1:]:
        i0, i1 = blocco.find("{"), blocco.rfind("}")
        fuori.append(blocco[i0:i1 + 1] if 0 <= i0 < i1 else "")
    return fuori


def fetch_remote_paper(node_name):
    """Legge i *_paper.json (officina) del nodo remoto — cache TTL come il live."""
    cfg = PAPER_SOURCES.get(node_name)
    if not cfg:
        return {}
    cache_key = f"remote_paper:{node_name}"
    now = time.time()
    hit = _remote_cache.get(cache_key)
    if hit and now - hit[0] < _REMOTE_TTL:
        return hit[1]
    if node_name == "mc2" and ON_MC2:
        # istanza mc2: i file officina sono LOCALI (niente tunnel verso se stessi)
        out = {}
        try:
            for f in sorted(Path(cfg["dir"]).glob("*_paper.json")):
                try:
                    h = json.loads(f.read_text())
                except Exception:
                    continue
                if h.get("symbol"):
                    out[h["symbol"]] = h
        except OSError:
            return {}
        _remote_cache[cache_key] = (now, out)
        return out
    ssh_args = " ".join(cfg["ssh"])
    d = cfg["dir"]
    cmd = (f"ssh -o BatchMode=yes -o ConnectTimeout=5 {ssh_args} "
           f"'for f in {d}/*_paper.json; do echo ===FILE===; cat \"$f\" 2>/dev/null; echo; done'")
    out = {}
    try:
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=20)
        if r.returncode == 0 and r.stdout.strip():
            for block in r.stdout.split("===FILE===")[1:]:
                i0, i1 = block.find("{"), block.rfind("}")
                if not (0 <= i0 < i1):
                    continue
                try:
                    h = json.loads(block[i0:i1 + 1])
                except Exception:
                    continue
                out[h.get("symbol") or "unknown"] = h
    except Exception:
        return {}
    _remote_cache[cache_key] = (now, out)
    return out


def fetch_remote_node_bots(node_name):
    """Legge i *_health.json del Node remoto via SSH (con cache TTL)."""
    cfg = REMOTE_NODES.get(node_name)
    if not cfg:
        return {}
    data_dir = cfg["data_dir"]
    cache_key = f"remote_node:{node_name}"
    now = time.time()
    hit = _remote_cache.get(cache_key)
    if hit and now - hit[0] < _REMOTE_TTL:
        return hit[1]
    if node_name == "mc2" and ON_MC2:
        # istanza mc2: gli health dei bot sono LOCALI (*_paper.json in denaro/health)
        out = {}
        try:
            for f in sorted(Path(data_dir).glob("*_paper.json")):
                try:
                    h = json.loads(f.read_text())
                except Exception:
                    continue
                if h.get("symbol"):
                    out[h["symbol"]] = h
        except OSError:
            return {}
        _remote_cache[cache_key] = (now, out)
        return out
    ssh_args = " ".join(cfg["ssh"])
    cmd = (f"ssh -o BatchMode=yes -o ConnectTimeout=5 {ssh_args} "
           f"'for f in {data_dir}/*_health.json {data_dir}/*.json; do if [ -f \"$f\" ]; then echo ===FILE===; cat \"$f\"; echo; fi; done'")
    try:
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=20)
        bots = {}
        if r.returncode == 0 and r.stdout.strip():
            blocks = r.stdout.split("===FILE===")
            for block in blocks[1:]:
                lines = block.strip().splitlines()
                if not lines:
                    continue
                try:
                    h = json.loads(lines[-1])
                    sym = h.get("symbol")
                    if not sym:
                        continue  # file di servizio (trend/infra/snapshot) senza symbol: non e' un bot
                    bots[sym] = h
                except Exception:
                    continue
        # istanza TREND paper sul remoto: node_data_trend/*_health.json
        trend_dir = data_dir.rsplit("/", 1)[0] + "/node_data_trend"
        cmd2 = (f"ssh -o BatchMode=yes -o ConnectTimeout=5 {ssh_args} "
                f"'for f in {trend_dir}/*_health.json; do echo ===FILE===; cat \"$f\"; echo; done'")
        try:
            r2 = subprocess.run(["bash", "-c", cmd2], capture_output=True,
                                text=True, timeout=20)
            if r2.returncode == 0 and r2.stdout.strip():
                for block in r2.stdout.split("===FILE===")[1:]:
                    lines = block.strip().splitlines()
                    if not lines:
                        continue
                    try:
                        h = json.loads(lines[-1])
                        bots[f"trend:{h.get('symbol', 'unknown')}"] = h
                    except Exception:
                        continue
        except Exception:
            pass
        _remote_cache[cache_key] = (now, bots)
        return bots
    except Exception:
        return {}


def read_trend():
    """Serie storica equity (aggiornata da infra_snapshot via cron)."""
    try:
        return json.loads((HEALTH_DIR / "trend.json").read_text())
    except Exception:
        return []


# Servizi del progetto money per macchina (stesso set di push_metrics.py) → dashboard
SERVICE_UNITS = {
    "marcodg1": {
        "ssh": [],
        "units": [
            "money-aggregator-marcodg1", "money-dashboard-marcodg1",
            "money-health-marcodg1", "money-landing-marcodg1",
            "money-watchdog-marcodg1.timer", "money-banco-secco.timer",
            "fabbrica-worker.timer", "cloudflared", "zabbix-agent",
            "money-prometheus", "money-grafana", "money-exporter",
        ],
    },
    "nuvola": {
        "ssh": ["sergio@100.103.169.99", "-p", "22"],
        "units": ["denaro-node-nuvola-trade", "money-health-nuvola",
                  "zabbix-agent", "zabbix-tunnel", "denaro-exporter"],
    },
    "mc2": {
        "ssh": ["sergio@127.0.0.1", "-p", "2222"],  # tunnel inverso
        "units": ["money-aggregator-mc2", "money-dashboard-mc2", "money-health-mc2",
                  "denaro-node-mc2", "denaro-feeder-mc2",
                  "cloudflared-home", "zabbix-agent", "zabbix-tunnel-reverse",
                  "denaro-exporter-mc2"],
    },
}


_smart_cache = {}


def _read_json_smart(local_path: str, host: str = "MARCODG1", ttl: float = 20.0):
    """Legge un JSON che vive su MARCODG1 (path /home/marco/...).

    Se ci giriamo sopra (MARCODG1): lettura locale. Altrimenti (mc2): ssh + stat
    per l'eta'. Cache TTL breve per non ripetere la stessa ssh nello stesso giro.
    Ritorna (obj, age_s). Solleva eccezione se non leggibile (decide il chiamante).
    """
    now = time.time()
    key = f"{host}:{local_path}"
    hit = _smart_cache.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1], hit[2] + (now - hit[0])
    p = Path(local_path)
    if p.exists():
        obj = json.loads(p.read_text())
        age = max(0.0, now - p.stat().st_mtime)
    else:
        if ON_MARCODG1:
            raise FileNotFoundError(local_path)
        q = shlex.quote(local_path)
        remote_cmd = f"stat -c %Y {q} 2>/dev/null; echo @@; cat {q} 2>/dev/null"
        r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
                            host, remote_cmd], capture_output=True, text=True, timeout=20)
        if r.returncode != 0 or "@@" not in r.stdout:
            raise FileNotFoundError(local_path)
        head, _, body = r.stdout.partition("@@")
        body = body.strip()
        if not body:
            raise FileNotFoundError(local_path)
        mtime = None
        for line in head.strip().splitlines():
            line = line.strip()
            if line.isdigit():
                mtime = float(line)
        obj = json.loads(body)
        age = max(0.0, now - mtime) if mtime else 0.0
    _smart_cache[key] = (now, obj, age)
    return obj, age


CANARY_STATE = Path("/home/marco/canary/canary_state.json")


def collect_canary():
    """[01/10] Stato del canary C1 (carry DOGE su OKX EEA) — per la dashboard.

    Legge lo state scritto dal monitor `canary_carry.py status` su MARCODG1
    (cron ogni 10'). Nessuna chiamata all'exchange qui: solo il file; se manca,
    errore onesto invece di numeri inventati.
    """
    try:
        st, age = _read_json_smart(str(CANARY_STATE))
        age = int(age)
    except Exception as exc:
        return {"ok": False, "error": "state canary non leggibile: " + exc.__class__.__name__}
    spot = st.get("spot") or {}
    perp = st.get("perp") or {}
    return {
        "ok": bool(st.get("status") == "open" and age < 2400),
        "status": st.get("status"),
        "age_s": age,
        "ts_open": st.get("ts_open"),
        "symbol": "DOGE",
        "spot_qty": spot.get("qty"),
        "spot_avg": spot.get("avg_px"),
        "perp_ct": perp.get("ct"),
        "perp_avg": perp.get("avg_px"),
        "mark": st.get("last_mark"),
        "upl": st.get("last_upl"),
        "funding": st.get("last_funding"),
        "delta_qty": st.get("last_delta"),
        "last_check": st.get("last_check"),
    }



RICERCA_STATO = Path("/home/marco/money/data/ricerca_stato.json")


def collect_ricerca():
    """[15/10] Stato della ricerca edge — per la dashboard.

    Legge il riepilogo scritto da scripts/genera_ricerca.py (verdetti C1/P15/E,
    funding scan, contatore promosse/archiviate). Nessun numero inventato: se il
    file manca, errore onesto.
    """
    try:
        r, age = _read_json_smart(str(RICERCA_STATO))
        age = int(age)
    except Exception as exc:
        return {"ok": False, "error": "stato ricerca non leggibile: " + exc.__class__.__name__}
    return {
        "ok": True,
        "age_s": age,
        "generato_il": r.get("generato_il"),
        "promosse": r.get("promosse"),
        "archiviate": r.get("archiviate"),
        "ultimi": r.get("ultimi") or [],
        "prossimo": r.get("prossimo"),
        "review_c1": r.get("review_c1") or {},
        "funding_scan": r.get("funding_scan") or {},
        "p15_mvrv": r.get("p15_mvrv") or {},
        "nodo_e_basis": r.get("nodo_e_basis") or {},
    }


CARRY_STATO = Path("/home/marco/money/data/carry_stato.json")


def collect_carry():
    """Stato del carry multi-coppia (DOT+ADA, 16/10) per la dashboard."""
    try:
        c, age = _read_json_smart(str(CARRY_STATO))
        age = int(age)
    except Exception as exc:
        return {"ok": False, "error": "stato carry non leggibile: " + exc.__class__.__name__}
    return {"ok": True, "age_s": age,
            "coppie_aperte": c.get("coppie_aperte"),
            "nozionale_totale_eur": c.get("nozionale_totale_eur"),
            "upl_totale": c.get("upl_totale"),
            "candidate": c.get("candidate") or [],
            "coppie": c.get("coppie") or {}}


BANCO_HEALTH = "/home/marco/money/logs/banco_secco_health.json"
BANCO_JSONL = "/home/marco/money/logs/banco_secco.jsonl"
BANCO_HISTORY_CACHE = "/home/marco/money/data/banco_history.json"


def collect_banco():
    """[18/10] Il banco a secco (read-only) riconciliato: equity per comparto.

    Fonte: banco_secco_health.json su MARCODG1 (run ogni ~2'). Se il file non e'
    leggibile il campo e' ok=False: niente numeri inventati.
    """
    try:
        b, age = _read_json_smart(BANCO_HEALTH)
        age = int(age)
    except Exception as exc:
        return {"ok": False, "error": "banco non leggibile: " + exc.__class__.__name__}
    return {
        "ok": True, "age_s": age,
        "ts": b.get("timestamp"), "esito": b.get("esito"),
        "equity_eur": b.get("equity_eur"),
        "equity_trading_eur": b.get("equity_trading_eur"),
        "equity_funding_eur": b.get("equity_funding_eur"),
        "equity_savings_eur": b.get("equity_savings_eur"),
        "riconciliazione_quadra": b.get("riconciliazione_quadra"),
        "ordini_aperti": b.get("ordini_aperti"),
        "chiave_solo_lettura": b.get("chiave_solo_lettura"),
    }


def _parse_banco_row(line: str):
    """Una riga JSONL del banco -> (ts_unix, equity_eur, savings_eur) o None."""
    try:
        r = json.loads(line)
        ts_raw = str(r.get("timestamp") or "")
        if not ts_raw:
            return None
        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).timestamp()
        eq = r.get("equity_eur")
        if eq is None:
            return None
        sav = r.get("equity_savings_eur")
        return (ts, float(eq), float(sav) if sav is not None else None)
    except Exception:
        return None


def build_equity_series(rows, now):
    """Serie equity/savings per la dashboard: finestre 24h (5'), 7g (1h), 14g (2h).

    rows: iterabile di (ts, equity, savings|None). Ultimo punto di ogni bucket;
    delta e summary calcolati dai punti REALI (mai interpolati).
    """
    pts = sorted((r for r in rows if r), key=lambda x: x[0])
    # Coerenza (18/10): il banco ha avuto salti di CONTABILITA' (comparti non letti
    # per giorni: 10-14/10 l'equity segnava ~120→22 invece di ~1.100). Un salto
    # >25% tra punti consecutivi marca un cambio di metro: si tiene SOLO l'ultimo
    # segmento coerente — mai mischiare due metri in un grafico o in un delta.
    _breaks = []
    for _i in range(1, len(pts)):
        _a, _b = pts[_i - 1][1], pts[_i][1]
        if _a and _b and abs(_b / _a - 1) > 0.25:
            _breaks.append(pts[_i][0])
    if _breaks:
        _cut = _breaks[-1]
        pts = [p for p in pts if p[0] >= _cut]

    def _win(secs, bucket):
        lo = now - secs
        out = []
        cur = None
        for p in pts:
            if p[0] < lo:
                continue
            b = int(p[0] // bucket)
            if cur != b:
                out.append(list(p))
                cur = b
            else:
                out[-1] = list(p)
        return [[round(p[0]), round(p[1], 2),
                 (round(p[2], 2) if p[2] is not None else None)] for p in out]

    def _at(target):
        cand = [p for p in pts if p[0] <= target]
        return cand[-1] if cand else None

    last = pts[-1] if pts else None

    def _delta(secs, idx=1):
        if not last:
            return None
        old = _at(last[0] - secs)
        if not old or last[idx] is None or old[idx] is None:
            return None
        return round(last[idx] - old[idx], 2)

    return {
        "h24": _win(86400, 300),
        "d7": _win(7 * 86400, 3600),
        "d14": _win(14 * 86400, 7200),
        "summary": {
            "now": round(last[0]) if last else None,
            "equity": round(last[1], 2) if last else None,
            "savings": round(last[2], 2) if last and last[2] is not None else None,
            "d24": _delta(86400), "d7": _delta(7 * 86400),
            "earn_d24": _delta(86400, 2), "earn_d7": _delta(7 * 86400, 2),
            "first_ts": round(pts[0][0]) if pts else None,
            "coherent_from": round(pts[0][0]) if pts else None,
            "breaks_dropped": len(_breaks),
            "n": len(pts),
        },
    }


def collect_equity_history():
    """[18/10] Storia del capitale dal banco (jsonl su MARCODG1).

    Su MARCODG1: legge il jsonl e scrive la cache downsamplata (banco_history.json);
    su mc2: legge la cache via ssh (file piccolo, gia' pronto per il grafico).
    """
    if ON_MARCODG1:
        p = Path(BANCO_JSONL)
        try:
            size = p.stat().st_size
            with open(p, "rb") as f:
                if size > 4_000_000:
                    f.seek(size - 4_000_000)
                    f.readline()  # riga parziale in testa: scartata
                raw = f.read().decode("utf-8", "replace")
        except OSError as exc:
            return {"ok": False, "error": "storia banco non leggibile: " + exc.__class__.__name__}
        rows = [_parse_banco_row(l) for l in raw.splitlines()]
        out = build_equity_series(rows, time.time())
        out["ok"] = True
        try:
            Path(BANCO_HISTORY_CACHE).parent.mkdir(parents=True, exist_ok=True)
            Path(BANCO_HISTORY_CACHE).write_text(json.dumps(out))
        except OSError:
            pass
        return out
    try:
        obj, _age = _read_json_smart(BANCO_HISTORY_CACHE, ttl=60.0)
        return obj
    except Exception as exc:
        return {"ok": False, "error": "storia banco non leggibile: " + exc.__class__.__name__}

def collect_services():
    """Stato dei servizi Denaro per macchina (systemctl is-active)."""
    out = {}
    for node_name, cfg in SERVICE_UNITS.items():
        units = cfg["units"]
        if cfg["ssh"] and not (node_name == "mc2" and ON_MC2):
            ssh_args = " ".join(cfg["ssh"])
            # NB: fallback per user unit (mc2: denaro-node-mc2 e' una --user unit;
            # `systemctl is-active` a scope di sistema la legge "inactive").
            cmd = (f"ssh -o BatchMode=yes -o ConnectTimeout=5 {ssh_args} "
                   f"'for u in {' '.join(units)}; do s=$(systemctl is-active $u 2>/dev/null); "
                   f"if [ \"$s\" != active ]; then s=$(XDG_RUNTIME_DIR=/run/user/1000 systemctl --user is-active $u 2>/dev/null); fi; "
                   f"echo $u=$s; done'")
            try:
                r = subprocess.run(["bash", "-c", cmd], capture_output=True,
                                   text=True, timeout=20)
                states = {}
                for line in r.stdout.splitlines():
                    if "=" in line:
                        u, s = line.split("=", 1)
                        states[u.strip()] = s.strip()
            except Exception:
                states = {}
        else:
            # Locale: systemctl, con fallback sulle unit --user (su mc2 denaro-node-mc2
            # e' una user unit: a scope di sistema risulta "inactive").
            states = {}
            _env_user = dict(os.environ, XDG_RUNTIME_DIR="/run/user/%d" % os.getuid())
            for u in units:
                try:
                    r = subprocess.run(["systemctl", "is-active", u],
                                       capture_output=True, text=True, timeout=10)
                    s = r.stdout.strip()
                    if s != "active":
                        r2 = subprocess.run(["systemctl", "--user", "is-active", u],
                                            capture_output=True, text=True, timeout=10,
                                            env=_env_user)
                        if r2.stdout.strip() == "active":
                            s = "active"
                    states[u] = s
                except Exception:
                    states[u] = ""
        out[node_name] = {
            "units": {u: (1 if states.get(u) == "active" else 0) for u in units},
            "all_active": all(states.get(u) == "active" for u in units),
        }
    return out


def write_trend(points):
    try:
        (HEALTH_DIR / "trend.json").write_text(json.dumps(points))
    except Exception:
        pass


def collect():
    data = {"generated": time.time(), "ts_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    # 1) Card dei bot (2026-10-18, pulizia «togli i vecchi»): le card ufficiali
    #    sono SOLO quelle dell'officina paper ("<nodo>:paper:<SYM>"); le vecchie
    #    card "mc2:okx:*" (pre-officina, puntavano a file inesistenti -> no_file)
    #    sono state rimosse: i 7 bot mc2 sono GLI STESSI della flotta paper e le
    #    loro card si riempiono qui sotto dal backfill di node_bots.
    bots = {}
    data["bots"] = bots

    # 2) Saldi REALI: OKX main + subaccount (locale e via SSH) + Kraken
    balances = {}

    # 2a) conti con .env LOCALE su questa macchina
    locali, remoti = sorgenti_conti()
    for label, (path, prefix) in locali.items():
        env = load_env(path)
        acct = {k[len(prefix):]: v for k, v in env.items() if k.startswith(prefix)} if prefix else env
        if acct.get("OKX_API_KEY"):
            balances[label] = fetch_okx_balance(acct)
        else:
            balances[label] = {"ok": False, "error": "no key"}

    # 2b) conti con chiavi IP-bound: letti SULLA macchina che le possiede
    for label, (ssh_target, ssh_port, remote_env, remote_py, prefix) in remoti.items():
        res = fetch_remote_okx_balance(ssh_target, ssh_port, remote_env,
                                       remote_py, prefix)
        balances[label] = res if res else {"ok": False, "error": "ssh/ccxt fallito"}

    # 2c) Kraken RIMOSSO dal capitale (decommissionato 19/09/2026 per decisione
    # del proprietario). Non si colleziona piu': la polvere residua (~0.02 EUR)
    # non deve entrare nel totale della dashboard. KRAKEN_ENV_FILES e
    # fetch_kraken_balance restano per memoria storica, senza consumer.

    data["balances"] = balances

    # Capitale reale valorizzato dai saldi (account deduplicati)
    real_total, equity_detail, unpriced = balance_eur(balances)
    data["equity_breakdown"] = equity_detail
    data["equity_unpriced"] = unpriced

    # 3) Prezzi
    data["prices"] = fetch_prices()

    # 4) Nodi
    nodes = {}
    for name, (host, port) in NODES.items():
        nodes[name] = {"reachable": ping_host(host, port), "host": host}
    data["nodes"] = nodes
    # 4b) Repo: il codice che gira e quello committato?
    try:
        import importlib.util as _ilu
        _spec_ir = _ilu.spec_from_file_location(
            "infra_repo_money", str(Path(__file__).resolve().parent / "infra_repo.py"))
        _ir = _ilu.module_from_spec(_spec_ir)
        _spec_ir.loader.exec_module(_ir)
        data["repo"] = _ir.stato_repo()
    except Exception as e:  # noqa: BLE001
        data["repo"] = {"errore": str(e)[:120]}

    # 5) Zabbix + tunnel
    data["zabbix"] = zabbix_state()
    data["docker"] = docker_state()

    # 6) Sistema
    data["system"] = system_state()

    # 8) Node (Fase 3) — tutti i bot (paper + live) + aggregati
    node_bots = collect_node_bots()
    data["node_bots"] = node_bots

    # Le card ufficiali dei bot vivono in node_bots con la chiave officina
    # "<nodo>:paper:<SYM>" (o ":live:" quando esistera' un bot live). Qui si
    # riempie data["bots"] con quelle: se una lettura fallisce la card sparisce
    # dal payload e i consumer (dashboard, Zabbix, alert) non vedono fossili.
    for _k, _v in node_bots.items():
        if not isinstance(_v, dict) or _v.get("stale"):
            continue
        if ":paper:" in _k:
            if _k not in bots or bots[_k].get("status") in (None, "no_file", "error"):
                bots[_k] = _v

    # 6c) FRESCHEZZA delle card (2026-09-20). Le card della flotta devono
    # mostrare solo bot che stanno lavorando ADESSO: un health di giorni fa
    # con status "running" e' un fossile, e veniva mostrato come stato attuale.
    # Il JS salta le card con stale=true; qui si applica lo stesso metro di
    # collect_node_bots (timestamp piu' vecchio di BOT_STALE_S).
    _now = time.time()
    for _k, _h in bots.items():
        if not isinstance(_h, dict) or _h.get("stale"):
            continue
        try:
            _ts = float(_h.get("timestamp") or 0.0)
        except (TypeError, ValueError):
            _ts = 0.0
        if not _ts or (_now - _ts) > BOT_STALE_S:
            _h["stale"] = True
            _h["age_s"] = round(_now - _ts, 1) if _ts else None

    # 7) CAPITALE TOTALE REALE = somma dei SALDI reali (account deduplicati).
    #    Prima esistevano due costanti hardcoded (24.0 e 25.47): con 75 EUR
    #    investiti la dashboard mostrava sempre 24 EUR.
    okx_eq = sum(b.get("total_equity", 0) for k, b in node_bots.items()
                 if "mc2:okx" in k and b.get("status") == "running"
                 and not b.get("stale"))
    kraken_eq = sum(b.get("total_equity", 0) for k, b in node_bots.items()
                    if "trend-live" in k and b.get("status") == "running"
                    and not b.get("stale"))
    data["bot_equity"] = round(okx_eq, 2)
    data["kraken_equity"] = round(kraken_eq, 2)
    if real_total > 0:
        data["total_equity"] = round(real_total, 2)
        data["equity_source"] = "balances"
    else:
        data["total_equity"] = round(okx_eq + kraken_eq, 2)
        data["equity_source"] = "bots"

    # ONESTA' DELLA TELEMETRIA (2026-09-16). Due difetti osservati dal vivo:
    #  1) il PnL dei bot PAPER (equity virtuali, capitali da 100-300 EUR) veniva
    #     sommato al PnL reale: la dashboard mostrava +26,44 EUR mentre il
    #     risultato realizzato era circa -0,30 EUR;
    #  2) i bot con health vecchio (nodi spenti) contavano come "running".
    # Ora: "running" = vivo, non stale e recente; paper e live separati.
    live_running = [b for b in node_bots.values()
                    if b.get("status") == "running" and not b.get("stale")
                    and b.get("mode") == "live"]
    paper_running = [b for b in node_bots.values()
                     if b.get("status") == "running" and not b.get("stale")
                     and b.get("mode") != "live"]
    node_running = live_running
    data["node_total_pnl"] = round(sum(b.get("pnl", 0) for b in live_running), 4)
    data["node_paper_pnl"] = round(sum(b.get("pnl", 0) for b in paper_running), 4)
    data["node_live_bots"] = len(live_running)
    data["node_paper_bots"] = len(paper_running)
    data["node_stale_bots"] = sorted(k for k, b in node_bots.items()
                                     if isinstance(b, dict) and b.get("stale"))
    data["node_total_trades"] = sum(b.get("trades", 0) for b in live_running)
    wins = sum(b.get("wins", 0) for b in live_running)
    losses = sum(b.get("losses", 0) for b in live_running)
    data["node_win_rate"] = round(wins / (wins + losses) * 100, 1) if (wins + losses) else 0
    data["node_errors"] = {sym: b.get("error", "")
                           for sym, b in node_bots.items() if b.get("error")}

    # 8b) Totali PER NODO: marcodg1 (locale) + nuvola + mc2 (via SSH)
    node_totals = {}
    all_node_names = ["marcodg1"] + list(REMOTE_NODES.keys())
    remote_prefixes = tuple(f"{n}:" for n in REMOTE_NODES)
    for node_name in all_node_names:
        if node_name == "marcodg1":
            nb = {k: v for k, v in node_bots.items()
                  if not k.startswith(remote_prefixes)}
        else:
            prefix = f"{node_name}:"
            nb = {k: v for k, v in node_bots.items() if k.startswith(prefix)}
        running = [b for b in nb.values()
                   if b.get("status") == "running" and not b.get("stale")
                   and b.get("mode") == "live"]
        # paper: dedup per simbolo (lo stesso file puo' arrivare da due chiavi:
        # "<nodo>:<SYM>" dal glob legacy e "<nodo>:paper:<SYM>" dall'officina).
        _paper = {}
        for _bk, _bv in nb.items():
            if (_bv.get("status") == "running" and not _bv.get("stale")
                    and _bv.get("mode") != "live"):
                _paper[_bv.get("symbol") or _bk] = _bv
        paper_running = _paper
        node_totals[node_name] = {
            "bots": len(nb),
            "running": len(running),
            "paper_running": len(paper_running),
            "paper_equity": round(sum(b.get("total_equity", 0) for b in paper_running.values()), 2),
            "pnl": round(sum(b.get("pnl", 0) for b in running), 4),
            "trades": sum(b.get("trades", 0) for b in running),
            "equity": round(sum(b.get("total_equity", 0) for b in running), 2),
            "reachable": (node_name == "marcodg1"
                          or any(h.get("timestamp") for h in nb.values())),
        }
    data["node_totals"] = node_totals
    data["canary"] = collect_canary()
    data["ricerca"] = collect_ricerca()
    data["carry"] = collect_carry()
    data["banco"] = collect_banco()
    data["equity_history"] = collect_equity_history()
    data["services"] = collect_services()
    data["trend"] = read_trend()[-240:]
    return data


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        body = json.dumps(payload, indent=1).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")
        try:
            if path in ("/infra.json", "/api/infra.json", ""):
                # Preferisce lo snapshot pre-generato (istantaneo); fallback live
                snap_path = HEALTH_DIR / "infra_snapshot.json"
                if snap_path.exists():
                    try:
                        payload = json.loads(snap_path.read_text())
                        # Uno snapshot troppo VECCHIO non e' rappresentativo
                        # (i flag stale dei bot si congelano alla generazione):
                        # meglio una collect live, lenta ma onesta.
                        age = time.time() - payload.get("generated", 0)
                        if age <= SNAP_MAX_AGE_S:
                            payload["cached"] = True
                            payload["cached_age"] = round(age, 1)
                            self._send(200, payload)
                            return
                    except Exception:
                        pass
                self._send(200, collect())
            elif path == "/health":
                bots = {}
                for name in ("sol", "ada"):
                    p = HEALTH_DIR / f"{name}.json"
                    if p.exists():
                        try:
                            bots[name] = json.loads(p.read_text())
                        except Exception:
                            pass
                ok = len(bots) > 0 and all(b.get("status") == "running" for b in bots.values())
                self._send(200, {"status": "healthy" if ok else "degraded",
                                 "timestamp": time.time(), "bots": bots})
            else:
                self._send(404, {"status": "not_found"})
        except Exception as e:
            self._send(500, {"status": "error", "error": str(e)})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print(f"Infra aggregator on {HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
