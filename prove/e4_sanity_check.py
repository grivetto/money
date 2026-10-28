#!/usr/bin/env python3
"""e4_sanity_check.py — verifica INDIPENDENTE del segno del segnale momentum cross-sezionale.

Scritto da zero (numpy puro, nessun import dal motore) per escludere un bug di segno o di
timing in scripts/crosssec_mom_vol.py: misura lo spread quintile lordo (top − bottom,
momentum 63d normalizzato per vol 60d, ribilanciamento settimanale, esecuzione con 1 barra
di ritardo) e la media lorda del top quintile (long-only) SOLO sul periodo OOS (>= 2024-06-01),
senza costi.

Esito del run del 2026-10-26 (pannello okx_eea 1d, 87 simboli):
  LS spread lordo: media/sett −0,3645% | CAGR −18,38% | t −1,83
  LO top-quintile lordo: media/sett −0,4533% | CAGR −22,71% | t −1,77
→ il segno negativo misurato dal motore è confermato da un'implementazione diversa:
  il momentum cross-sezionale vol-normalizzato NON ha edge positivo OOS su questo universo.
"""
import json
import glob
import sys

import numpy as np
from datetime import datetime, timezone

ESCLUSI = {"CTC", "GAS", "USDC"}
L, V = 63, 60


def main() -> int:
    sym_ts, sym_cl = {}, {}
    for p in glob.glob("data/cache/okx_eea_*-USDT_1d.json"):
        sym = p.split("okx_eea_", 1)[1].split("-USDT", 1)[0]
        if sym in ESCLUSI:
            continue
        d = json.load(open(p))
        ts = np.array([int(b[0]) for b in d["barre"]], dtype=np.int64)
        cl = np.array([float(b[4]) for b in d["barre"]], dtype=np.float64)
        m = cl > 0
        sym_ts[sym], sym_cl[sym] = ts[m], cl[m]

    giorni = np.array(sorted({int(t) for ts in sym_ts.values() for t in ts}), dtype=np.int64)
    start = int(datetime(2023, 1, 1).replace(tzinfo=timezone.utc).timestamp() * 1000)
    giorni = giorni[giorni >= start]
    confine = int(datetime.fromisoformat("2024-06-01").replace(tzinfo=timezone.utc).timestamp() * 1000)

    spreads, lo_means = [], []
    prev_wk = None
    for idx, t in enumerate(giorni[:-1]):
        wk = datetime.fromtimestamp(t / 1000, timezone.utc).isocalendar()[1]
        if prev_wk is None or wk != prev_wk:
            prev_wk = wk
            if t < confine:
                continue
            t_ref = giorni[idx - 1]
            scores = {}
            for s, ts in sym_ts.items():
                j = int(np.searchsorted(ts, t_ref, side="right")) - 1
                if j < L or j < V or t_ref - ts[j] > 1.5 * 86_400_000:
                    continue
                r_L = sym_cl[s][j] / sym_cl[s][j - L] - 1
                sig = float(np.std(sym_cl[s][j - V + 1:j + 1] / sym_cl[s][j - V:j] - 1))
                if sig <= 0:
                    continue
                scores[s] = r_L / (sig * np.sqrt(L))
            if len(scores) < 30:
                continue
            k = len(scores) // 5
            order = sorted(scores, key=scores.get, reverse=True)
            top, bot = order[:k], order[-k:]
            r_next = {}
            for s, ts in sym_ts.items():
                j1 = int(np.searchsorted(ts, t, side="right")) - 1
                j2 = int(np.searchsorted(ts, giorni[idx + 1], side="right")) - 1
                if 0 <= j1 < j2 < len(ts):
                    r_next[s] = sym_cl[s][j2] / sym_cl[s][j1] - 1
            st = [r_next[s] for s in top if s in r_next]
            sb = [r_next[s] for s in bot if s in r_next]
            if st and sb:
                spreads.append(np.mean(st) - np.mean(sb))
                lo_means.append(np.mean(st))

    spreads, lo_means = np.array(spreads), np.array(lo_means)
    ann = lambda x: (1 + x).prod() ** (52 / len(x)) - 1  # noqa: E731
    print(f"settimane OOS: {len(spreads)}")
    print(f"LS spread lordo: media/sett {spreads.mean()*100:.4f}% | CAGR {ann(spreads):.2%} | "
          f"t {spreads.mean()/spreads.std()*np.sqrt(len(spreads)):+.2f}")
    print(f"LO top-quintile lordo: media/sett {lo_means.mean()*100:.4f}% | CAGR {ann(lo_means):.2%} | "
          f"t {lo_means.mean()/lo_means.std()*np.sqrt(len(lo_means)):+.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
