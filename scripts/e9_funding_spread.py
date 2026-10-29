#!/usr/bin/env python3
"""E9 — funding-spread cross-venue carry engine.
Spec: ~/money/coda_catena/E9_funding_spread_crossvenue.md (REGOLA CONGELATA — zero gradi di libertà)

Regola operativa (da spec):
  diff = funding_A - funding_B  (per epoca)
  Rolling media 7 epoche, anti-look-ahead: decisione a epoca t usa funding <= t-1
    => rolling_avg(t) = mean(diffs[t-7 .. t-1])   (esclude t)
  Apertura: |rolling_avg| >= 0.0010%/epoca (dec = 0.00001)
    => gambe opposte: long sulla venue col funding minore, short sull'altra
  Chiusura: |rolling_avg| < 0.0002%/epoca (dec = 0.000002) per 3 epoche consecutive
    OPPURE segno invertito per 2 epoche consecutive (uscita immediata)
  P&L per epoca = funding incassato netto (diff * direction); costi solo apertura/chiusura
    => 20bp RT normal (5bp/lato x 2 gambe x 2 venue = 20bp... interpretazione: 20bp RT totale)
    => stress x2: 40bp + slippage 1bp/lato = 42bp RT totale

Output per simbolo e aggregato: epoche aperte, media netto/epoca, t-stat, CI90 bootstrap,
  media a costi x2, persistenza del segno per mese, DSR (N=3).
"""

import json
import math
import os
import random
import sys
from statistics import mean, stdev

# === Costanti spec (CONGELATE) ===
UNIVERSE = ["DOT", "ADA", "LTC", "AVAX", "DOGE"]
THRESHOLD_OPEN = 0.0010 / 100    # 0.00001 per epoca (decimal)
THRESHOLD_CLOSE = 0.0002 / 100   # 0.000002 per epoca (decimal)
ROLLING_WINDOW = 7
COSTS_RT = 0.0020               # 20bp round trip (normal)
STRESS_MULT = 2.0               # stress x2
SLIPPAGE_PER_LEG = 0.0001       # 1bp per lato (x2 lati = 2bp)
STRESS_COSTS_RT = COSTS_RT * STRESS_MULT + SLIPPAGE_PER_LEG * 2  # 0.0042 = 42bp
N_DSR = 3                       # numero di strategie nella famiglia funding (P21, E7, E9)

# Expected maximum of N i.i.d. standard normals (Blom approximation)
def expected_max_normal(n):
    """E[max of N i.i.d. N(0,1)] — Blom's approximation."""
    # Blom: p = (i - 3/8) / (n + 1/4), then E[max] = Phi^{-1}(p) for the largest
    p = (n - 3.0/8.0) / (n + 1.0/4.0)
    return _inv_norm(p)

# Inverse CDF of standard normal (rational approximation, Acklam)
def _inv_norm(p):
    if p <= 0:
        return float("-inf")
    if p >= 1:
        return float("inf")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow = 0.02425
    phigh = 1 - plow
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        x = (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
            ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    elif p <= phigh:
        q = p - 0.5
        r = q*q
        x = (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
            (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    else:
        q = math.sqrt(-2 * math.log(1-p))
        x = -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
            ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    # 1 refinement step of Newton-Raphson
    e = 0.5 * math.erfc(-x / math.sqrt(2)) - p
    u = e * math.sqrt(2 * math.pi) * math.exp(x*x/2)
    x = x - u / (1 + x*u/2)
    return x


def load_series(filepath):
    """Carica i dati di funding da JSON, ritorna dict {ts_ms: rate}."""
    with open(filepath) as f:
        data = json.load(f)
    return {int(t[0]): float(t[1]) for t in data["tassi"]}


def align_series(series_a, series_b):
    """Allinea due serie di funding per timestamp comune.
    Ritorna lista di (ts, f_a, f_b) ordinata per ts.
    """
    common_ts = sorted(set(series_a.keys()) & set(series_b.keys()))
    return [(ts, series_a[ts], series_b[ts]) for ts in common_ts]


def rolling_avg_exclusive(diffs, idx, window=ROLLING_WINDOW):
    """Media mobile su `window` epoche, ESCLUSA l'epoca idx (anti-look-ahead).
    rolling_avg(t) = mean(diffs[t-window+1 .. t-1])  → usa epoche [t-7, t-1]
    """
    start = idx - window
    if start < 0:
        return None
    # diffs[start:idx] = diffs[t-window .. t-1], length = window, excludes t
    return sum(diffs[start:idx]) / window


def bootstrap_ci90(values, n_boot=10000, seed=42):
    """90% confidence interval via bootstrap (percentile method)."""
    rng = random.Random(seed)
    if len(values) < 2:
        return (float("nan"), float("nan"))
    means = []
    n = len(values)
    for _ in range(n_boot):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo_idx = int(0.05 * n_boot)
    hi_idx = int(0.95 * n_boot)
    return (means[lo_idx], means[hi_idx])


def t_statistic(values):
    """One-sample t-statistic (H0: mean = 0)."""
    n = len(values)
    if n < 2:
        return float("nan")
    m = sum(values) / n
    sd = stdev(values)
    if sd == 0:
        return float("nan")
    return m / (sd / math.sqrt(n))


def compute_dsr(all_per_epoch_gross, directions_map):
    """DSR (Deflated Sharpe Ratio) con N=3 (famiglia funding: P21, E7, E9).
    SR per-epoch (non annualizzato), T = numero di epoche.
    DSR = (SR_p - SR_hat) / SE(SR_p)
      SR_hat = E[max Z_1..Z_N] / sqrt(T)
      SE(SR) = sqrt((1 + 0.5*SR^2) / T)
    """
    if len(all_per_epoch_gross) < 2:
        return float("nan")
    n = len(all_per_epoch_gross)
    m = sum(all_per_epoch_gross) / n
    sd = stdev(all_per_epoch_gross)
    if sd == 0:
        return float("nan")
    sr = m / sd  # per-epoch Sharpe ratio
    e_max = expected_max_normal(N_DSR)  # ~1.0 for N=3
    # Actually for N=3 standard normals: E[max] ≈ 0.8460
    # But using Blom approximation: E[max] = phi^{-1}((n-3/8)/(n+1/4))
    # For n=3: p = (3 - 3/8) / (3 + 1/4) = (21/8) / (13/4) = (21/8) * (4/13) = 84/104 = 21/26 ≈ 0.8077
    # phi^{-1}(0.8077) ≈ 0.874
    # Hmm, let me use the exact known value for N=3: E[max of 3 iid normals] ≈ 0.846
    # The Blom approximation gives ≈ 0.874, which is a bit high for small N.
    # Let me hardcode the known values for small N:
    e_max_table = {1: 0.0, 2: 0.5642, 3: 0.8462, 4: 1.0294, 5: 1.1630}
    e_max = e_max_table.get(N_DSR, expected_max_normal(N_DSR))
    
    sr_hat = e_max / math.sqrt(n)
    se_sr = math.sqrt((1 + 0.5 * sr * sr) / n)
    if se_sr == 0:
        return float("nan")
    dsr = (sr - sr_hat) / se_sr
    return dsr


def sign_persistence_monthly(aligned, diffs, positions):
    """Calcola la persistenza del segno per mese.
    Per ogni mese, conteggia quante epoche hanno lo stesso segno del diff medio del mese.
    """
    from datetime import datetime, timezone

    monthly_diffs = {}
    for idx, (ts, _, _) in enumerate(aligned):
        dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        mk = (dt.year, dt.month)
        monthly_diffs.setdefault(mk, []).append(diffs[idx])

    result = {}
    for mk in sorted(monthly_diffs.keys()):
        vals = monthly_diffs[mk]
        if not vals:
            continue
        mean_diff = sum(vals) / len(vals)
        if abs(mean_diff) < 1e-30:
            result[str(mk)] = 0.0
            continue
        sign = 1 if mean_diff > 0 else -1
        same_sign = sum(1 for v in vals if (v > 0) == (sign > 0)) / len(vals)
        result[str(mk)] = round(same_sign * 100, 2)
    return result


def run_strategy(aligned, venue_a_name="bybit", venue_b_name="binance"):
    """Esegue la strategia E9 sui dati allineati.
    aligned: lista di (ts, f_a, f_b) dove f_a = funding venue A, f_b = funding venue B
    diff = f_a - f_b
    Se diff > 0: long B (funding minore), short A → P&L per epoca = diff
    Se diff < 0: long A (funding minore), short B → P&L per epoca = -diff
    direzione = sign(rolling_avg) al momento dell'apertura
    """
    n = len(aligned)
    if n < ROLLING_WINDOW + 1:
        return {"error": "Not enough data"}

    diffs = [f_a - f_b for _, f_a, f_b in aligned]

    # Strategy state
    in_position = False
    direction = 0  # +1: long B short A, -1: long A short B
    pos_start_idx = -1
    close_below_count = 0
    sign_flip_count = 0
    prev_roll_sign = 0

    positions = []          # list of position dicts
    per_epoch_gross = []     # gross P&L per open epoch (list of (epoch_idx, gross))

    for t in range(n):
        roll = rolling_avg_exclusive(diffs, t, ROLLING_WINDOW)
        if roll is None:
            continue

        roll_abs = abs(roll)
        roll_sign = 1 if roll > 0 else (-1 if roll < 0 else 0)

        if not in_position:
            if roll_abs >= THRESHOLD_OPEN and roll_sign != 0:
                # Open position: long sulla venue col funding minore
                in_position = True
                direction = roll_sign
                pos_start_idx = t
                close_below_count = 0
                sign_flip_count = 0
                prev_roll_sign = roll_sign
        else:
            # Check closing conditions
            should_close = False
            if roll_abs < THRESHOLD_CLOSE:
                close_below_count += 1
                if close_below_count >= 3:
                    should_close = True
            else:
                close_below_count = 0

            if roll_sign != 0 and roll_sign != prev_roll_sign:
                sign_flip_count += 1
                if sign_flip_count >= 2:
                    should_close = True
            else:
                sign_flip_count = 0
            prev_roll_sign = roll_sign if roll_sign != 0 else prev_roll_sign

            if should_close:
                # Close: position was open for [pos_start_idx, t-1]
                pos_end_idx = t - 1
                pos_epochs = t - pos_start_idx  # epochs collected (start to t-1)
                pos_gross = sum(direction * diffs[i] for i in range(pos_start_idx, t))
                positions.append({
                    "start_ts": aligned[pos_start_idx][0],
                    "end_ts": aligned[pos_end_idx][0],
                    "direction": direction,
                    "n_epochs": pos_epochs,
                    "gross": pos_gross,
                })
                for i in range(pos_start_idx, t):
                    per_epoch_gross.append((i, direction * diffs[i]))
                open_epochs = sum(p["n_epochs"] for p in positions)
                in_position = False
                direction = 0
                pos_start_idx = -1
                close_below_count = 0
                sign_flip_count = 0
                prev_roll_sign = 0
            else:
                # Still in position: collect funding at epoch t
                per_epoch_gross.append((t, direction * diffs[t]))

    # Handle position still open at end
    if in_position:
        pos_end_idx = n - 1
        pos_epochs = n - pos_start_idx
        pos_gross = sum(direction * diffs[i] for i in range(pos_start_idx, n))
        positions.append({
            "start_ts": aligned[pos_start_idx][0],
            "end_ts": aligned[pos_end_idx][0],
            "direction": direction,
            "n_epochs": pos_epochs,
            "gross": pos_gross,
        })
        for i in range(pos_start_idx, n):
            per_epoch_gross.append((i, direction * diffs[i]))

    # === Aggregate statistics ===
    open_epochs = sum(p["n_epochs"] for p in positions)
    n_positions = len(positions)
    gross_values = [v for _, v in per_epoch_gross]
    total_gross = sum(gross_values)

    # Normal costs: 20bp RT per position
    total_costs_normal = COSTS_RT * n_positions
    total_costs_stress = STRESS_COSTS_RT * n_positions

    mean_gross = total_gross / open_epochs if open_epochs > 0 else 0
    mean_net = (total_gross - total_costs_normal) / open_epochs if open_epochs > 0 else 0
    mean_stress = (total_gross - total_costs_stress) / open_epochs if open_epochs > 0 else 0

    t_val = t_statistic(gross_values)
    ci90_lo, ci90_hi = bootstrap_ci90(gross_values)

    # Sign persistence per month
    sign_persist = sign_persistence_monthly(aligned, diffs, positions)

    # DSR (on gross per-epoch values)
    dsr = compute_dsr(gross_values, None)

    result = {
        "venue_a": venue_a_name,
        "venue_b": venue_b_name,
        "universe": UNIVERSE,
        "total_epochs": n,
        "total_open_epochs": open_epochs,
        "n_positions": n_positions,
        "total_gross": total_gross,
        "total_costs_normal": total_costs_normal,
        "total_costs_stress": total_costs_stress,
        "mean_gross_per_epoch": mean_gross,
        "mean_net_per_epoch": mean_net,
        "mean_stress_per_epoch": mean_stress,
        "t_stat": t_val,
        "ci90": {"lo": ci90_lo, "hi": ci90_hi},
        "dsr": dsr,
        "monthly_sign_persistence_pct": sign_persist,
        "positions": positions,
    }
    return result


def run_symbol(symbol, datadir, venue_a="bybit", venue_b="binance"):
    """Run E9 strategy for a single symbol across two venues."""
    file_a = os.path.join(datadir, f"{venue_a}_{symbol}_8h.json")
    file_b = os.path.join(datadir, f"{venue_b}_{symbol}_8h.json")
    if not os.path.exists(file_a):
        return {"symbol": symbol, "error": f"Missing {file_a}"}
    if not os.path.exists(file_b):
        return {"symbol": symbol, "error": f"Missing {file_b}"}

    series_a = load_series(file_a)
    series_b = load_series(file_b)
    aligned = align_series(series_a, series_b)

    result = run_strategy(aligned, venue_a_name=venue_a, venue_b_name=venue_b)
    result["symbol"] = symbol
    result["n_aligned_epochs"] = len(aligned)
    return result


def main():
    """Main entry point — run SMOKE across all symbols and venue pairs."""
    import argparse
    parser = argparse.ArgumentParser(description="E9 funding-spread cross-venue engine")
    parser.add_argument("--datadir", default=os.path.expanduser("~/hermes-scratch/e9/dati"))
    parser.add_argument("--venue-a", default="bybit")
    parser.add_argument("--venue-b", default="binance")
    parser.add_argument("--symbols", nargs="+", default=UNIVERSE)
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args()

    datadir = os.path.expanduser(args.datadir)
    all_results = {}
    all_gross_values = []

    for sym in args.symbols:
        print(f"\n=== {args.venue_a} <-> {args.venue_b} | {sym} ===", flush=True)
        res = run_symbol(sym, datadir, args.venue_a, args.venue_b)
        all_results[sym] = res

        if "error" in res:
            print(f"  ERROR: {res['error']}", flush=True)
            continue

        print(f"  epoche totali (allineate): {res['n_aligned_epochs']}", flush=True)
        print(f"  epoche aperte: {res['total_open_epochs']}", flush=True)
        print(f"  posizioni: {res['n_positions']}", flush=True)
        print(f"  media lorda/epoca: {res['mean_gross_per_epoch']:.8f}", flush=True)
        print(f"  media netto/epoca (20bp RT): {res['mean_net_per_epoch']:.8f}", flush=True)
        print(f"  media stress/epoca (42bp RT): {res['mean_stress_per_epoch']:.8f}", flush=True)
        print(f"  t-stat: {res['t_stat']:.4f}", flush=True)
        print(f"  CI90: [{res['ci90']['lo']:.8f}, {res['ci90']['hi']:.8f}]", flush=True)
        print(f"  DSR (N=3): {res['dsr']:.4f}", flush=True)
        print(f"  persistenza segno/mese: {res['monthly_sign_persistence_pct']}", flush=True)
        if res["n_positions"] > 0:
            for p in res["positions"]:
                print(f"    pos @ {p['start_ts']} → {p['end_ts']} | dir={p['direction']} | epoche={p['n_epochs']} | lordo={p['gross']:.8f}", flush=True)

    # Print summary table
    print("\n" + "=" * 100, flush=True)
    print(f"SMOKE: {args.venue_a} <-> {args.venue_b}", flush=True)
    print(f"{'Simbolo':<8} {'Epoche aperte':<15} {'Media netto/epoca':<20} {'t-stat':<10}", flush=True)
    print("-" * 100, flush=True)
    pos_symbols = 0
    for sym in args.symbols:
        res = all_results.get(sym, {})
        if "error" in res:
            print(f"{sym:<8} ERROR: {res['error']}", flush=True)
            continue
        open_ep = res["total_open_epochs"]
        mean_net = res["mean_net_per_epoch"]
        t_val = res["t_stat"]
        is_positive = mean_net > 0
        if is_positive:
            pos_symbols += 1
        print(f"{sym:<8} {open_ep:<15} {mean_net:<20.8f} {t_val:<10.4f} {'+' if is_positive else '−'}", flush=True)
    print("-" * 100, flush=True)
    print(f"Simboli con media positiva: {pos_symbols}/{len(args.symbols)}", flush=True)

    if args.json_out:
        with open(os.path.expanduser(args.json_out), "w") as f:
            json.dump(all_results, f, indent=2, default=str)
        print(f"\nResults written to: {args.json_out}", flush=True)

    return all_results


if __name__ == "__main__":
    main()
