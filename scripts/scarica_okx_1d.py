#!/usr/bin/env python3
"""scarica_okx_1d.py — preflight prezzi E11 (REQ-MERL-20261029-025).

Candele 1D OKX (endpoint pubblico v5 `market/history-candles`, paginazione
all'indietro via `after`) per BTC-USDT e ETH-USDT, finestra 2019-01-01 ->
2026-10-28 inclusa (la barra del 28/10, chiusa).

Formato di uscita = convenzione cache del progetto:
    {venue, simbolo, timeframe, barre: [[ts_ms, o, h, l, c, v], ...]} con ts crescente.

Validazione (monotonìa, duplicati, gap, null, varianza) in
`validazione_preflight.json`, nello stesso stile del resto dei preflight del repo.

Uso:  python3 scarica_okx_1d.py [--out DIR] [--simboli BTC-USDT ETH-USDT]
"""
from __future__ import annotations

import argparse
import json
import math
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://eea.okx.com"
BAR = "1D"
INIZIO_MS = 1_546_300_800_000   # 2019-01-01T00:00:00Z
FINE_MS = 1_793_232_000_000     # 2026-10-29T00:00:00Z (include tutta la barra del 28/10)
LIMIT = 300
MS_GIORNO = 86_400_000
SIMBOLI = ["BTC-USDT", "ETH-USDT"]


def iso(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M")


def get_json(url: str, tentativi: int = 4) -> list:
    ultimo: Exception | None = None
    for i in range(tentativi):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=25) as r:
                d = json.loads(r.read().decode())
            if d.get("code") != "0":
                raise RuntimeError(f"OKX code {d.get('code')}: {d.get('msg')}")
            return d["data"]
        except Exception as e:  # noqa: BLE001
            ultimo = e
            if i == tentativi - 1:
                raise
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"irraggiungibile: {ultimo}")


def scarica(simbolo: str) -> tuple[list[list], int]:
    """Barre ASCENDENTI, dedup per ts, finestra [INIZIO_MS, FINE_MS); solo candele confermate."""
    per_ts: dict[int, list] = {}
    non_confermate: set = set()
    after = FINE_MS
    call = 0
    while call < 80:
        call += 1
        url = (f"{BASE}/api/v5/market/history-candles?instId={simbolo}"
               f"&bar={BAR}&after={after}&limit={LIMIT}")
        data = get_json(url)
        if not data:
            break
        nuovi = 0
        for r in data:
            ts = int(r[0])
            if not (INIZIO_MS <= ts < FINE_MS) or ts in per_ts:
                continue
            if r[8] != "1":
                # candela non confermata (in formazione): esclusa come il "giorno corrente parziale"
                non_confermate.add(ts)
                continue
            # candela OKX: [ts, o, h, l, c, vol(base), volCcy, volCcyQuote, confirm]
            per_ts[ts] = [ts, float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])]
            nuovi += 1
        m = min(int(r[0]) for r in data)
        if m < INIZIO_MS:
            break
        if nuovi == 0 and call > 1:
            break
        after = m
        time.sleep(0.25)
    print(f"{simbolo}: {call} call, {len(per_ts)} barre in finestra, "
          f"{len(non_confermate)} scartate (non confermate)")
    return [per_ts[k] for k in sorted(per_ts)], len(non_confermate)


def valida(barre: list[list], simbolo: str) -> dict:
    ts = [b[0] for b in barre]
    rep: dict = {"simbolo": simbolo, "n_barre": len(barre)}
    rep["primo"] = iso(ts[0]) if ts else None
    rep["ultimo"] = iso(ts[-1]) if ts else None
    rep["monotona_stretta"] = all(ts[i] < ts[i + 1] for i in range(len(ts) - 1))
    rep["duplicati"] = len(ts) - len(set(ts))
    gaps = [(ts[i], ts[i + 1]) for i in range(len(ts) - 1) if ts[i + 1] - ts[i] > MS_GIORNO]
    rep["gap_n"] = len(gaps)
    rep["gap_giorni_totali"] = int(sum((b - a) // MS_GIORNO - 1 for a, b in gaps))
    rep["gap_esempi"] = [[iso(a), iso(b)] for a, b in gaps[:5]]
    nulli = 0
    for b in barre:
        for x in b[1:6]:
            if x is None or (isinstance(x, float) and math.isnan(x)):
                nulli += 1
    rep["valori_null"] = nulli
    viol = 0
    for _, o, h, l, c, _v in barre:
        if not (l <= min(o, c) and max(o, c) <= h):
            viol += 1
    rep["ohlc_violazioni"] = viol
    rets = [barre[i + 1][4] / barre[i][4] - 1.0 for i in range(len(barre) - 1)]
    n = len(rets)
    m = sum(rets) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in rets) / n)
    rep["ret_media_giornaliera"] = m
    rep["ret_stdev_giornaliera"] = sd
    rep["ret_min"] = min(rets)
    rep["ret_max"] = max(rets)
    rep["close_primo"] = barre[0][4]
    rep["close_ultimo"] = barre[-1][4]
    return rep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent / "prezzi"))
    ap.add_argument("--simboli", nargs="*", default=SIMBOLI)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    report = {
        "venue": "okx",
        "endpoint": f"{BASE}/api/v5/market/history-candles",
        "bar": BAR,
        "finestra_richiesta": [iso(INIZIO_MS), iso(FINE_MS)],
        "scarica_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "per_simbolo": {},
    }
    for simbolo in args.simboli:
        barre, n_nc = scarica(simbolo)
        p = out / f"okx_{simbolo}_1D.json"
        payload = {"venue": "okx", "simbolo": simbolo, "timeframe": "1D", "barre": barre}
        p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        rep = valida(barre, simbolo)
        rep["barre_scartate_non_confermate"] = n_nc
        report["per_simbolo"][simbolo] = rep
        print(f"{simbolo}: {rep['n_barre']} barre | {rep['primo']} -> {rep['ultimo']} | "
              f"gap={rep['gap_n']} ({rep['gap_giorni_totali']}g) | duplicati={rep['duplicati']} | "
              f"null={rep['valori_null']} | ohlc_viol={rep['ohlc_violazioni']} | "
              f"stdev_ret={rep['ret_stdev_giornaliera']:.4f} | {p}")

    (out / "validazione_preflight.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nvalidazione: {out / 'validazione_preflight.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
