#!/usr/bin/env python3
"""E15 — test anti-look-ahead per l'engine (da eseguire PRIMA di guardare i numeri).

I 4 test della spec (a-d). Design: ogni test e' scritto per FALLIRE se l'engine
introduce una sbirciata al futuro o ignora la regola congelata:
(a) il segnale del giorno t non usa epoche di t+1 (mutare un rate futuro non cambia
    la posizione di t; mutare il passato si; la soglia di ingresso e' rispettata);
(b) il capitale vincolato e' 2x il nozionale (spot + margine 1x);
(c) un funding negativo riduce il PnL (non viene incassato come positivo) e la
    coppia esce;
(d) input vuoto -> exit 2 (fail-closed).

Eseguibile con pytest (`pytest test_e15_antilookahead.py`) o in autonomia
(`python3 test_e15_antilookahead.py`); rispetta E15_ENGINE_DIR per i run mutanti.
"""
import copy
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def _engine_dir():
    env = os.environ.get('E15_ENGINE_DIR')
    cands = ([env] if env else []) + [
        os.path.join(os.path.dirname(HERE), 'scripts'),   # scratch: e15/tests -> e15/scripts
        os.path.join(HERE, '..', '..', 'scripts'),        # repo: tests/ricerca -> root/scripts
        os.path.join(HERE, '..', '..', '..', 'scripts'),  # handoff annidato
    ]
    for c in cands:
        c = os.path.abspath(c)
        if os.path.exists(os.path.join(c, 'e15_carry_soglia.py')):
            return c
    raise RuntimeError('e15_carry_soglia.py non trovato (usa E15_ENGINE_DIR)')


ENGINE_DIR = _engine_dir()
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)
import e15_carry_soglia as eng  # noqa: E402

D0 = 1_700_000_000_000
D0 -= D0 % eng.MS_GIORNO


def mk_daily(fa_map, n_giorni):
    """Daily sintetico. fa_map: {sym: {i: fa_annualizzato_%}} (riga assente se None/manca).

    Cadenza 8h (n_epochs=3). sum_rate = 3 * mean_rate (segno del funding = segno FA).
    """
    giorni = [D0 + i * eng.MS_GIORNO for i in range(n_giorni)]
    daily = {}
    for sym, mappa in fa_map.items():
        righe = {}
        for i, fa in mappa.items():
            if fa is None:
                continue
            mean = fa / (3 * 365.0 * 100.0)
            righe[giorni[i]] = {'day': giorni[i], 'sum_rate': 3 * mean,
                                'n_epochs': 3, 'mean_rate': mean}
        daily[sym] = righe
    return daily, giorni


def test_segnale_giorno_t_non_usa_epoche_di_t_piu_1():
    n = 8
    base = {s: {i: fa for i in range(n)} for s, fa in
            [('A', 25.0), ('B', 20.0), ('C', 15.0), ('D', 12.0), ('E', 11.0),
             ('F', 10.0), ('G', 9.9)]}
    daily, giorni = mk_daily(base, n)
    univ = list(base)
    p1 = eng.posizioni_per_giorno(univ, daily, giorni)
    d4 = giorni[4]
    assert set(p1[d4]) == {'A', 'B', 'C', 'D', 'E'}, p1[d4]
    assert 'G' not in p1[d4], 'soglia di ingresso (10%) ignorata: G(FA=9.9) in posizione!'
    # mutazione FUTURA (giorni 4 e 5, anche oltre la soglia): posizioni di d4 invariate
    b2 = copy.deepcopy(base)
    b2['F'][4] = 100.0
    b2['F'][5] = 100.0
    b2['G'][4] = 100.0
    p2 = eng.posizioni_per_giorno(univ, mk_daily(b2, n)[0], giorni)
    assert p2[d4] == p1[d4], 'epoche future (t, t+1) influenzano la posizione del giorno t!'
    # mutazione del PASSATO (giorno 3 = segnale di d4): deve cambiare
    b3 = copy.deepcopy(base)
    b3['F'][3] = 100.0
    p3 = eng.posizioni_per_giorno(univ, mk_daily(b3, n)[0], giorni)
    assert set(p3[d4]) == {'F', 'A', 'B', 'C', 'D'}, p3[d4]


def test_capitale_vincolato_doppio_nozionale():
    assert eng.CAPITALE == 1000.0
    nz = eng.nozionale_per_coppia()
    assert abs(nz - 100.0) < 1e-12
    assert eng.capitale_vincolato_per_coppia() == 2 * nz, \
        'capitale vincolato per coppia != 2 x nozionale'
    assert abs(eng.capitale_vincolato_totale() - 1000.0) < 1e-12, \
        'capitale vincolato totale (5 coppie) != 1000 EUR'


def test_funding_negativo_riduce_pnl():
    giorni = [D0 + i * eng.MS_GIORNO for i in range(7)]
    mean = 20.0 / (3 * 365.0 * 100.0)

    def riga(day, sgn):
        return {'day': day, 'sum_rate': sgn * 3 * mean, 'n_epochs': 3,
                'mean_rate': sgn * mean}

    daily_b = {'A': {g: riga(g, 1.0) for g in giorni}}
    pos_b = eng.posizioni_per_giorno(['A'], daily_b, giorni)
    gp = giorni[1:]
    serie_b, n_sw_b, *_ = eng.pnl_per_giorno(pos_b, daily_b, gp, 100.0, 0.003)
    d4 = giorni[4]
    assert serie_b[d4] > 0, serie_b[d4]

    daily_n = {'A': {g: riga(g, -1.0 if g in (giorni[4], giorni[5]) else 1.0)
                     for g in giorni}}
    pos_n = eng.posizioni_per_giorno(['A'], daily_n, giorni)
    serie_n, n_sw_n, *_ = eng.pnl_per_giorno(pos_n, daily_n, gp, 100.0, 0.003)
    assert serie_n[d4] < serie_b[d4], 'funding negativo non riduce il PnL!'
    assert serie_n[d4] < 0, 'funding negativo incassato come positivo!'
    # uscita: al giorno 5 FA(4) < 5% -> A esce (e la regola 2-giorni-negativi concorda)
    assert pos_n[giorni[5]] == [], pos_n


def test_input_vuoto_exit_2():
    eng_path = os.path.join(ENGINE_DIR, 'e15_carry_soglia.py')
    with tempfile.TemporaryDirectory() as td:
        os.makedirs(os.path.join(td, 'dati'))
        with open(os.path.join(td, 'dati', 'funding_daily.json'), 'w') as f:
            json.dump({}, f)
        r = subprocess.run([sys.executable, eng_path, '--dati-dir',
                            os.path.join(td, 'dati'),
                            '--out-prove', os.path.join(td, 'prove')],
                           capture_output=True, text=True, timeout=120)
        assert r.returncode == 2, f'exit {r.returncode}: {r.stderr!r} {r.stdout!r}'
        assert 'FAIL-CLOSED' in r.stderr
    with tempfile.TemporaryDirectory() as td:
        r = subprocess.run([sys.executable, eng_path, '--dati-dir',
                            os.path.join(td, 'nope'),
                            '--out-prove', os.path.join(td, 'prove')],
                           capture_output=True, text=True, timeout=120)
        assert r.returncode == 2, f'exit {r.returncode}: {r.stderr!r}'


def _main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith('test_') and callable(v)]
    fails = []
    for fn in fns:
        try:
            fn()
            print(f'OK   {fn.__name__}')
        except Exception as e:  # noqa: BLE001
            print(f'FAIL {fn.__name__}: {e!r}')
            fails.append(fn.__name__)
    print(f'{len(fns) - len(fails)}/{len(fns)} verdi')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(_main())
