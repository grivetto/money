#!/usr/bin/env python3
"""Test anti-look-ahead per il motore E8 (momentum estremo, hold-out Bitvavo).

Contratto (spec E8, punto «Test falsificabile»): il segnale della barra i deve
dipendere SOLO da candele chiuse <= i; il test DEVE fallire se la barra di
segnale usa il close della barra stessa, o se l'ingresso non e' all'open della
barra successiva.

Eseguito PRIMA della misura (spec): `.venv/bin/python -m pytest tests/ricerca/ -q -k e8`.
"""
import os
import sys

RADICE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(RADICE, "scripts"))
sys.path.insert(0, os.path.join(RADICE, "src"))

import e5_meanrev_7g as e5  # noqa: E402


# ---- helper: barre sintetiche [ts, o, h, l, c, v] ---------------------------------


def _barre(n, base=100.0, step=0.1):
    out = []
    for i in range(n):
        c = base + i * step
        out.append([1_700_000_000_000 + i * 3_600_000, c - 0.05, c + 0.1, c - 0.1, c, 10.0])
    return out


def _barre_larghe(n, base=100.0):
    """Range ampio (h/l ±20%): distanza di stop = 0.5 (cap), mai toccata — isola l'uscita da |z|."""
    out = []
    for i in range(n):
        c = base + i * 0.001
        out.append([1_700_000_000_000 + i * 3_600_000, c - 5.0, c + 20.0, c - 20.0, c, 10.0])
    return out


# ---- TEST 1: z[i] non usa barre > i; usa eccome la barra i ------------------------


def test_zscores_no_future_leak():
    b1 = _barre(400)
    z1 = e5.zscores(b1)
    i = 300

    # perturbare TUTTE le barre successive a i non deve cambiare z[i]
    b2 = [list(r) for r in b1]
    for k in range(i + 1, len(b2)):
        b2[k][4] = b2[k][4] * 1.5  # close futuro alterato
        b2[k][1], b2[k][2], b2[k][3] = b2[k][1] * 1.5, b2[k][2] * 1.5, b2[k][3] * 1.5
    z2 = e5.zscores(b2)
    assert z1[i] == z2[i], "z[i] e' cambiato perturbando il FUTURO: look-ahead"

    # ma z[i] DEVE dipendere dalla barra i (usa il close della barra stessa)
    b3 = [list(r) for r in b1]
    b3[i][4] = b3[i][4] * 1.2
    z3 = e5.zscores(b3)
    assert z1[i] != z3[i], "z[i] non dipende dalla barra i: contratto violato"


# ---- TEST 2: gli eventi <= k non cambiano perturbando barre > k -------------------


def test_eventi_decisione_solo_passato():
    b = _barre(600)
    # innesca un estremo: crollo forte di un tratto (sufficiente a z <= -3)
    for k in range(520, 560):
        b[k][4] = b[k][4] * 0.80
        b[k][1], b[k][3] = min(b[k][1], b[k][4]), min(b[k][3], b[k][4])
    z = e5.zscores(b)
    ev1 = e5.eventi(b, z)
    assert ev1, "scenario di test senza eventi: da rivedere"

    # perturba il futuro oltre l'ULTIMO evento: gli eventi fino a lì restano identici
    ultimo = max(i for i, _ in ev1)
    b2 = [list(r) for r in b]
    for k in range(ultimo + 1, len(b2)):
        b2[k][4] *= 1.10
    z2 = e5.zscores(b2)
    ev2 = e5.eventi(b2, z2)
    ev2_fino_a_ultimo = [e for e in ev2 if e[0] <= ultimo]
    assert ev1 == ev2_fino_a_ultimo, "eventi <=k cambiati perturbando il futuro: look-ahead"


# ---- TEST 3: ingresso all'OPEN della barra i+1, uscita al close della barra j -----


def test_ingresso_open_successivo_uscita_close():
    n = 340
    b = _barre(n)
    i = 240
    # z costruito a mano: nessuna uscita per rientro fino a j = i+5, poi |z|<=0.5
    z = [2.0] * n
    z[i + 5] = 0.0  # rientro alla barra i+5
    r = e5.simula(b, i, z, 1)
    assert r is not None
    netto, _stress, motivo, _dist = r
    assert motivo == "rientro"
    # se l'ingresso fosse il close di i (o qualsiasi altra barra), il lordo ricostruito
    # NON coinciderebbe: open(i+1) e close(i) differiscono di 0.05 (~4e-4 relativo)
    lordo_atteso = float(b[i + 5][4]) / float(b[i + 1][1]) - 1.0
    lordo_ottenuto = netto + e5.COSTO_RT
    assert abs(lordo_ottenuto - lordo_atteso) < 1e-12, (
        "l'ingresso non e' l'open della barra i+1 (o l'uscita non e' il close di j)")
    lordo_con_close_i = float(b[i + 5][4]) / float(b[i][4]) - 1.0
    assert abs(lordo_atteso - lordo_con_close_i) > 1e-9, "fixture non discriminante"


# ---- TEST 4: uscita SIMMETRICA in |z| (il bug E6: per-lato chiudeva subito) -------


def test_uscita_simmetrica_abs():
    n = 340
    b = _barre_larghe(n)
    i = 240

    # lato long, z resta +2.5: |z| > 0.5 -> NON si esce per rientro
    z = [2.5] * n
    r = e5.simula(b, i, z, 1)
    assert r is not None and r[2] == "tempo", f"uscita anticipata long con |z|=2.5: {r[2] if r else None}"

    # lato short, z resta -2.5: speculare
    r2 = e5.simula(b, i, z_neg := [-2.5] * n, -1)
    assert r2 is not None and r2[2] == "tempo", "uscita anticipata short con |z|=2.5"

    # rientro con |z| <= 0.5 (simmetrico sui due segni)
    z3 = [2.5] * n
    z3[i + 3] = -0.4
    r3 = e5.simula(b, i, z3, 1)
    assert r3 is not None and r3[2] == "rientro", "|z|<=0.5 negativo non chiude il long"


# ---- TEST 5: loader Bitvavo = formato cache atteso (skip se dati assenti) ---------


def test_loader_bitvavo_formato():
    import json
    from pathlib import Path

    import pytest

    cache = Path(RADICE) / "data" / "cache"
    files = sorted(cache.glob("bitvavo_*_1h.json"))
    if len(files) < 7:
        pytest.skip("cache Bitvavo non presente su questa macchina")
    for p in files:
        d = json.loads(p.read_text())
        assert set(("venue", "simbolo", "timeframe", "barre")) <= set(d)
        assert d["venue"] == "bitvavo" and d["timeframe"] == "1h"
        b = d["barre"]
        assert len(b) >= 3000
        ts = [x[0] for x in b]
        assert all(ts[i] < ts[i + 1] for i in range(len(ts) - 1)), "barre non ordinate"
