#!/usr/bin/env python3
"""Test anti-look-ahead per il motore E11 «TSMOM 12M/1M long-only BTC/ETH».

Contratto (spec E11 — test OBBLIGATORIO PRIMA dei numeri):
1. il segnale del mese r usa SOLO barre <= ultimo giorno del mese r-1;
2. l'ingresso e' all'apertura del primo giorno utile >= r (mai al close del giorno
   di ribilanciamento);
3. il test DEVE fallire se R12(r) ingoia il close di r o giorni successivi, o se
   l'ingresso usa il close del giorno di ribilanciamento — le controprove finali
   usano varianti bacate e verificano che l'invariante le SMASCHERA (discriminante).

Eseguito PRIMA dei numeri (spec): `pytest tests/ricerca/ -q -k e11` oppure
`python3 tests/ricerca/test_e11_antilookahead.py` (runner interno, senza pytest).
"""
import os
import sys
from datetime import datetime, timezone

QUI = os.path.dirname(os.path.abspath(__file__))
RADICE = os.path.normpath(os.path.join(QUI, "..", ".."))
for _d in (os.path.join(RADICE, "scripts"), os.path.join(RADICE, "src")):
    if os.path.isdir(_d) and _d not in sys.path:
        sys.path.insert(0, _d)

import e11_tsmom as e11  # noqa: E402

MS = 86_400_000
T0 = int(datetime(2019, 1, 1, 16, tzinfo=timezone.utc).timestamp() * 1000)


def _d(ts):
    return datetime.fromtimestamp(ts / 1000, timezone.utc)


def _fixture(n=800, modo="crescita"):
    """Barre giornaliere sintetiche da T0 (una ogni 24h, come OKX 1D).

    Gap marcato all'open del 1o di ogni mese (open = close_prec * 1.10) e salto
    intraday (close = open * 1.05): rende DISCRIMINANTE il prezzo d'ingresso
    (open del giorno di ribilanciamento vs close dello stesso giorno).
    modi: "crescita" (R12 > 0 -> long), "discesa" (R12 < 0 -> flat), "giro"
    (sale 500 giorni poi scende: produce entrata E uscita).
    """
    out = []
    prec = None
    for i in range(n):
        ts = T0 + i * MS
        dd = _d(ts)
        if modo == "crescita":
            c = 100.0 + 0.10 * i
        elif modo == "discesa":
            c = 200.0 - 0.10 * i
        else:  # giro
            c = 100.0 + 0.20 * i if i < 500 else 100.0 + 0.20 * 500 - 0.60 * (i - 500)
        o = prec if prec is not None else c
        if dd.day == 1:
            o = o * 1.10
            c = o * 1.05
        out.append([ts, o, max(o, c) * 1.001, min(o, c) * 0.999, c, 10.0])
        prec = c
    return out


def _fine_mese(barre, p):
    a, m = _d(barre[p][0]).year, _d(barre[p][0]).month
    return max(i for i in range(p, len(barre))
               if (_d(barre[i][0]).year, _d(barre[i][0]).month) == (a, m))


# --- 1. R12 non guarda il futuro; dipende da close(i) e close(i-365) ---------------

def test_r12_solo_passato():
    barre = _fixture(900)
    i = 700
    r1 = e11.r12_serie(barre)
    assert r1[i] is not None
    b2 = [list(r) for r in barre]
    for j in range(i + 1, len(b2)):
        b2[j][4] *= 1.5
    assert r1[i] == e11.r12_serie(b2)[i], "R12(i) cambiato perturbando il FUTURO: look-ahead"
    b3 = [list(r) for r in barre]
    b3[i][4] *= 1.2
    assert e11.r12_serie(b3)[i] != r1[i], "R12(i) non dipende dal close(i)"
    b4 = [list(r) for r in barre]
    b4[i - 365][4] *= 1.2
    assert e11.r12_serie(b4)[i] != r1[i], "R12(i) non dipende dal close(i-365)"


# --- 2. il segnale del mese r usa SOLO il mese r-1 ----------------------------------

def test_segnale_mese_r_solo_mese_precedente():
    barre = _fixture(700)
    r12 = e11.r12_serie(barre)
    pos = e11.posizioni_mensili(barre, r12)
    k = (2020, 5)
    assert pos[k] == 1  # fixture crescente -> R12 > 0

    # (a) perturbare TUTTE le barre del mese k (primo giorno incluso) NON cambia il segnale
    b2 = [list(r) for r in barre]
    for r in b2:
        dd = _d(r[0])
        if (dd.year, dd.month) == k:
            r[4] *= 0.5
    assert e11.posizioni_mensili(b2, e11.r12_serie(b2))[k] == 1, \
        "segnale del mese r cambiato perturbando le barre del mese r: look-ahead"

    # (b) perturbare il close dell'ULTIMO giorno del mese precedente lo cambia (flip)
    mesi = e11.indici_mesi(barre)
    i1_apr = next(i1 for a, m, _i0, i1 in mesi if (a, m) == (2020, 4))
    b3 = [list(r) for r in barre]
    b3[i1_apr][4] *= 0.5
    assert e11.posizioni_mensili(b3, e11.r12_serie(b3))[k] == 0, \
        "segnale insensibile al close dell'ultimo giorno del mese precedente"


# --- 3. ingresso all'OPEN del giorno di ribilanciamento (mai al close) --------------

def test_ingresso_all_open_primo_giorno():
    barre = _fixture(800)
    r12 = e11.r12_serie(barre)
    pos = e11.posizioni_mensili(barre, r12)
    i_da = 365
    serie = e11.serie_rendimenti(barre, pos, i_da, len(barre) - 1, costo_rt=0.0)
    rec = next(x for x in serie if x["switch"] and x["pos"] == 1)  # prima entrata
    p = rec["i"]
    assert p - i_da >= 1, "fixture: ribilanciamento troppo a inizio serie"
    assert _d(barre[p][0]).day == 1, "ribilanciamento non sul primo giorno del mese"
    assert serie[p - i_da - 1]["pos"] == 0, "l'entrata non partiva da FLAT"

    atteso = barre[p][4] / barre[p][1] - 1.0  # close(p)/open(p) - 1
    assert abs(rec["r"] - atteso) < 1e-12, "il giorno di ingresso non usa open(p)"

    q = _fine_mese(barre, p)
    comp = 1.0
    for x in serie:
        if p <= x["i"] <= q:
            assert x["pos"] == 1
            comp *= (1.0 + x["r"])
    comp_atteso = barre[q][4] / barre[p][1] - 1.0
    assert abs((comp - 1.0) - comp_atteso) < 1e-9, \
        "composto del periodo != close(q)/open(p)-1"
    bacato = barre[q][4] / barre[p][4] - 1.0  # variante: ingresso al close(p)
    assert abs(comp_atteso - bacato) > 1e-6, "fixture non discriminante open vs close"

    # il close del giorno di ribilanciamento si ELIDE nel composto: perturbarlo invano
    b2 = [list(r) for r in barre]
    b2[p][4] *= 1.2
    posb = e11.posizioni_mensili(b2, e11.r12_serie(b2))
    compb = 1.0
    for x in e11.serie_rendimenti(b2, posb, p, q, costo_rt=0.0):
        compb *= (1.0 + x["r"])
    assert abs((compb - 1.0) - comp_atteso) < 1e-9, \
        "il composto dipende dal close del giorno di ribilanciamento (ingresso al close)"


# --- 4. uscita (long -> flat) all'open del primo giorno ------------------------------

def test_uscita_all_open():
    barre = _fixture(900, modo="giro")
    r12 = e11.r12_serie(barre)
    pos = e11.posizioni_mensili(barre, r12)
    serie = e11.serie_rendimenti(barre, pos, 365, len(barre) - 1, costo_rt=0.0)
    rec = next(x for x in serie if x["switch"] and x["pos"] == 0)
    p = rec["i"]
    assert _d(barre[p][0]).day == 1
    atteso = barre[p][1] / barre[p - 1][4] - 1.0  # open(p)/close(p-1) - 1
    assert abs(rec["r"] - atteso) < 1e-12, "l'uscita non e' all'open del giorno di switch"


# --- 5. posizione costante tra ribilanciamenti; switch solo al primo giorno ----------

def test_posizione_costante_tra_ribilanciamenti():
    barre = _fixture(800)
    r12 = e11.r12_serie(barre)
    pos = e11.posizioni_mensili(barre, r12)
    serie = e11.serie_rendimenti(barre, pos, 365, len(barre) - 1, costo_rt=0.0)
    prec_mese = None
    v_mese = None
    for x in serie:
        dd = _d(barre[x["i"]][0])
        k = (dd.year, dd.month)
        v = pos.get(k)
        v = 0 if v is None else v
        if k != prec_mese:
            prec_mese = k
            v_mese = v
        assert x["pos"] == v_mese, "posizione incoerente col segnale mensile"
        if dd.day != 1:
            assert x["switch"] is False, "switch fuori dal primo giorno del mese"


# --- 6. costi: solo allo switch; stress = x2 -----------------------------------------

def test_costi_solo_al_cambio():
    barre = _fixture(800)
    r12 = e11.r12_serie(barre)
    pos = e11.posizioni_mensili(barre, r12)
    serie = e11.serie_rendimenti(barre, pos, 365, len(barre) - 1, costo_rt=e11.COSTO_RT)
    n_switch = 0
    for x in serie:
        if x["switch"]:
            n_switch += 1
            assert abs(x["r_stress"] - (x["r"] - e11.COSTO_RT)) < 1e-15, \
                "stress != costo x2 sul giorno di switch"
        else:
            assert x["r"] == x["r_stress"], "costo applicato su un giorno senza switch"
    assert n_switch >= 1, "fixture senza switch: da rivedere"
    rec = next(x for x in serie if x["switch"] and x["pos"] == 1)
    lordo = barre[rec["i"]][4] / barre[rec["i"]][1] - 1.0
    assert abs(rec["r"] - (lordo - e11.COSTO_RT)) < 1e-12, "costo di entrata non applicato"


# --- 7. controprove: le varianti BACATE vengono smascherate ---------------------------

def test_variante_lookahead_smascherata():
    # (a) variante che calcola R12(r) col close del mese r: l'invariante del test 2
    # (segnale invariante sotto perturbazione del mese r) DEVE fallire su di essa.
    barre = _fixture(700)
    r12 = e11.r12_serie(barre)
    k = (2020, 5)

    def segnale_variante(barre_, r12_, k_):
        mesi = e11.indici_mesi(barre_)
        i1_k = next(i1 for a, m, _i0, i1 in mesi if (a, m) == k_)
        r = r12_[i1_k]
        return None if r is None else (1 if r > 0 else 0)

    b2 = [list(r) for r in barre]
    for r in b2:
        dd = _d(r[0])
        if (dd.year, dd.month) == k:
            r[4] *= 0.5
    r12b = e11.r12_serie(b2)
    assert e11.posizioni_mensili(b2, r12b)[k] == e11.posizioni_mensili(barre, r12)[k]
    assert segnale_variante(b2, r12b, k) != segnale_variante(barre, r12, k), \
        "controprova non discriminante (a): rivedere la fixture"

    # (b) variante che entra al close del giorno di ribilanciamento: il composto
    # del periodo di detenzione DEVE differire da close(q)/close(p)-1 (test 3).
    barre2 = _fixture(800)
    pos2 = e11.posizioni_mensili(barre2, e11.r12_serie(barre2))
    serie2 = e11.serie_rendimenti(barre2, pos2, 365, len(barre2) - 1, costo_rt=0.0)
    p = next(x for x in serie2 if x["switch"] and x["pos"] == 1)["i"]
    q = _fine_mese(barre2, p)
    comp = 1.0
    for x in serie2:
        if p <= x["i"] <= q:
            comp *= (1.0 + x["r"])
    corretto = barre2[q][4] / barre2[p][1] - 1.0
    bacato = barre2[q][4] / barre2[p][4] - 1.0
    assert abs((comp - 1.0) - corretto) < 1e-9
    assert abs((comp - 1.0) - bacato) > 1e-6, \
        "controprova non discriminante (b): la variante al close non verrebbe smascherata"


if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    ok = 0
    for nome, fn in fns:
        try:
            fn()
            ok += 1
            print(f"PASS {nome}")
        except AssertionError as e:
            print(f"FAIL {nome}: {e}")
            raise SystemExit(1)
    print(f"\n{ok}/{len(fns)} test verdi (runner interno, senza pytest)")
