#!/usr/bin/env python3
"""E13 — «Listing drift 24h long-only (OKX, universo globale)» engine.

Spec: coda_catena/E13_listing_drift_universo.md (regola IDENTICA a E12; cambia l'universo:
da annunci EEA a listTime globale). Zero gradi di liberta'.

- Evento: strumento spot OKX con listTime in [2023-06-01, 2026-10-01);
  t0 = primo bar 1H (registrato nel freeze). Bybit: proxy primo bar (v. freeze README).
- LONG a open(t0); FLAT al close del 24o bar 1H (quello che inizia a t0+23h).
- Return per evento = close(t0+23h)/open(t0) - 1 - costi. Base RT 0.30%; stress x2 = 0.60%.
- Filtri sui primi 24 bar (identici a E12): 24 bar orari consecutivi, nessun buco,
  nessuno zero (o/h/l/c > 0, vol > 0, bar piena); volume quote prime 24h >= 50.000.
- Finestre: TRAIN lt < 2025-06-01 <= OOS. Gate T1-T5 come spec E13.
- Output: per-evento, esclusioni con motivo, per-finestra, per-trimestre, sensibilita'
  (L2 collapse multibook, L3 lettura larga). Legge SOLO dati congelati (freeze/).

NOTA (anomalia segnalata, non replicata): in e12_listing_drift.py la costante
CUT_HI_MS=1798675200000 era commentata '2026-10-01' ma vale 2026-12-31 (ms corretto per
2026-10-01 = 1790812800000). Qui il valore e' CORRETTO. Impatto su E12: nullo (nessun
annuncio oltre il 2026-10 era nel freeze), ma il file canonico E12 va corretto.

Uso: python3 e13_listing_drift.py --freeze <dir> --json <out.json> --txt <out.txt>
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
SPLIT_MS = 1748736000000    # 2025-06-01T00:00:00Z (inizio OOS)
CUT_LO_MS = 1685577600000   # 2023-06-01T00:00:00Z
CUT_HI_MS = 1790812800000   # 2026-10-01T00:00:00Z (corretto; E12 aveva 1798675200000)
T1_N_MIN = 100              # E13: n OOS >= 100
T1_T_MIN = 2.7
T2_MEAN_MIN = 0.0
T3_T_MIN = 1.5
T4_T_MIN = 1.0
T4_N_SCOPE = 100            # T4: OOS se n OOS >= 100, altrimenti intero periodo


class DataError(Exception):
    pass


def _f(x):
    return float(x)


def check_and_compute(bars, t0):
    """Applica filtri sui primi 24 bar e calcola i return (identico a E12).

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


def check_and_compute_larga(bars, t0):
    """L3 — lettura larga: come E12 'lettura B' (buco/ordine e prezzi<=0 esclusi;
    volume zero ammesso). Retrocompatibile con la sensibilita' L3 della spec."""
    if not bars or len(bars) < 24:
        return {'ok': False, 'reason': 'solo <24 bar'}
    w = bars[:24]
    for i, b in enumerate(w):
        if int(b[0]) != t0 + i * H:
            return {'ok': False, 'reason': f'buco al bar {i}'}
        o, h, l, c = _f(b[1]), _f(b[2]), _f(b[3]), _f(b[4])
        if min(o, h, l, c) <= 0:
            return {'ok': False, 'reason': f'prezzo zero al bar {i}'}
        if len(b) > 8 and str(b[8]) != '1':
            return {'ok': False, 'reason': f'bar non piena al bar {i}'}
    qv = sum(_f(b[7]) if len(b) > 7 else _f(b[6]) for b in w)
    if qv < VOL_MIN:
        return {'ok': False, 'reason': f'volume {qv:.0f} < {VOL_MIN:.0f}'}
    o0, c23 = _f(w[0][1]), _f(w[23][4])
    return {'ok': True, 'reason': None, 'qvol24': qv,
            'ret_base': c23 / o0 - 1 - COST_BASE,
            'ret_stress': c23 / o0 - 1 - COST_STRESS}


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


def split_half(events, key='t0_ms'):
    ev = sorted(events, key=lambda e: e[key])
    k = len(ev) // 2
    return ev[:k], ev[k:]


def trimestre(ms):
    import time as _t
    tt = _t.gmtime(int(ms) / 1000)
    return f'{tt.tm_year}Q{(tt.tm_mon - 1) // 3 + 1}'


def lt_of(e):
    return e.get('listTime_ms') or e.get('listTime_ms_proxy') or e.get('lt_ms')


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


def run_venue(freeze_dir, venue, variant='stretta'):
    loaded = load_events(freeze_dir, venue)
    if loaded is None:
        return None
    compute = check_and_compute if variant == 'stretta' else check_and_compute_larga
    records, excluded = [], []
    for e, b in loaded:
        lt = lt_of(e)
        if lt is None:
            raise DataError(f'listTime assente per {e}')
        lt = int(lt)
        t0 = int(b['first_ms'])
        if not (CUT_LO_MS <= lt < CUT_HI_MS):
            raise DataError(f'listTime fuori finestra {e}')
        res = compute(b['bars'], t0)
        band = 'TRAIN' if lt < SPLIT_MS else 'OOS'
        row = {'key': e.get('instId') or e.get('symbol') or e.get('sym'), 'venue': venue,
               'band': band, 'lt_ms': lt, 'lt_utc': e.get('listTime_utc') or e.get('first_utc'),
               't0_ms': t0, 'base': e.get('base'), 'trimestre': trimestre(lt),
               'pair': e.get('pair') or e.get('sym') or e.get('symbol'),
               'motivo': res['reason'], 'qvol24': res.get('qvol24')}
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


def per_trimestre(venue_res):
    out = {}
    for r in venue_res['events']:
        t = r['trimestre']
        out.setdefault(t, []).append(r['ret_base'])
    return {t: stats(v) for t, v in sorted(out.items())}


def collapse_token(venue_res):
    """L2 — 1 evento per token (base), tenendo la quote col t0 piu' antico."""
    best = {}
    for r in venue_res['events']:
        base = r.get('base') or r['key']
        cur = best.get(base)
        if cur is None or r['t0_ms'] < cur['t0_ms']:
            best[base] = r
    ev = list(best.values())
    tr = [r for r in ev if r['band'] == 'TRAIN']
    oo = [r for r in ev if r['band'] == 'OOS']
    s_oo = stats([r['ret_base'] for r in oo])
    return {'n_token': len(ev), 'n_events_collapsed': len(ev), 'train': stats([r['ret_base'] for r in tr]),
            'oos': s_oo,
            't1_like': bool(s_oo['n'] >= T1_N_MIN and s_oo['mean'] is not None and s_oo['mean'] > 0
                            and s_oo['t'] is not None and s_oo['t'] >= T1_T_MIN)}


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
    if len(oo) >= T4_N_SCOPE:
        s = stats([e['ret_base'] for e in oo])
        scope = 'OOS'
    else:
        s = stats([e['ret_base'] for e in bybit['events']])
        scope = f'intero periodo (n OOS {len(oo)} < {T4_N_SCOPE})'
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
    okx_larga = run_venue(freeze_dir, 'okx', variant='larga')
    t1, t2, t3, t4, t5 = gate_t1(okx), gate_t2(okx), gate_t3(okx), gate_t4(bybit), gate_t5(okx)
    gates = {'T1': t1, 'T2': t2, 'T3': t3, 'T4': t4, 'T5': t5}
    verd = {g: (v['pass'] if v['pass'] is not None else None) for g, v in gates.items()}
    promossa = all(verd[g] is True for g in ('T1', 'T2', 'T3', 'T4', 'T5'))
    return {'spec': {'cost_base_rt': COST_BASE, 'cost_stress_rt': COST_STRESS,
                     'vol_min_quote_24h': VOL_MIN, 'split_ms': SPLIT_MS,
                     'cut_lo_ms': CUT_LO_MS, 'cut_hi_ms': CUT_HI_MS,
                     't1_n_min': T1_N_MIN, 't1_t_min': T1_T_MIN,
                     't3_t_min': T3_T_MIN, 't4_t_min': T4_T_MIN, 't4_n_scope': T4_N_SCOPE},
            'okx': okx, 'bybit': bybit,
            'okx_trimestre': per_trimestre(okx),
            'okx_collapse_token': collapse_token(okx),
            'okx_larga': {'n_events': okx_larga['n_events'], 'n_excluded': okx_larga['n_excluded'],
                          'train': okx_larga['train'], 'oos': okx_larga['oos']},
            'gates': gates, 'verdict': {'promossa': promossa, 'per_gate': verd}}


def fmt_stats(s):
    if s['n'] == 0:
        return 'n=0'
    t = 'None' if s['t'] is None else f"{s['t']:.3f}"
    m = 'None' if s['mean'] is None else f"{s['mean'] * 100:+.3f}%"
    return f"n={s['n']} mean={m} t={t}"


def render_txt(res):
    L = []
    A = L.append
    A('E13 — listing drift 24h long-only, universo OKX globale (smoke da dati CONGELATI)')
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
    A('--- PER-TRIMESTRE (OKX, inclusi) ---')
    for t, s in res['okx_trimestre'].items():
        A(f"  {t}: {fmt_stats(s)}")
    c = res['okx_collapse_token']
    A(f"--- SENSIBILITA L2 collapse 1/token: n={c['n_token']} OOS {fmt_stats(c['oos'])} t1_like={c['t1_like']}")
    la = res['okx_larga']
    A(f"--- SENSIBILITA L3 lettura larga: inclusi={la['n_events']} OOS {fmt_stats(la['oos'])}")
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
