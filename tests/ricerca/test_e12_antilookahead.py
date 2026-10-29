#!/usr/bin/env python3
"""E12 — test anti-look-ahead per l'engine (da eseguire PRIMA di guardare i numeri).

Design: ogni test e' scritto per FALLIRE se l'engine introduce una sbirciata al futuro:
- entry a open(t0) e mai close(t0)/bar successivi;
- exit SOLO a close(t0+23h);
- selezione/filtri SOLO sui primi 24 bar (mai bar 24+);
- primo bar allineato a t0;
- nessun accesso rete nel sorgente dell'engine.

Eseguibile con pytest (`pytest test_e12_anti_lookahead.py`) o in autonomia:
`python3 test_e12_anti_lookahead.py` (rispetta E12_ENGINE_DIR per i run mutanti).
"""
import copy
import json
import os
import sys
import tempfile

H = 3600000
HERE = os.path.dirname(os.path.abspath(__file__))
# layout del repo: engine in <repo>/scripts/ (nel pacchetto di consegna era dirname(HERE))
ENGINE_DIR = os.environ.get('E12_ENGINE_DIR') or os.path.join(
    os.path.dirname(os.path.dirname(HERE)), 'scripts')
sys.path.insert(0, ENGINE_DIR)
import e12_listing_drift as eng  # noqa: E402

T0 = 1730000000000 - (1730000000000 % H)  # t0 orario sintetico (2024-10-27 ...)


def mk_bars(t0=T0, n=48, o0=100.0, c23=110.0, qv=1_000_000.0):
    bars = []
    for i in range(n):
        bars.append([str(t0 + i * H), '100.0', '103.0', '99.0', '101.5',
                     '1000', '100000', '%.4f' % (qv / 24.0), '1'])
    bars[0] = [str(t0), '%.4f' % o0, '103.0', '99.0', '101.5', '1000', '100000',
               '%.4f' % (qv / 24.0), '1']
    bars[23] = [str(t0 + 23 * H), '100.0', '106.0', '99.0', '%.4f' % c23, '1000', '100000',
                '%.4f' % (qv / 24.0), '1']
    return bars


def mk_bybit_bars(t0=T0, n=48, o0=100.0, c23=110.0, qv=1_000_000.0):
    bars = []
    for i in range(n):
        bars.append([str(t0 + i * H), '100.0', '103.0', '99.0', '101.5',
                     '1000', '%.4f' % (qv / 24.0)])
    bars[0] = [str(t0), '%.4f' % o0, '103.0', '99.0', '101.5', '1000', '%.4f' % (qv / 24.0)]
    bars[23] = [str(t0 + 23 * H), '100.0', '106.0', '99.0', '%.4f' % c23, '1000',
                '%.4f' % (qv / 24.0)]
    return bars


def write_freeze(dirp, venue, events, barsmap):
    with open(os.path.join(dirp, f'{venue}_events.jsonl'), 'w') as f:
        for e in events:
            f.write(json.dumps(e) + '\n')
    with open(os.path.join(dirp, f'{venue}_bars.jsonl'), 'w') as f:
        for k, v in barsmap.items():
            f.write(json.dumps({'instId': k, 'symbol': k, 'first_ms': v['first_ms'],
                                'n': len(v['bars']), 'bars': v['bars']}) + '\n')


def _ev(key, ann_ms, t0=T0):
    return {'instId': key, 'symbol': key, 'pair': key, 'ann_ms': ann_ms,
            'ann_utc': '2026-01-01 00:00', 'first_ms': t0}


# ---------------- test ----------------

def test_entry_uses_open_of_t0_not_close():
    bars = mk_bars()
    r1 = eng.check_and_compute(bars, T0)
    assert r1['ok']
    b2 = copy.deepcopy(bars)
    b2[0][4] = '999.0'  # close(t0) assurdo: NON deve influenzare il return
    r2 = eng.check_and_compute(b2, T0)
    assert abs(r1['ret_base'] - r2['ret_base']) < 1e-12, 'close(t0) influenza il return!'
    b3 = copy.deepcopy(bars)
    b3[0][1] = '200.0'  # open(t0) raddoppiato: il return DEVE cambiare
    r3 = eng.check_and_compute(b3, T0)
    assert abs(r1['ret_base'] - r3['ret_base']) > 1e-9, 'open(t0) non usato come entry!'


def test_exit_is_close_of_24th_bar_only():
    bars = mk_bars()
    r0 = eng.check_and_compute(bars, T0)
    b1 = copy.deepcopy(bars)
    b1[22][4] = '888.0'  # close del 23o bar: NON usato
    r1 = eng.check_and_compute(b1, T0)
    assert abs(r0['ret_base'] - r1['ret_base']) < 1e-12
    b2 = copy.deepcopy(bars)
    b2[23][4] = '120.0'  # close del 24o bar: usato
    r2 = eng.check_and_compute(b2, T0)
    assert abs(r0['ret_base'] - r2['ret_base']) > 1e-9


def test_future_bars_never_used():
    """Sbirciata al futuro: i bar 24..47 (dopo l'uscita) NON devono entrare in nulla."""
    bars = mk_bars()
    r0 = eng.check_and_compute(bars, T0)
    b = copy.deepcopy(bars)
    for i in range(24, 48):
        b[i][1] = '1e9'
        b[i][2] = '9e9'
        b[i][4] = '8e9'
        b[i][5] = '777'
        b[i][7] = '7e12'
    r1 = eng.check_and_compute(b, T0)
    assert abs(r0['ret_base'] - r1['ret_base']) < 1e-12, 'bar futuri influenzano il return!'
    assert abs(r0['ret_stress'] - r1['ret_stress']) < 1e-12
    assert abs(r0['qvol24'] - r1['qvol24']) < 1e-9, 'volume oltre il 24o bar usato nei filtri!'


def test_gap_disorder_excluded():
    bars = mk_bars()
    b = copy.deepcopy(bars)
    del b[5]  # ora i bar 0..23 contengono il vecchio bar 24 (buco + non orario)
    r = eng.check_and_compute(b, T0)
    assert not r['ok'] and 'buco' in r['reason']
    b2 = copy.deepcopy(bars)
    b2[10][0] = str(T0 + 10 * H + 60000)  # ts spostato di 1 minuto
    r2 = eng.check_and_compute(b2, T0)
    assert not r2['ok'] and 'buco' in r2['reason']


def test_zeros_excluded():
    bars = mk_bars()
    b = copy.deepcopy(bars)
    b[7][5] = '0'  # volume zero
    assert not eng.check_and_compute(b, T0)['ok']
    b2 = copy.deepcopy(bars)
    b2[9][4] = '0'  # close zero
    assert not eng.check_and_compute(b2, T0)['ok']
    b3 = copy.deepcopy(bars)
    b3[3][1] = '-5'  # open negativo
    assert not eng.check_and_compute(b3, T0)['ok']
    b4 = copy.deepcopy(bars)
    b4[11][8] = '0'  # bar non piena
    assert not eng.check_and_compute(b4, T0)['ok']


def test_volume_threshold_boundary():
    below = mk_bars(qv=49_999.0)
    assert not eng.check_and_compute(below, T0)['ok']
    at = mk_bars(qv=50_000.4)
    r = eng.check_and_compute(at, T0)
    assert r['ok'], r
    above = mk_bars(qv=60_000.0)
    assert eng.check_and_compute(above, T0)['ok']


def test_costs_and_stress():
    bars = mk_bars()
    r = eng.check_and_compute(bars, T0)
    assert abs((r['ret_base'] - r['ret_stress']) - (eng.COST_STRESS - eng.COST_BASE)) < 1e-12
    assert abs(r['ret_base'] - (110.0 / 100.0 - 1 - 0.003)) < 1e-9


def test_first_bar_alignment_enforced():
    bars = mk_bars()
    try:
        eng.check_and_compute(bars, T0 + H)  # t0 sbagliato di 1h
    except eng.DataError:
        return
    raise AssertionError('primo bar non allineato non rilevato!')


def test_bands_train_oos_boundary():
    with tempfile.TemporaryDirectory() as d:
        t0a = T0
        t0b = T0 + 100 * H
        events = [_ev('AAA-USDT', eng.SPLIT_MS - 1, t0a), _ev('BBB-USDT', eng.SPLIT_MS, t0b)]
        bars = {'AAA-USDT': {'first_ms': t0a, 'bars': mk_bars(t0a)},
                'BBB-USDT': {'first_ms': t0b, 'bars': mk_bars(t0b)}}
        write_freeze(d, 'okx', events, bars)
        res = eng.run_venue(d, 'okx')
        bands = {r['key']: r['band'] for r in res['events']}
        assert bands['AAA-USDT'] == 'TRAIN'
        assert bands['BBB-USDT'] == 'OOS'


def test_dedupe_duplicate_instrument_rejected():
    with tempfile.TemporaryDirectory() as d:
        events = [_ev('AAA-USDT', eng.SPLIT_MS - 1), _ev('AAA-USDT', eng.SPLIT_MS)]
        bars = {'AAA-USDT': {'first_ms': T0, 'bars': mk_bars()}}
        write_freeze(d, 'okx', events, bars)
        try:
            eng.run_venue(d, 'okx')
        except eng.DataError:
            return
        raise AssertionError('strumento duplicato non rilevato!')


def test_missing_bar_rejected():
    with tempfile.TemporaryDirectory() as d:
        events = [_ev('AAA-USDT', eng.SPLIT_MS - 1)]
        write_freeze(d, 'okx', events, {})
        try:
            eng.run_venue(d, 'okx')
        except eng.DataError:
            return
        raise AssertionError('bar mancanti non rilevati!')


def test_gate_t1_n_min():
    fake = {'oos': {'n': 59, 'mean': 0.10, 'sd': 0.2, 't': 5.0},
            'oos_stress': {'n': 59, 'mean': 0.09, 'sd': 0.2, 't': 4.0},
            'train': {'n': 10, 'mean': 0.01, 'sd': 0.1, 't': 1.0},
            'oos_half1': {'n': 29, 'mean': 0.01}, 'oos_half2': {'n': 30, 'mean': 0.02}}
    g = eng.gate_t1(fake)
    assert g['pass'] is False and 'n OOS 59' in g['reason']
    fake['oos']['n'] = 60
    assert eng.gate_t1(fake)['pass'] is True
    fake['oos']['t'] = 2.69
    assert eng.gate_t1(fake)['pass'] is False


def test_bybit_7field_format_supported():
    bars = mk_bybit_bars(qv=80_000.0)
    r = eng.check_and_compute(bars, T0)
    assert r['ok']
    assert abs(r['qvol24'] - 80_000.0) < 1.0


def test_engine_source_has_no_network():
    src = open(eng.__file__).read()
    for tok in ('urllib', 'urlopen', 'requests.', 'socket.'):
        assert tok not in src, f'token di rete {tok} trovato nel sorgente engine!'


def _main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith('test_') and callable(v)]
    fails = []
    for fn in fns:
        try:
            fn()
            print(f'PASS {fn.__name__}')
        except Exception as e:  # noqa: BLE001
            fails.append(fn.__name__)
            print(f'FAIL {fn.__name__}: {e!r}')
    print(f'--- {len(fns) - len(fails)}/{len(fns)} test verdi ---')
    if fails:
        print('ROSSI:', fails)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(_main())
