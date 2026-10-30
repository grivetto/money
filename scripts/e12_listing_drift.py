#!/usr/bin/env python3
"""E12 — «Listing drift 24h long-only» engine (spec: coda_catena/E12_listing_drift.md).

Regole CONGELATE (dalla spec, zero gradi di liberta'):
- Evento: coppia spot OKX EEA annunciata in [2023-06-01, 2026-10-01); t0 = primo bar 1H.
- LONG a open(t0); FLAT al close del 24o bar 1H (il bar che inizia a t0+23h).
- Return per evento = close(t0+23h)/open(t0) - 1 - costi.
- Costi: base RT 0.30%; stress x2 = 0.60%.
- Filtri universo (sui primi 24 bar): 24 bar orari consecutivi da t0, nessun buco,
  nessuno zero (o/h/l/c > 0, volume > 0, bar piena); volume quote prime 24h >= 50.000.
- Finestre: TRAIN ann < 2025-06-01 <= OOS. Gate T1-T5 come da spec.
- Legge SOLO i dati congelati (freeze/); nessun fetch a tempo di misura.

Uso: python3 e12_listing_drift.py --freeze <dir> --json <out.json> --txt <out.txt>
"""
import argparse
import json
import math
import os
import sys

H = 3600000
COST_BASE = 0.0030          # RT base 0,30%
COST_STRESS = 0.0060        # stress x2
VOL_MIN = 50_000.0          # volume quote prime 24h
SPLIT_MS = 1748736000000    # 2025-06-01T00:00:00Z (finestra OOS da qui)
CUT_LO_MS = 1685577600000   # 2023-06-01T00:00:00Z (finestra universo)
CUT_HI_MS = 1790812800000   # 2026-10-01T00:00:00Z (fix 30/10: prima 1798675200000 = 2026-12-31, refuso; impatto nullo sul freeze E12, nessun annuncio oltre il cut)
T1_N_MIN = 60
T1_T_MIN = 2.7
T2_MEAN_MIN = 0.0
T3_T_MIN = 1.5
T4_T_MIN = 1.0


class DataError(Exception):
    pass


def _f(x):
    return float(x)


def check_and_compute(bars, t0):
    """Applica filtri sui primi 24 bar e calcola i return.

    bars: lista di bar grezzi [ts,o,h,l,c,vol,volCcy,volCcyQuote,confirm] (OKX)
          oppure [ts,o,h,l,c,vol,turnover] (Bybit).
    t0: primo bar atteso (ms). Ritorna dict con esito.
    """
    if not bars:
        return {'ok': False, 'reason': 'nessun bar'}
    if int(bars[0][0]) != t0:
        raise DataError(f'disallineamento primo bar: {bars[0][0]} != t0 {t0}')
    if len(bars) < 24:
        return {'ok': False, 'reason': f'solo {len(bars)} bar < 24'}
    w = bars[:24]
    for i, b in enumerate(w):
        if int(b[0]) != t0 + i * H:
            return {'ok': False, 'reason': f'buco/ordine non orario al bar {i}'}
    qv = 0.0
    for i, b in enumerate(w):
        o, h, l, c = _f(b[1]), _f(b[2]), _f(b[3]), _f(b[4])
        vol = _f(b[5])
        if min(o, h, l, c) <= 0 or vol <= 0:
            return {'ok': False, 'reason': f'zero al bar {i}'}
        if len(b) > 8 and str(b[8]) != '1':
            return {'ok': False, 'reason': f'bar non piena al bar {i}'}
        qv += _f(b[7]) if len(b) > 7 else _f(b[6])
    if qv < VOL_MIN:
        return {'ok': False, 'reason': f'volume 24h {qv:.0f} < {VOL_MIN:.0f}', 'qvol24': qv}
    o0 = _f(w[0][1])
    c23 = _f(w[23][4])
    return {'ok': True, 'reason': None, 'qvol24': qv,
            'ret_base': c23 / o0 - 1 - COST_BASE,
            'ret_stress': c23 / o0 - 1 - COST_STRESS,
            'entry_open': o0, 'exit_close': c23}


def stats(rets):
    n = len(rets)
    if n == 0:
        return {'n': 0, 'mean': None, 'sd': None, 't': None}
    m = sum(rets) / n
    if n > 1:
        sd = math.sqrt(sum((x - m) ** 2 for x in rets) / (n - 1))
        t = (m / (sd / math.sqrt(n))) if sd > 0 else None
    else:
        sd, t = None, None
    return {'n': n, 'mean': m, 'sd': sd, 't': t}


def split_half(events, key='t0'):
    ev = sorted(events, key=lambda e: e[key])
    k = len(ev) // 2
    return ev[:k], ev[k:]


def load_events(freeze_dir, venue):
    ev_path = os.path.join(freeze_dir, f'{venue}_events.jsonl')
    bar_path = os.path.join(freeze_dir, f'{venue}_bars.jsonl')
    if not (os.path.exists(ev_path) and os.path.exists(bar_path)):
        return None
    events = [json.loads(l) for l in open(ev_path)]
    bars = {}
    for l in open(bar_path):
        r = json.loads(l)
        key = r.get('instId') or r.get('symbol')
        if key in bars:
            raise DataError(f'duplicato strumento {key} in {bar_path}')
        bars[key] = r
    out = []
    for e in events:
        key = e.get('instId') or e.get('symbol') or e.get('sym')
        if key not in bars:
            raise DataError(f'manca bar per {key} in {bar_path}')
        b = bars[key]
        out.append((e, b))
    seen = set()
    for e, _ in out:
        key = e.get('instId') or e.get('symbol') or e.get('sym')
        if key in seen:
            raise DataError(f'strumento duplicato {key} in {ev_path}')
        seen.add(key)
    return out


def run_venue(freeze_dir, venue):
    loaded = load_events(freeze_dir, venue)
    if loaded is None:
        return None
    records, excluded = [], []
    for e, b in loaded:
        ann_ms = int(e['ann_ms'])
        t0 = int(b['first_ms'])
        if not (CUT_LO_MS <= ann_ms < CUT_HI_MS):
            raise DataError(f'annuncio fuori finestra {e}')
        res = check_and_compute(b['bars'], t0)
        band = 'TRAIN' if ann_ms < SPLIT_MS else 'OOS'
        row = {'key': e.get('instId') or e.get('symbol') or e.get('sym'), 'venue': venue, 'band': band,
               'ann_utc': e.get('ann_utc'), 'ann_ms': ann_ms, 't0_ms': t0,
               'pair': e.get('pair') or e.get('sym'), 'motivo': res['reason'],
               'qvol24': res.get('qvol24')}
        if res['ok']:
            row.update({'ret_base': res['ret_base'], 'ret_stress': res['ret_stress'],
                        'included': True})
            records.append(row)
        else:
            row['included'] = False
            excluded.append(row)
    tr = [r for r in records if r['band'] == 'TRAIN']
    oo = [r for r in records if r['band'] == 'OOS']
    s_tr = stats([r['ret_base'] for r in tr])
    s_oo = stats([r['ret_base'] for r in oo])
    s_oo_stress = stats([r['ret_stress'] for r in oo])
    h1, h2 = split_half(oo, key='t0_ms')
    return {'events': records, 'excluded': excluded,
            'train': s_tr, 'oos': s_oo, 'oos_stress': s_oo_stress,
            'oos_half1': stats([r['ret_base'] for r in h1]),
            'oos_half2': stats([r['ret_base'] for r in h2]),
            'n_events': len(records), 'n_excluded': len(excluded)}


def gate_t1(okx):
    s = okx['oos']
    if s['n'] < T1_N_MIN:
        return {'pass': False, 'reason': f"n OOS {s['n']} < {T1_N_MIN}", **s}
    ok = (s['mean'] is not None and s['mean'] > 0) and (s['t'] is not None and s['t'] >= T1_T_MIN)
    return {'pass': bool(ok), **s}


def gate_t2(okx):
    s = okx['oos_stress']
    ok = s['n'] > 0 and s['mean'] is not None and s['mean'] > T2_MEAN_MIN
    return {'pass': bool(ok), **s}


def gate_t3(okx):
    s = okx['train']
    ok = s['n'] > 0 and (s['mean'] is not None and s['mean'] > 0) and (s['t'] is not None and s['t'] >= T3_T_MIN)
    return {'pass': bool(ok), **s}


def gate_t4(bybit):
    if bybit is None:
        return {'pass': None, 'reason': 'dati Bybit assenti'}
    oo = [e for e in bybit['events'] if e['band'] == 'OOS']
    if len(oo) >= T1_N_MIN:
        s = stats([e['ret_base'] for e in oo])
        scope = 'OOS'
    else:
        s = stats([e['ret_base'] for e in bybit['events']])
        scope = 'intero periodo (n OOS < 60)'
    ok = s['n'] > 0 and (s['mean'] is not None and s['mean'] > 0) and (s['t'] is not None and s['t'] >= T4_T_MIN)
    return {'pass': bool(ok), 'scope': scope, **s}


def gate_t5(okx):
    a, b = okx['oos_half1'], okx['oos_half2']
    ok = (a['n'] > 0 and b['n'] > 0 and a['mean'] is not None and a['mean'] > 0
          and b['mean'] is not None and b['mean'] > 0)
    return {'pass': bool(ok), 'half1': a, 'half2': b}


def run_all(freeze_dir):
    okx = run_venue(freeze_dir, 'okx')
    bybit = run_venue(freeze_dir, 'bybit')
    if okx is None:
        raise DataError('dati OKX congelati assenti')
    t1, t2, t3, t4, t5 = gate_t1(okx), gate_t2(okx), gate_t3(okx), gate_t4(bybit), gate_t5(okx)
    gates = {'T1': t1, 'T2': t2, 'T3': t3, 'T4': t4, 'T5': t5}
    verd = {g: (v['pass'] if v['pass'] is not None else None) for g, v in gates.items()}
    promossa = all(verd[g] is True for g in ('T1', 'T2', 'T3', 'T4', 'T5'))
    return {'spec': {'cost_base_rt': COST_BASE, 'cost_stress_rt': COST_STRESS, 'vol_min_quote_24h': VOL_MIN,
                     'split_ms': SPLIT_MS, 'cut_lo_ms': CUT_LO_MS, 'cut_hi_ms': CUT_HI_MS,
                     't1_n_min': T1_N_MIN, 't1_t_min': T1_T_MIN, 't3_t_min': T3_T_MIN, 't4_t_min': T4_T_MIN},
            'okx': okx, 'bybit': bybit, 'gates': gates, 'verdict': {'promossa': promossa, 'per_gate': verd}}


def fmt_stats(s):
    if s['n'] == 0:
        return 'n=0'
    t = 'None' if s['t'] is None else f"{s['t']:.3f}"
    m = 'None' if s['mean'] is None else f"{s['mean'] * 100:+.3f}%"
    return f"n={s['n']} mean={m} t={t}"


def render_txt(res):
    L = []
    A = L.append
    A('E12 — listing drift 24h long-only (smoke da dati CONGELATI)')
    A(f"costi: base RT {res['spec']['cost_base_rt'] * 100:.2f}% | stress {res['spec']['cost_stress_rt'] * 100:.2f}% | "
      f"vol24 min {res['spec']['vol_min_quote_24h']:.0f}")
    for venue in ('okx', 'bybit'):
        v = res[venue]
        if v is None:
            A(f'[{venue}] dati assenti')
            continue
        A(f"[{venue}] inclusi={v['n_events']} esclusi={v['n_excluded']}")
        A(f"  TRAIN: {fmt_stats(v['train'])}")
        A(f"  OOS  : {fmt_stats(v['oos'])}")
        A(f"  OOS stress: {fmt_stats(v['oos_stress'])}")
        A(f"  OOS half1: {fmt_stats(v['oos_half1'])} | half2: {fmt_stats(v['oos_half2'])}")
        from collections import Counter
        exc = Counter((e['motivo'] or '').split(' ')[0] for e in v['excluded'])
        if v['excluded']:
            A(f"  esclusioni per motivo: {dict(exc)}")
    A('--- GATE ---')
    for g in ('T1', 'T2', 'T3', 'T4', 'T5'):
        x = res['gates'][g]
        extra = ''
        if g == 'T1' and 'reason' in x:
            extra = f" [{x['reason']}]"
        if g == 'T4' and x.get('scope'):
            extra = f" [{x['scope']}]"
        A(f"  {g}: pass={x['pass']}{extra} | {fmt_stats(x) if 'n' in x else ''}")
    A(f"VERDETTO: promossa={res['verdict']['promossa']} {res['verdict']['per_gate']}")
    return '\n'.join(L) + '\n'


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--freeze', required=True)
    ap.add_argument('--json', required=True)
    ap.add_argument('--txt', required=True)
    a = ap.parse_args(argv)
    res = run_all(a.freeze)
    with open(a.json, 'w') as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    txt = render_txt(res)
    with open(a.txt, 'w') as f:
        f.write(txt)
    print(txt)
    return 0


if __name__ == '__main__':
    sys.exit(main())
