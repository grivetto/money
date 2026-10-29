#!/usr/bin/env python3
"""E12 — evidenza RED: le mutazioni "sbirciata al futuro" sull'engine DEVONO far fallire i test.

Per ogni mutazione (copiata in una tmp dir): esegue la suite dei test contro la copia mutata
(tramite E12_ENGINE_DIR) ed esige un exit code != 0 (almeno un test rosso).
Se una mutazione NON viene rilevata -> questo script fallisce.
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
# layout del repo: test in tests/ricerca/, engine in <repo>/scripts/
TEST = os.path.join(HERE, 'test_e12_antilookahead.py')
ENGINE = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'scripts', 'e12_listing_drift.py')

src = open(ENGINE).read()

MUTATIONS = {
    'M1_entry_da_close_t0': ('o0 = _f(w[0][1])', 'o0 = _f(w[0][4])'),
    'M2_exit_da_bar_futuro_24': ('c23 = _f(w[23][4])', 'c23 = _f(bars[24][4])'),
    'M3_volume_include_futuro': ('qv += _f(b[7]) if len(b) > 7 else _f(b[6])',
                                 'qv += sum(_f(x[7]) for x in bars[24:]) if len(b) > 7 else _f(b[6])'),
}

ok = True
for name, (old, new) in MUTATIONS.items():
    if old not in src:
        print(f'!! pattern non trovato per {name}: {old!r}')
        ok = False
        continue
    mut = src.replace(old, new)
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'e12_listing_drift.py')
        with open(p, 'w') as f:
            f.write(mut)
        env = dict(os.environ, E12_ENGINE_DIR=d)
        r = subprocess.run([sys.executable, TEST], env=env, capture_output=True, text=True)
        red = r.returncode != 0
        print(f'== {name}: exit={r.returncode} rosso_atteso={"OK" if red else "NON RILEVATA!"}')
        tail = [l for l in r.stdout.splitlines() if l.startswith('FAIL') or l.startswith('---')]
        for l in tail:
            print('   ', l)
        if not red:
            ok = False

print('ESITO:', 'tutte le mutazioni rilevate (evidenza anti-look-ahead OK)' if ok else 'MUTAZIONI NON RILEVATE')
sys.exit(0 if ok else 1)
