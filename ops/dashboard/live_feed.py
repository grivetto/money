#!/usr/bin/env python3
"""live_feed.py — daemon «denaro LIVE» (MARCODG1): trading attivi in tempo reale.

Direttiva owner 29/10/2026: console grafica che mostra le posizioni APERTE
su OKX main aggiornate ogni pochi secondi, sola lettura.

Ogni ciclo (default 5 s):
  - fetch_positions() (ccxt, chiavi in sola lettura dall'env-file; MAI stampate);
  - saldi spot/perp (fetch_balance) ogni ~20 s;
  - funding rate corrente + prossimo incasso (endpoint pubblico, cache 4 min);
  - sparkline: candele mark 1m ultime 2h (endpoint pubblico, cache 60 s);
  - riferimento equity dal collector live_trading.json (scritto ogni minuto).
Scrive ATOMICAMENTE ops/dashboard/livefeed.json (servito da serve_dashboard
:8913 sulla route /api/livefeed.json).

Se una fonte fallisce la sezione resta all'ultimo valore buono con 'stale_s':
mai numeri inventati. Mai ordini, mai scritture fuori da livefeed.json.

Uso: LIVE_FEED_ONCE=1 per un singolo ciclo (test); LIVE_FEED_INTERVAL per la
cadenza. In produzione: systemd money-live-feed-marcodg1.service.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import ccxt

DASH = Path("/home/marco/money/ops/dashboard")
OUT = DASH / "livefeed.json"
ENV_FILE = Path(os.environ.get("LIVE_FEED_ENV", "/home/marco/money/config/.env_banco"))
ENV_FALLBACK = Path("/home/marco/denaro/secrets/main_okx.env")
REF_LIVE = DASH / "live_trading.json"
OKX_PUBLIC = "https://www.okx.com"
TAG_BY_BASE = {"DOT": "carry", "LTC": "carry", "DOGE": "canary"}
FUNDING_TTL = 240.0
CANDLES_TTL = 60.0
BALANCE_EVERY = 4  # cicli tra due letture del balance

# ── stato persistente tra cicli (last-good per sezione) ────────────────────
_ST: dict = {
    "posizioni": None, "posizioni_t": 0.0,
    "saldi": None, "saldi_t": 0.0,
    "funding": {},      # instId -> (rate, next_ms, fetched_at)
    "candles": {},      # instId -> (closes, fetched_at)
    "ordini": None, "ordini_t": 0.0,
}


def log(msg: str) -> None:
    print("[live_feed] %s" % msg, flush=True)


def read_env(path: Path) -> dict:
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def http_json(url: str, timeout: float = 6.0):
    req = urllib.request.Request(url, headers={"User-Agent": "denaro-live-feed/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def build_client() -> ccxt.Exchange:
    env_file = ENV_FILE if ENV_FILE.exists() else ENV_FALLBACK
    if not env_file.exists():
        raise RuntimeError("env-file mancante: %s" % env_file)
    env = read_env(env_file)
    return ccxt.okx({"apiKey": env.get("OKX_API_KEY"),
                     "secret": env.get("OKX_API_SECRET"),
                     "password": env.get("OKX_PASSPHRASE"),
                     "hostname": "eea.okx.com", "enableRateLimit": True,
                     "options": {"defaultType": "spot"}})


def _f(x, default: float = 0.0) -> float:
    try:
        v = float(x)
        return v if v == v else default  # NaN -> default
    except (TypeError, ValueError):
        return default


def leggi_funding(instId: str) -> dict | None:
    """Funding rate corrente (pubblico). Cache FUNDING_TTL."""
    ora = time.time()
    cached = _ST["funding"].get(instId)
    if cached and ora - cached[2] < FUNDING_TTL:
        rate, next_ms, _ = cached
    else:
        try:
            d = http_json("%s/api/v5/public/funding-rate?instId=%s" % (OKX_PUBLIC, instId))
            row = (d.get("data") or [None])[0]
            if not row:
                return None
            rate = _f(row.get("fundingRate"))
            next_ms = int(_f(row.get("nextFundingTime")))
            _ST["funding"][instId] = (rate, next_ms, ora)
        except Exception as exc:  # noqa: BLE001
            if cached:
                rate, next_ms, _ = cached
            else:
                log("funding %s non leggibile: %s" % (instId, exc))
                return None
    return {"rate": rate, "rate_8h_pct": round(rate * 100, 5),
            "anno_pct": round(rate * 3 * 365 * 100, 2),
            "next_ms": next_ms, "next_iso": _iso(next_ms) if next_ms else None}


def leggi_candles(instId: str) -> list | None:
    """Close delle candele mark 1m, ultime 2h (pubblico). Cache CANDLES_TTL."""
    ora = time.time()
    cached = _ST["candles"].get(instId)
    if cached and ora - cached[1] < CANDLES_TTL:
        return cached[0]
    try:
        d = http_json("%s/api/v5/market/mark-price-candles?instId=%s&bar=1m&limit=120"
                      % (OKX_PUBLIC, instId))
        rows = d.get("data") or []
        closes = [_f(r[4]) for r in reversed(rows)]
        _ST["candles"][instId] = (closes, ora)
        return closes
    except Exception as exc:  # noqa: BLE001
        log("candles %s non leggibili: %s" % (instId, exc))
        return cached[0] if cached else None


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def posizioni_json(ex: ccxt.Exchange, saldi: dict | None) -> list[dict]:
    """Posizioni aperte, AGGREGATE per instId (lezione P34-F1: una stessa instId
    puo' avere piu' righe isolated+cross — si sommano i contratti firmati, gli uPL
    e i collaterali; l'entry e' la media pesata; la liq e' quella piu' vicina al mark)."""
    gruppi: dict[str, list[dict]] = {}
    for p in ex.fetch_positions() or []:
        info = p.get("info") or {}
        signed = _f(info.get("pos"))
        side = (p.get("side") or ("short" if signed < 0 else "long")).lower()
        ct = abs(signed) if signed else abs(_f(p.get("contracts")))
        if ct == 0:
            continue
        instId = info.get("instId") or p.get("symbol") or "?"
        ct_val = _f(info.get("ctVal")) or _f(p.get("contractSize")) or 0.0
        if not signed:
            signed = ct * (-1 if side == "short" else 1)
        gruppi.setdefault(instId, []).append({
            "signed": signed, "ct_val": ct_val,
            "mark": _f(p.get("markPrice")) or _f(info.get("markPx")),
            "entry": _f(p.get("entryPrice")) or _f(info.get("avgPx")),
            "upl": _f(p.get("unrealizedPnl")) or _f(info.get("upl")),
            "liq": _f(p.get("liquidationPrice")) or _f(info.get("liqPx")),
            "coll": _f(p.get("collateral")) or _f(info.get("imr")),
            "lev": _f(p.get("leverage")) or _f(info.get("lever")),
            "mgn": p.get("marginMode") or info.get("mgnMode") or "",
            "base": (p.get("base") or instId.split("-")[0] or "?").split("/")[0],
        })
    out: list[dict] = []
    for instId, righe in gruppi.items():
        mark = next((r["mark"] for r in righe if r["mark"] > 0), 0.0)
        ct_val = next((r["ct_val"] for r in righe if r["ct_val"]), 0.0)
        signed_tot = sum(r["signed"] for r in righe)
        qty_base = signed_tot * ct_val
        side = "short" if signed_tot < 0 else "long"
        upl = sum(r["upl"] for r in righe)
        coll = sum(r["coll"] for r in righe)
        wsum = sum(abs(r["signed"]) * r["entry"] for r in righe if r["entry"] > 0)
        wtot = sum(abs(r["signed"]) for r in righe if r["entry"] > 0)
        entry = (wsum / wtot) if wtot else (righe[0]["entry"] if righe else 0.0)
        liqs = [r["liq"] for r in righe if r["liq"] > 0 and mark > 0]
        liq = min(liqs, key=lambda x: abs(x - mark)) if liqs else 0.0
        levs = sorted({r["lev"] for r in righe if r["lev"]})
        mgns = sorted({r["mgn"] for r in righe if r["mgn"]})
        lev = levs[0] if len(levs) == 1 else ("/".join(str(int(x)) for x in levs) if levs else 0)
        mgn = mgns[0] if len(mgns) == 1 else ("mixed" if mgns else "")
        base = righe[0]["base"]
        liq_dist = None
        if mark > 0 and liq > 0:
            liq_dist = (liq - mark) / mark * 100 if side == "short" else (mark - liq) / mark * 100
        spot_qty = None
        delta = None
        delta_pct = None
        if saldi is not None:
            spot_qty = _f((saldi.get(base) or {}).get("total"))
            delta = spot_qty + qty_base
            if qty_base:
                delta_pct = delta / abs(qty_base) * 100
        funding = leggi_funding(instId)
        nozionale = abs(qty_base) * mark
        contrib_day = None
        if funding and nozionale:
            segno = 1.0 if side == "short" else -1.0
            contrib_day = funding["rate"] * 3 * nozionale * segno
        out.append({
            "instId": instId, "base": base, "tag": TAG_BY_BASE.get(base, "perp"),
            "side": side, "ct": round(abs(signed_tot), 8), "ctVal": ct_val,
            "righe": len(righe),
            "qty_base": round(qty_base, 8), "mark": mark, "entry": entry,
            "upl_usd": round(upl, 6), "upl_pct": round(upl / coll * 100, 3) if coll else None,
            "liq": liq, "liq_dist_pct": round(liq_dist, 2) if liq_dist is not None else None,
            "lev": lev, "mgn": mgn,
            "spot_qty": round(spot_qty, 8) if spot_qty is not None else None,
            "delta_base": round(delta, 8) if delta is not None else None,
            "delta_pct": round(delta_pct, 4) if delta_pct is not None else None,
            "funding": funding, "nozionale_usd": round(nozionale, 2),
            "funding_giorno_usd": round(contrib_day, 4) if contrib_day is not None else None,
        })
    return out


def saldi_json(ex: ccxt.Exchange) -> dict:
    b = ex.fetch_balance()
    total = b.get("total") or {}
    out: dict[str, dict] = {}
    for k, v in total.items():
        t = _f(v)
        if abs(t) < 1e-9:
            continue
        out[k] = {"total": round(t, 8),
                  "free": _f((b.get("free") or {}).get(k)),
                  "used": _f((b.get("used") or {}).get(k))}
    # ordine: stables primi, poi alfabetico
    def key(k: str):
        return (0 if k in ("USDC", "USDT", "USD") else 1, k)
    return {k: out[k] for k in sorted(out, key=key)}


def ordini_json(ex: ccxt.Exchange) -> list[dict]:
    out = []
    for o in ex.fetch_open_orders() or []:
        out.append({"instId": (o.get("info") or {}).get("instId") or o.get("symbol"),
                    "side": o.get("side"), "type": o.get("type"),
                    "amount": o.get("amount"), "price": o.get("price"),
                    "ts": o.get("timestamp")})
    return out


def ref_economia() -> dict | None:
    try:
        d = json.loads(REF_LIVE.read_text(encoding="utf-8"))
        eq = d.get("equity") or {}
        return {"equity_eur": eq.get("totale_eur"), "delta24_eur": eq.get("delta24_eur"),
                "delta24_pct": eq.get("delta24_pct"), "equity_ts": eq.get("ts"),
                "risparmi_eur": eq.get("risparmi_eur")}
    except (OSError, ValueError):
        return None


def write_atomic(obj: dict) -> None:
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, OUT)


def ciclo(ex: ccxt.Exchange, n: int) -> dict:
    ora = time.time()
    errori: list[str] = []

    # saldi ogni BALANCE_EVERY cicli (o al primo)
    if _ST["saldi"] is None or n % BALANCE_EVERY == 1:
        try:
            _ST["saldi"] = saldi_json(ex)
            _ST["saldi_t"] = ora
        except Exception as exc:  # noqa: BLE001
            errori.append("saldi: %s" % exc)
    try:
        _ST["posizioni"] = posizioni_json(ex, _ST["saldi"])
        _ST["posizioni_t"] = ora
    except Exception as exc:  # noqa: BLE001
        errori.append("posizioni: %s" % exc)

    # ordini aperti (ogni 4 cicli)
    if _ST["ordini"] is None or n % BALANCE_EVERY == 0:
        try:
            _ST["ordini"] = ordini_json(ex)
            _ST["ordini_t"] = ora
        except Exception as exc:  # noqa: BLE001
            errori.append("ordini: %s" % exc)

    posizioni = _ST["posizioni"] or []
    upl_tot = sum(p["upl_usd"] for p in posizioni)
    fund_day = sum(p["funding_giorno_usd"] or 0.0 for p in posizioni)
    spark: dict[str, list] = {}
    for p in posizioni[:4]:
        closes = leggi_candles(p["instId"])
        if closes:
            spark[p["base"]] = closes

    stale = {"posizioni_s": round(ora - _ST["posizioni_t"]) if _ST["posizioni_t"] else None,
             "saldi_s": round(ora - _ST["saldi_t"]) if _ST["saldi_t"] else None,
             "ordini_s": round(ora - _ST["ordini_t"]) if _ST["ordini_t"] else None}
    return {
        "ok": not errori and _ST["posizioni"] is not None,
        "ts": int(ora * 1000), "ts_iso": _iso(int(ora * 1000)),
        "venue": "OKX EEA", "conto": "main", "ciclo": n,
        "posizioni": posizioni, "n_posizioni": len(posizioni),
        "upl_totale_usd": round(upl_tot, 6),
        "funding_giorno_usd": round(fund_day, 4),
        "saldi": _ST["saldi"] or {},
        "ordini": _ST["ordini"] or [],
        "spark": spark,
        "ref": ref_economia(),
        "stale": stale, "errori": errori,
    }


def main() -> int:
    interval = max(2.0, _f(os.environ.get("LIVE_FEED_INTERVAL", "5"), 5.0))
    once = os.environ.get("LIVE_FEED_ONCE") == "1"
    ex = build_client()
    log("avvio: intervallo %.0fs, out=%s" % (interval, OUT))
    n = 0
    while True:
        n += 1
        t0 = time.time()
        try:
            obj = ciclo(ex, n)
        except Exception as exc:  # noqa: BLE001
            log("ERRORE ciclo: %s" % exc)
            if once:
                return 1
            time.sleep(interval)
            continue
        try:
            write_atomic(obj)
        except OSError as exc:
            log("scrittura fallita: %s" % exc)
        if once:
            log("ciclo singolo ok: posizioni=%d errori=%s" % (obj["n_posizioni"], obj["errori"]))
            return 0 if obj["ok"] else 1
        if n % 12 == 1 or obj["errori"]:
            log("ciclo %d: posizioni=%d upl=%s errori=%s" %
                (n, obj["n_posizioni"], obj["upl_totale_usd"], obj["errori"]))
        time.sleep(max(0.5, interval - (time.time() - t0)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
