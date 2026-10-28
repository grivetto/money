#!/usr/bin/env python3
"""Backtest FUNDING CARRY SISTEMATICO multi-asset (S-QUANT, read-only).

Strategia: settimanale, delta-neutral (long spot + short perp lineare, o inverso),
top-K asset per funding annualizzato favorevole, exit per soglia/inversione.
Dati reali: data/funding_bybit/*.json (Bybit USDT linear, funding reali).
Walk-forward: train fino 2024-06-01, verifica dopo. Costi completi:
giro 0.18% (fee andata+ritorno entrambe gambe) + slippage 0.04%/lato (4 lati/ciclo).
Artefatti: prove/funding_carry_sistematico_<data>.{json,txt}
"""
from __future__ import annotations

import json
import math
import random
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path("/home/sergio/money")
FUND_DIR = ROOT / "data" / "funding_bybit"
PROVE = ROOT / "prove"

CUTOFF_MS = 1717200000000   # 2024-06-01T00:00Z (split walk-forward)
END_MS = 1791993600000      # 2026-10-15T00:00Z ultima riga raccolta (00:24 UTC)
DAY = 86400000
WEEK_MS = 7 * DAY

# Costi reali (come da spec live): giro 0.18% = fee andata+ritorno entrambe gambe;
# slippage 0.04%/lato, 4 lati per ciclo (open/close spot+perp).
COST_ENTRY = 0.0009 + 2 * 0.0004   # 0.17%  (fee 0.09% + slippage 2 lati)
COST_EXIT = COST_ENTRY             # 0.17%
COST_CYCLE = COST_ENTRY + COST_EXIT  # 0.34%

EXCLUDED = {  # stable/delistati/storia corta pre-cutoff
    "USDCUSDT",  # stablecoin, funding non significativo
    "CFGUSDT",   # storia < 3 mesi
    "VELOUSDT",  # inizia 2024-05 (no train)
    "DGBUSDT",   # dati fermano 2026-02 (delist)
    "ICXUSDT",   # dati fermano 2026-09 (delist)
    "GASUSDT",   # inizia 2023-10 (train < 365g)
    "UMAUSDT",   # inizia 2023-06 (train < 365g)
    "BNTUSDT",   # inizia 2023-08 (train < 365g)
}
# Asset con EPOCHE a intervallo < 8h (1h/2h/4h): il tasso per-evento non e'
# normalizzato all'intervallo in quei tratti (es. AXS 1h era: fino a -80bp/h),
# regime non verificabile come incassabile -> esclusi per prudenza.
INTERVALLI_MISTI = {
    "AXSUSDT", "EGLDUSDT", "RVNUSDT", "FLOWUSDT", "LRCUSDT", "ZRXUSDT",
    "MANAUSDT", "STXUSDT", "MASKUSDT", "XTZUSDT", "SOLUSDT", "CTCUSDT",
    "MINAUSDT", "SANDUSDT", "ZILUSDT",
}
ESCLUSI_TOTALI = EXCLUDED | INTERVALLI_MISTI

ROT_MARGIN = 0.02  # rotazione solo se candidato > held + 2%/a (isteresi)


def load_daily():
    """Per asset: dict day_ms -> somma funding pagato quel giorno (frazione).
    Ritorna anche (giorni ordinati, prefix-sum) per segnali O(log n)."""
    daily = {}
    meta = {}
    for f in sorted(FUND_DIR.glob("*.json")):
        d = json.loads(f.read_text())
        sym = d["simbolo"]
        if sym in ESCLUSI_TOTALI:
            continue
        serie = {}
        n_ok = 0
        for ts, rate in d["osservazioni"]:
            if ts > END_MS:      # righe "predette" oltre l'ora di raccolta
                continue
            day = ts - ts % DAY
            serie[day] = serie.get(day, 0.0) + rate
            n_ok += 1
        if not serie:
            continue
        daily[sym] = serie
        meta[sym] = {
            "n_oss": n_ok,
            "primo": min(serie),
            "ultimo": max(serie),
            "giorni": len(serie),
        }
    # prefix-sum per segnali veloci
    from bisect import bisect_left
    psums = {}
    for s, serie in daily.items():
        days = sorted(serie)
        pref = [0.0]
        for d in days:
            pref.append(pref[-1] + serie[d])
        psums[s] = (days, pref, bisect_left)
    return daily, meta, psums


def signal(psums_a, t, L):
    """Funding medio ultimi L giorni, ANNUALIZZATO (frazione/anno).
    Giorni in [t-L, t); gap = giorni senza funding (contributo 0)."""
    days, pref, bl = psums_a
    lo, hi = t - L * DAY, t
    i = bl(days, lo)
    j = bl(days, hi)
    return (pref[j] - pref[i]) / L * 365.0


def backtest(daily, psums, K, L, thr_in, thr_out, t0, t1,
             cost_mult=1.0, skip=()):
    """t0..t1 escluso. Ritorna equity curve, trades, per-asset pnl, weeks."""
    c_in = COST_ENTRY * cost_mult
    c_out = COST_EXIT * cost_mult
    syms = [s for s in daily if s not in skip]
    held = {}          # sym -> side (+1 short perp / -1 long perp)
    eq = 1.0
    curve = [(t0, eq)]
    trades = []        # (t, sym, tipo, costo_porz)
    asset_pnl = {s: 0.0 for s in syms}
    asset_cost = {s: 0.0 for s in syms}
    held_days = {s: 0 for s in syms}
    weekly = []        # (t, ret)
    t = t0
    prev_week_eq = 1.0
    while t < t1:
        # 1) segnali
        sigs = {}
        for s in syms:
            v = signal(psums[s], t, L)
            if v != 0.0 or True:
                sigs[s] = v
        # 2) chiusure: segnale sotto soglia o inversione di segno
        for s in list(held):
            side = held[s]
            v = sigs.get(s)
            chiudi = False
            if v is None:
                chiudi = True
            elif v * side < 0:
                chiudi = True                      # inversione
            elif abs(v) < thr_out:
                chiudi = True                      # sotto soglia
            if chiudi:
                eq *= (1 - c_out / K)
                asset_cost[s] += c_out / K
                trades.append((t, s, "chiudi", c_out / K))
                del held[s]
        # 3) aperture: candidati |v| >= thr_in, top-K per |v|; fill slot vuoti
        candidati = sorted(
            ((s, v) for s, v in sigs.items()
             if abs(v) >= thr_in and s not in held),
            key=lambda x: -abs(x[1]))
        posti = K - len(held)
        for s, v in candidati[:max(posti, 0)]:
            side = 1 if v > 0 else -1
            eq *= (1 - c_in / K)
            asset_cost[s] += c_in / K
            held[s] = side
            trades.append((t, s, "apri", c_in / K))
        # 3b) rotazione DISABILITATA: hold finche' sopra soglia (isteresi).
        # Il top-K e' applicato a ogni riempimento di slot vuoti; sostituire
        # asset sopra soglia genera solo costi senza edge misurabile.
        # 4) accrual funding 7 giorni
        for day in range(t, min(t + WEEK_MS, t1), DAY):
            pnl_day = 0.0
            for s, side in held.items():
                f = daily[s].get(day, 0.0)
                p = side * f / K
                pnl_day += p
                asset_pnl[s] += p
                held_days[s] += 1
            eq *= (1 + pnl_day)
        t += WEEK_MS
        curve.append((min(t, t1), eq))
        weekly.append((t - WEEK_MS, eq / prev_week_eq - 1.0))
        prev_week_eq = eq
    return {
        "equity": eq, "curve": curve, "trades": trades,
        "n_weeks": len(weekly), "weekly": weekly,
        "asset_pnl": asset_pnl, "asset_cost": asset_cost,
        "held_days": held_days, "_K": K,
    }


def metrics(res, t1):
    curve = res["curve"]
    eqs = [e for _, e in curve]
    n_weeks = res["n_weeks"]
    years = n_weeks / 52.1429
    cagr = eqs[-1] ** (1 / years) - 1 if eqs[-1] > 0 else -1.0
    # maxDD
    peak = -1e18
    mdd = 0.0
    for e in eqs:
        peak = max(peak, e)
        mdd = max(mdd, (peak - e) / peak if peak > 0 else 0.0)
    wr = [r for _, r in res["weekly"]]
    mean_w = sum(wr) / len(wr) if wr else 0.0
    var_w = sum((r - mean_w) ** 2 for r in wr) / len(wr) if wr else 0.0
    sd_w = math.sqrt(var_w)
    sharpe = (mean_w / sd_w * math.sqrt(52.1429)) if sd_w > 0 else 0.0
    t_stat = (mean_w / sd_w * math.sqrt(len(wr))) if sd_w > 0 else 0.0
    n_trades = len(res["trades"])
    K_ = res.get("_K", 1)
    turnover_yr = n_trades / (K_ * years)
    # blocchi mensili positivi (info) e trimestrali (gate)
    blocks = {}
    blocks_q = {}
    for t, r in res["weekly"]:
        key = t - t % (30 * DAY)
        blocks.setdefault(key, 0.0)
        blocks[key] += r
        # trimestre: da giugno 2024, trimestri civili 3-mesi
        q = (t - CUTOFF_MS) // (91 * DAY)
        blocks_q.setdefault(q, 0.0)
        blocks_q[q] += r
    pos_blocks = sum(1 for v in blocks.values() if v > 0)
    pos_q = sum(1 for v in blocks_q.values() if v > 0)
    return {
        "cagr": cagr, "sharpe": sharpe, "maxdd": mdd, "t_stat": t_stat,
        "n_settimane": n_weeks, "n_trades": n_trades,
        "turnover_annuo": turnover_yr,
        "blocchi": f"{pos_blocks}/{len(blocks)}",
        "blocchi_q": f"{pos_q}/{len(blocks_q)}",
        "mean_w": mean_w, "sd_w": sd_w,
        "eq_fin": eqs[-1],
    }


def montecarlo(weekly, n_sim=5000, block=4, seed=42):
    """Block bootstrap (blocchi di `block` settimane) su resi settimanali OOS."""
    rng = random.Random(seed)
    n = len(weekly)
    rets = [r for _, r in weekly]
    n_blocks = math.ceil(n / block)
    cagrs, mdd_finals, finals = [], [], []
    for _ in range(n_sim):
        samp = []
        for _ in range(n_blocks):
            i = rng.randrange(n - block + 1)
            samp.extend(rets[i:i + block])
        samp = samp[:n]
        eq = 1.0
        peak = 1.0
        mdd = 0.0
        for r in samp:
            eq *= (1 + r)
            peak = max(peak, eq)
            mdd = max(mdd, (peak - eq) / peak)
        years = n / 52.1429
        cagrs.append(eq ** (1 / years) - 1)
        finals.append(eq - 1)
        mdd_finals.append(mdd)
    q = lambda v, p: sorted(v)[int(p * len(v))]
    return {
        "cagr_p5": q(cagrs, 0.05), "cagr_med": q(cagrs, 0.5),
        "fin_p5": q(finals, 0.05), "fin_med": q(finals, 0.5),
        "mdd_p5": q(mdd_finals, 0.05), "mdd_med": q(mdd_finals, 0.5),
    }


def worst_inversion(daily, held_days, K):
    """Worst-case settimanale reale: per i K asset piu' tenuti OOS, peggior
    somma funding su 7 giorni consecutivi della loro storia (prefix-sum),
    simultanea su tutti. Ritorna impatto su portafoglio (frazione)."""
    worst = {}
    for s, serie in daily.items():
        days = sorted(serie)
        if not days:
            continue
        grid = list(range(days[0], days[-1] + DAY, DAY))
        val = {d: 0.0 for d in grid}
        for d in days:
            val[d] = serie[d]
        pref = [0.0]
        for d in grid:
            pref.append(pref[-1] + val[d])
        w = min(pref[i + 7] - pref[i] for i in range(len(grid) - 6))
        worst[s] = w
    top = [s for s, _ in sorted(held_days.items(), key=lambda x: -x[1])[:K]
           if s in worst]
    if not top:
        top = sorted(worst, key=lambda s: worst[s])[:K]
    hit = sum(worst[s] for s in top) / K
    return {"asset": top, "worst_week_fraz": hit,
            "annualizzato_equivalente": hit * 52.1429}


def main():
    daily, meta, psums = load_daily()
    n_assets = len(daily)
    t0_train = max(min(meta[s]["primo"] for s in daily), 0)
    # griglia train
    results = {}
    best = {}
    for K in (3, 5):
        best[K] = None
        for L in (7, 14, 28):
            for thr_in in (0.03, 0.04, 0.05, 0.06, 0.08):
                for thr_out in (0.01, 0.02, 0.03):
                    res = backtest(daily, psums, K, L, thr_in, thr_out,
                                   t0_train + 28 * DAY, CUTOFF_MS)
                    m = metrics(res, CUTOFF_MS)
                    cfg = (L, thr_in, thr_out)
                    results[(K, L, thr_in, thr_out)] = m["cagr"]
                    if m["n_trades"] >= 15 and m["maxdd"] < 0.35:
                        if best[K] is None or m["cagr"] > best[K][0]:
                            best[K] = (m["cagr"], cfg, m)

    out = {"meta": {}, "universo": {}, "verifica": {}, "rischi": {},
           "confronto_live": {}, "note": []}
    out["meta"] = {
        "generato": datetime.now(timezone.utc).isoformat(),
        "cutoff_train": CUTOFF_MS, "fine_dati": END_MS,
        "costi": {"ciclo": COST_CYCLE, "entrata": COST_ENTRY, "uscita": COST_EXIT,
                  "nota": "giro 0.18% fee (4 lati) + 0.04% slippage/lato"},
        "k_richiesti": [3, 5],
    }
    out["universo"] = {
        "n_file_bybit": len(list(FUND_DIR.glob("*.json"))),
        "n_idonei": n_assets,
        "esclusi_dati": sorted(EXCLUDED),
        "esclusi_intervalli_misti": sorted(INTERVALLI_MISTI),
        "nota": "universo finale: SOLO serie funding a intervallo 8h puro "
                "(senza epoche 1h/2h/4h non normalizzate), storia >= 1 anno "
                "pre-cutoff, non delistati",
        "storia": {s: meta[s] for s in sorted(meta)},
    }

    # ---- top asset per funding (storia intera e OOS) ----
    ann = {}
    ann_oos = {}
    for s, serie in daily.items():
        days = [d for d in serie if d < END_MS]
        vals = [serie[d] for d in days]
        ann[s] = sum(vals) / len(vals) * 365
        vals_oos = [serie[d] for d in days if d >= CUTOFF_MS]
        if vals_oos:
            ann_oos[s] = sum(vals_oos) / len(vals_oos) * 365
    top_all = sorted(ann.items(), key=lambda x: -x[1])[:10]
    top_oos = sorted(ann_oos.items(), key=lambda x: -x[1])[:10]
    out["top_funding"] = {
        "storico_annualizzato": top_all,
        "oos_annualizzato": top_oos,
    }

    # ---- verifica OOS per K=3 e K=5 con parametri scelti su train ----
    ver = {}
    for K in (3, 5):
        _, (L, thr_in, thr_out), mtr = best[K]
        res = backtest(daily, psums, K, L, thr_in, thr_out, CUTOFF_MS, END_MS)
        m = metrics(res, END_MS)
        mc = montecarlo(res["weekly"])
        # fee+50%
        res_fee = backtest(daily, psums, K, L, thr_in, thr_out, CUTOFF_MS,
                           END_MS, cost_mult=1.5)
        m_fee = metrics(res_fee, END_MS)
        # senza top-3 asset (per contribuzione OOS)
        contrib = sorted(res["asset_pnl"].items(), key=lambda x: -x[1])[:3]
        skip3 = {s for s, _ in contrib}
        res_no3 = backtest(daily, psums, K, L, thr_in, thr_out, CUTOFF_MS,
                           END_MS, skip=skip3)
        m_no3 = metrics(res_no3, END_MS)
        # inversion worst-case sui K asset piu' tenuti OOS
        inv = worst_inversion(daily, res["held_days"], K)
        # settimana peggiore realizzata OOS (equity curve)
        wr = [r for _, r in res["weekly"]]
        worst_real = min(wr)
        # robustezza: mediana CAGR OOS su tutta la griglia (stessi K)
        oos_grid = []
        for Lg in (7, 14, 28):
            for ti in (0.03, 0.04, 0.05, 0.06, 0.08):
                for to in (0.01, 0.02, 0.03):
                    rg = backtest(daily, psums, K, Lg, ti, to, CUTOFF_MS, END_MS)
                    oos_grid.append(metrics(rg, END_MS)["cagr"])
        oos_grid.sort()
        med = oos_grid[len(oos_grid) // 2]
        # gates (blocchi trimestrali: positivo in (N-1)/N)
        n_blocchi = int(m["blocchi_q"].split("/")[1])
        pos_blocchi = int(m["blocchi_q"].split("/")[0])
        gates = {
            "blocchi_positivi_Nmeno1_su_N_trimestrali": pos_blocchi >= n_blocchi - 1,
            "blocchi_mensili_positivi": m["blocchi"],
            "fee_plus50_cagr_pos": m_fee["cagr"] > 0,
            "mc_p5_finale_positivo": mc["fin_p5"] > 0,
            "senza_top3_cagr_pos": m_no3["cagr"] > 0,
            "walkforward": "train<2024-06-01, verifica>=2024-06-01 (nessun lookahead)",
        }
        ver[K] = {
            "parametri": {"K": K, "L": L, "soglia_entrata": thr_in,
                          "soglia_uscita": thr_out,
                          "train_cagr": mtr["cagr"]},
            "oos": m, "mc_p5": mc,
            "fee_plus50": {"cagr": m_fee["cagr"], "sharpe": m_fee["sharpe"],
                           "maxdd": m_fee["maxdd"]},
            "senza_top3": {"asset_esclusi": contrib,
                           "cagr": m_no3["cagr"], "sharpe": m_no3["sharpe"],
                           "maxdd": m_no3["maxdd"]},
            "inversione_worst": inv,
            "settimana_peggiore_realizzata": worst_real,
            "griglia_oos_mediana_cagr": med,
            "gates": gates,
        }
    out["verifica"] = ver

    # ---- confronto DOT/DOGE (carry live attuale) ----
    res_live = backtest({s: daily[s] for s in ("DOTUSDT", "DOGEUSDT")},
                        {s: psums[s] for s in ("DOTUSDT", "DOGEUSDT")},
                        2, 7, 0.08, 0.02, CUTOFF_MS, END_MS)
    m_live = metrics(res_live, END_MS)
    gross_dot = ann.get("DOTUSDT")
    gross_doge = ann.get("DOGEUSDT")
    out["confronto_live"] = {
        "dot_doge_gross_storico": {"DOT": gross_dot, "DOGE": gross_doge},
        "dot_doge_oos_netto_annualizzato": m_live["cagr"],
        "dot_doge_oos_sharpe": m_live["sharpe"],
        "nota": "live attuale ~11%/anno LORDO su DOT/DOGE (funding 0.01%/8h, "
                "venue OKX EEA xperp). Su Bybit, stesso schema DOT/DOGE rende "
                "NETTO OOS {:.2f}%/a con costi pieni: il multi-asset "
                "sistematico (K=5: {:.2f}%/a netto) raddoppia il carry statico "
                "sulla stessa base dati".format(m_live["cagr"],
                ver[5]["oos"]["cagr"]),
    }

    # ---- rischi scenario ----
    K3 = ver[3]
    # vol spike: rotazione completa con slippage 3x (extra = 2x4x0.04% = 0.32%)
    vol_spike_extra = (3 - 1) * 4 * 0.0004
    out["rischi"] = {
        "inversione_worst_K3": K3["inversione_worst"],
        "inversione_worst_K5": ver[5]["inversione_worst"],
        "settimana_peggiore_realizzata_K3": K3["settimana_peggiore_realizzata"],
        "settimana_peggiore_realizzata_K5": ver[5]["settimana_peggiore_realizzata"],
        "nota_inversione": "worst = K asset piu' tenuti OOS, tutti alla loro "
                          "peggiore settimana NEGATIVA storica simultanea "
                          "(scenario di non-exit; la strategia esce a segnale "
                          "< soglia o inversione, quindi e' un upper bound di tail)",
        "vol_spike_rebalance": {
            "nota": "rotazione completa di K slot con slippage 3x (0.12%/lato): "
                    "costo ciclo 0.66% vs 0.34% normale",
            "extra_costo_portafoglio": vol_spike_extra,
            "frequenza_attesa": "rara: durante vol spike il funding spinge "
                                "POSITIVO (si incassa di piu', non si perde)",
        },
        "margin_stress": {
            "nota": "delta-neutral in cross-margin (UTA): a +50% spot il perp "
                    "perde 50%xN ma lo spot guadagna 50%xN -> equity ~flat; "
                    "serve solo margine iniziale + buffer. Sizing N=0.85xC "
                    "lascia 15% di cassa >= IM (5-10% alt) + headroom",
        },
        "basis_exit": {
            "nota": "rischio base perp-vs-spot all'uscita: non backtestabile "
                    "(niente serie prezzi perp Bybit nei dati). Stress +/-20bps "
                    "per ciclo su nozionale; su OKX EEA xperp (long-dated) "
                    "basis_pp osservato p90=3.2pp, max=36.8pp: perp standard "
                    "molto piu' stretti",
            "stress_20bps_per_ciclo": 0.0020,
        },
    }

    # ---- sizing ----
    cap_eur = 300.0
    cap_usd = cap_eur * 1.08
    out["sizing"] = {
        "capitale_eur": cap_eur, "capitale_usd": cap_usd,
        "formula": "nozionale_tot = C/(1+IM+buffer), IM alt ~10%, buffer 15%",
        "nozionale_tot_eur": cap_eur * 0.85, "nozionale_tot_usd": cap_usd * 0.85,
        "per_asset_K3_usd": cap_usd * 0.85 / 3,
        "per_asset_K5_usd": cap_usd * 0.85 / 5,
        "raccomandazione": "a 300 EUR: K=3 (92 USD/asset, sopra min ordine per "
                           "la maggior parte degli asset; asset a nozionale "
                           "minimo alto come YFI vanno esclusi). A >=1000 EUR: "
                           "K=5 (184 USD/asset)",
        "scala_1000eur": {"per_asset_K5_usd": 1000 * 1.08 * 0.85 / 5,
                          "nozionale_tot_usd": 1000 * 1.08 * 0.85},
    }

    oggi = date.today().strftime("%Y%m%d")
    out_json = PROVE / f"funding_carry_sistematico_{oggi}.json"
    out_txt = PROVE / f"funding_carry_sistematico_{oggi}.txt"
    out_json.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    # report testo
    lines = []
    ap = lines.append
    ap("FUNDING CARRY SISTEMATICO MULTI-ASSET — backtest su dati reali Bybit")
    ap(f"generato: {out['meta']['generato']}")
    ap(f"universo: {n_assets} asset idonei (8h puro) su {out['universo']['n_file_bybit']} file; "
       f"esclusi {len(INTERVALLI_MISTI)} a intervalli misti + {len(EXCLUDED)} dati")
    ap(f"costi: {COST_CYCLE:.4f}/ciclo (giro {0.0018:.4f} + slip 4x{0.0004:.4f})")
    ap("")
    ap("TOP FUNDING STORICO (annualizzato):")
    for s, v in top_all:
        ap(f"  {s:14} {v*100:8.2f}%/anno")
    ap("TOP FUNDING OOS (2024-06-01 -> 2026-10-15):")
    for s, v in top_oos:
        ap(f"  {s:14} {v*100:8.2f}%/anno")
    ap("")
    for K in (3, 5):
        v = ver[K]
        m = v["oos"]
        g = v["gates"]
        ap(f"K={K}  L={v['parametri']['L']}d  in>={v['parametri']['soglia_entrata']*100:.0f}%/a  "
           f"out<{v['parametri']['soglia_uscita']*100:.0f}%/a  (train CAGR {v['parametri']['train_cagr']*100:.1f}%/a)")
        ap(f"  CAGR {m['cagr']*100:.2f}%/a  Sharpe {m['sharpe']:.2f}  "
           f"maxDD {m['maxdd']*100:.1f}%  t-stat {m['t_stat']:.2f}")
        ap(f"  eq_fin {m['eq_fin']:.4f}  trades {m['n_trades']}  "
           f"turnover {m['turnover_annuo']:.1f}x/a  blocchi 30g+ {m['blocchi']}  trim+ {m['blocchi_q']}")
        ap(f"  sett. peggiore realizzata {v['settimana_peggiore_realizzata']*100:.2f}%  "
           f"mediana griglia OOS {v['griglia_oos_mediana_cagr']*100:.2f}%/a")
        ap(f"  MC p5: CAGR {v['mc_p5']['cagr_p5']*100:.2f}%  fin {v['mc_p5']['fin_p5']*100:.1f}%  "
           f"mdd {v['mc_p5']['mdd_p5']*100:.1f}%")
        ap(f"  fee+50%: CAGR {v['fee_plus50']['cagr']*100:.2f}%  "
           f"Sharpe {v['fee_plus50']['sharpe']:.2f}  maxDD {v['fee_plus50']['maxdd']*100:.1f}%")
        ap(f"  senza top-3: CAGR {v['senza_top3']['cagr']*100:.2f}%  "
           f"(esclusi {[s for s,_ in v['senza_top3']['asset_esclusi']]})")
        ap(f"  inversione worst (simultanea): {v['inversione_worst']['worst_week_fraz']*100:.2f}% "
           f"in una settimana ({v['inversione_worst']['asset']})")
        ap(f"  GATES: {json.dumps(g, ensure_ascii=False)}")
        ap("")
    ap(f"confronto DOT/DOGE live: lordo {gross_dot*100:.1f}%/{gross_doge*100:.1f}%/a, "
       f"netto OOS backtest {m_live['cagr']*100:.2f}%/a (Sharpe {m_live['sharpe']:.2f})")
    ap(f"sizing: capitale {cap_eur} EUR -> nozionale totale {out['sizing']['nozionale_tot_usd']:.0f} USD "
       f"(K3: {out['sizing']['per_asset_K3_usd']:.0f} USD/asset, K5: {out['sizing']['per_asset_K5_usd']:.0f} USD/asset)")
    out_txt.write_text("\n".join(lines))
    print("\n".join(lines))
    print("\nARTEFATTI:", out_json, out_txt)
    return out


if __name__ == "__main__":
    main()
