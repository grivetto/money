#!/usr/bin/env python3
"""Test anti-look-ahead per il motore E10 «stablecoin net issuance -> BTC/ETH long-only».

Contratto (spec E10 — test OBBLIGATORIO PRIMA dei numeri):
1. la decisione presa alla chiusura di t usa SOLO dati <= t e NESSUN dato >= t+1:
   - z_t = (S_t - media(S[t-365:t])) / stdev(S[t-365:t])  (la finestra trailing ESCLUDE t in poi;
     S_t al numeratore puo' includere il giorno t, che e' chiuso);
   - S_t usa I[t-29..t] (solo giorni <= t);
   - perturbare qualunque dato di giorni > t NON cambia z_t ne' la posizione pos(t).
2. la posizione entra/switcha all'APERTURA della barra t+1 (mai alla chiusura di t ne' di t+1):
   il giorno di switch, r = (1+po*(o/cp-1))*(1+pn*(c/o-1))-1, con ingresso da flat:
   r = c/o - 1 (open del giorno d'ingresso), uscita: r = o/cp - 1.
3. il test DEVE fallire sulle varianti BACATE (controprove con discriminante):
   (a) z_t con finestra che include giorni > t  -> smascherata dall'invarianza al futuro;
   (b) ingresso alla chiusura del giorno di segnale/t+1 -> smascherata dalle meccaniche d'ingresso.

Eseguito PRIMA dei numeri: `pytest tests/ricerca/ -q -k e10` oppure
`python3 tests/ricerca/test_e10_antilookahead.py` (runner interno, senza pytest).
"""
import math
import os
import sys
from datetime import datetime, timedelta, timezone

QUI = os.path.dirname(os.path.abspath(__file__))
RADICE = os.path.normpath(os.path.join(QUI, "..", ".."))
for _d in (QUI, os.path.join(RADICE, "scripts"), os.path.join(RADICE, "src"),
           os.path.join(os.path.expanduser("~"), "money", "src")):
    if os.path.isdir(_d) and _d not in sys.path:
        sys.path.insert(0, _d)

import e10_stablecoin as e10  # noqa: E402


# --- fixture sintetiche ------------------------------------------------------------------

def _giorno(i, inizio="2019-01-01"):
    return (datetime.strptime(inizio, "%Y-%m-%d") + timedelta(days=i)).strftime("%Y-%m-%d")


def _ts(i, inizio="2019-01-01"):
    """Timestamp della barra-giorno i sulla griglia OKX 1D (16:00 UTC)."""
    d = (datetime.strptime(inizio, "%Y-%m-%d") + timedelta(days=i)).replace(
        hour=16, tzinfo=timezone.utc)
    return int(d.timestamp() * 1000)


def _barre_fixture(n=900):
    """Barre giornaliere con mossa intraday marcata (open != close, ~+-1%): rende
    DISCRIMINANTE il prezzo d'ingresso (apertura vs chiusura)."""
    out = []
    for i in range(n):
        c = 100.0 + 0.13 * i + 3.0 * math.sin(i / 9.0)
        o = c * (1.01 if i % 2 == 0 else 0.99)
        out.append([_ts(i), o, max(o, c) * 1.001, min(o, c) * 0.999, c, 10.0])
    return out


def _stbl_fixture(n=900):
    """3 coin (quote 50/30/20%) con supply cumulate da un pattern di issuance:
    base lenta + impulso POSITIVO (giorni 350..409) + impulso NEGATIVO (410..469).
    Produce attraversamenti garantiti di +1 e di 0 dopo il warmup (~t=395)."""
    pattern = []
    for t in range(n):
        base = 1.0e9 * (1.0 + 0.2 * math.sin(2 * math.pi * t / 97.0))
        pulse = 0.0
        if 350 <= t < 410:
            pulse = 3.0e10
        elif 410 <= t < 470:
            pulse = -3.0e10
        pattern.append(base + pulse)
    quote = {"usdt": 0.5, "usdc": 0.3, "dai": 0.2}
    stbl = {}
    for nome, q in quote.items():
        supply = 1.0e10
        coin = {}
        for t in range(n):
            supply += pattern[t] * q
            coin[_giorno(t)] = supply
        stbl[nome] = coin
    return stbl, pattern


def _stbl_perturbata(stbl, pattern, tau, ampiezza=5.0e10):
    """Copia della fixture con il pattern di issuance perturbato sui giorni > tau:
    oscillazione alternata di ampiezza enorme -> attraversamenti garantiti delle soglie
    per qualunque pipeline sensibile ai giorni futuri (mette alla prova la controprova)."""
    n = len(pattern)
    p2 = list(pattern)
    for t in range(tau + 1, n):
        p2[t] = p2[t] + ampiezza * (1.0 if t % 2 == 0 else -1.0)
    quote = {"usdt": 0.5, "usdc": 0.3, "dai": 0.2}
    out = {}
    for nome, q in quote.items():
        supply = 1.0e10
        coin = {}
        for t in range(n):
            supply += p2[t] * q
            coin[_giorno(t)] = supply
        out[nome] = coin
    return out


def _pipeline(stbl, barre, z_fn=None):
    giorni, I, _ = e10.serie_I(stbl)
    S = e10.serie_S(giorni, I)
    z = e10.serie_z(giorni, S) if z_fn is None else z_fn(S)
    pos = e10.serie_pos(giorni, z)
    pos_by_date = {giorni[i]: pos[i] for i in range(len(giorni))}
    rec = e10.serie_rendimenti(barre, pos_by_date)
    return {"giorni": giorni, "I": I, "S": S, "z": z, "pos": pos,
            "pos_by_date": pos_by_date, "rec": rec}


def _z_bacata(S, j=365):
    """Variante BACATA (controprova): finestra trailing che termina a t+1 — include
    giorni > t. Il test d'invarianza al futuro DEVE smascherarla."""
    out = [None] * len(S)
    for t in range(len(S)):
        if S[t] is None or t < j:
            continue
        finestra = S[t - j + 2:t + 2]  # indici t-363..t+1 (365 valori, include t e t+1)
        if any(x is None for x in finestra):
            continue
        sd = e10.deviazione(finestra)
        if sd <= 0:
            continue
        out[t] = (S[t] - e10.media(finestra)) / sd
    return out


# --- 1. z: solo passato; dipende da t e dalla finestra ------------------------------------

def test_z_solo_passato_invariante_al_futuro():
    S = [100.0 + 1.0 * i + 1.5 * (i % 7) for i in range(800)]
    date = [_giorno(i) for i in range(800)]
    t = 700
    z = e10.serie_z(date, S)
    assert z[t] is not None
    S2 = list(S)
    for j in range(t + 1, 800):
        S2[j] *= 3.0
    assert e10.serie_z(date, S2)[t] == z[t], \
        "z_t cambiato perturbando il FUTURO: look-ahead"
    S3 = list(S)
    S3[t] *= 3.0
    assert e10.serie_z(date, S3)[t] != z[t], "z_t non dipende dal giorno t (S_t al numeratore)"
    S4 = list(S)
    S4[t - 365] *= 3.0
    assert e10.serie_z(date, S4)[t] != z[t], "z_t non dipende dal bordo sinistro della finestra"
    S5 = list(S)
    S5[t - 1] *= 3.0
    assert e10.serie_z(date, S5)[t] != z[t], "z_t non dipende dal bordo destro (t-1)"
    S6 = list(S)
    S6[t - 366] *= 3.0
    assert e10.serie_z(date, S6)[t] == z[t], "z_t dipende da t-366: finestra piu' larga del dichiarato"


def test_z_formula_campionaria_esatta():
    I = [1.0 + (i % 9) * 0.5 + 0.05 * i for i in range(800)]
    date = [_giorno(i) for i in range(800)]
    S = e10.serie_S(date, I)  # S[0..28] = None (warmup 30g)
    z = e10.serie_z(date, S)
    t = 600
    finestra = S[t - 365:t]
    m = math.fsum(finestra) / len(finestra)
    sd = math.sqrt(sum((x - m) ** 2 for x in finestra) / (len(finestra) - 1))  # campionaria n-1
    atteso = (S[t] - m) / sd
    assert abs(z[t] - atteso) < 1e-12, "z_t non e' (S_t - media)/stdev campionaria n-1"
    # warmup dichiarato: 30 (S) + 365 (z) = 395 giorni -> prima z all'indice 394
    assert z[393] is None and z[394] is not None, "warmup z errato (atteso: prima z all'indice 394)"
    assert z[29] is None and z[28] is None, "S definita troppo presto"


def test_z_discriminante_bacata_smascherata():
    """Controprova: la variante con finestra a t+1 E' sensibile al futuro; quella corretta no."""
    S = [100.0 + 1.0 * i + 1.5 * (i % 7) for i in range(800)]
    S2 = list(S)
    for j in range(701, 800):
        S2[j] = S2[j] * 3.0 + 7.0
    z_ok, z_ok2 = e10.serie_z([""] * 800, S), e10.serie_z([""] * 800, S2)
    z_bac, z_bac2 = _z_bacata(S), _z_bacata(S2)
    t = 700  # z_bac[t] finestra = S[337:702] -> include l'indice 701 (perturbato)
    assert z_ok[t] == z_ok2[t], "z corretta cambiata perturbando il futuro"
    assert z_bac[t] != z_bac2[t], "controprova non discriminante: la finestra a t+1 non sente il futuro"


# --- 2. S: finestra a 30 giorni, solo giorni <= t ------------------------------------------

def test_S_solo_giorni_fino_a_t():
    I = [1.0 * i + 0.5 for i in range(500)]
    date = [_giorno(i) for i in range(500)]
    S = e10.serie_S(date, I)
    t = 100
    assert abs(S[t] - math.fsum(I[t - 29:t + 1])) < 1e-12
    assert S[28] is None and S[29] is not None
    I2 = list(I)
    I2[t + 1] *= 9.0
    assert e10.serie_S(date, I2)[t] == S[t], "S_t cambiato perturbando t+1"
    I3 = list(I)
    I3[t] *= 9.0
    assert e10.serie_S(date, I3)[t] != S[t], "S_t non dipende dal giorno t"
    I4 = list(I)
    I4[t - 30] *= 9.0
    assert e10.serie_S(date, I4)[t] == S[t], "S_t dipende da t-30 (finestra troppo larga)"
    I5 = list(I)
    I5[t - 29] *= 9.0
    assert e10.serie_S(date, I5)[t] != S[t], "S_t non dipende dal bordo t-29"


# --- 3. posizione: isteresi e soglie --------------------------------------------------------

def test_pos_isteresi_e_soglie():
    z = [None, 2.0, 0.5, 0.5, -0.5, 1.5, 0.2, -2.0, 1.0, 0.99, 0.0]
    pos = e10.serie_pos([_giorno(i) for i in range(len(z))], z)
    atteso = [0, 1, 1, 1, 0, 1, 1, 0, 1, 1, 0]
    assert pos == atteso, f"isteresi/soglie errate: {pos} != {atteso}"
    # z None mantiene (warmup: resta flat)
    pos2 = e10.serie_pos([""] * 5, [None, None, 0.7, None, None])
    assert pos2 == [0, 0, 0, 0, 0], "z None / 0<z<1 non mantengono lo stato"


def test_I_somma_delta_e_guardia_integrita():
    stbl = {}
    for nome in ("usdt", "usdc", "dai"):
        stbl[nome] = {_giorno(i): 1000.0 + 10.0 * i * {"usdt": 2, "usdc": 1, "dai": 3}[nome]
                      for i in range(20)}
    giorni, I, _ = e10.serie_I(stbl)
    assert giorni[0] == "2019-01-01" and len(giorni) == 20
    # delta del giorno 5: usdt +20, usdc +10, dai +30 -> I=60; giorno 0 (primo punto): 0
    assert abs(I[5] - 60.0) < 1e-9
    assert abs(I[0]) < 1e-9
    # guardia: buco di 2 giorni in un coin -> SystemExit (fail-loud, non silenzioso)
    stbl2 = {k: dict(v) for k, v in stbl.items()}
    del stbl2["dai"][_giorno(7)]
    try:
        e10.serie_I(stbl2)
        raise AssertionError("guardia d'integrita' non scattata su un buco interno")
    except SystemExit:
        pass


# --- 4. end-to-end: ingresso/uscita all'APERTURA del giorno t+1 -----------------------------

def test_e2e_ingressi_agli_open_e_meccaniche_switch():
    n = 900
    barre = _barre_fixture(n)
    stbl, _ = _stbl_fixture(n)
    ris = _pipeline(stbl, barre)
    giorni, z, pos, rec = ris["giorni"], ris["z"], ris["pos"], ris["rec"]
    rec_by_day = {x["giorno"]: x for x in rec}

    # il fixture produce attraversamenti: primo z >= +1 e poi z <= 0
    primi1 = [i for i in range(len(z)) if z[i] is not None and z[i] >= 1.0]
    assert primi1, "fixture non discriminante: nessun z >= +1"
    t_f = primi1[0]
    assert pos[t_f] == 1 and pos[t_f - 1] == 0, "prima entrata non da flat"
    primi0 = [i for i in range(t_f + 1, len(z)) if z[i] is not None and z[i] <= 0.0]
    assert primi0, "fixture non discriminante: nessuna uscita (z <= 0) dopo l'entrata"
    t_x = primi0[0]
    assert pos[t_x] == 0 and pos[t_x - 1] == 1, "uscita non a partire da long"

    # il giorno del segnale T: nessuna posizione attiva (si entra solo dal giorno T+1)
    r_segnale = rec_by_day[giorni[t_f]]
    assert r_segnale["pos"] == 0 and abs(r_segnale["r_lordo"]) < 1e-15, \
        "posizione attiva il giorno del segnale: look-ahead"
    # l'entrata e' all'apertura del giorno T+1: r = c/o - 1 (costo separato)
    i_e = t_f + 1
    rec_e = rec_by_day[giorni[i_e]]
    atteso_e = float(barre[i_e][4]) / float(barre[i_e][1]) - 1.0
    assert rec_e["switch"] and rec_e["pos"] == 1
    assert abs(rec_e["r_lordo"] - atteso_e) < 1e-12, "entrata non all'apertura di t+1"
    assert abs(rec_e["r"] - (atteso_e - e10.COSTO_RT)) < 1e-12, "costo di entrata non applicato"
    # discriminante: entrare alla CHIUSURA del giorno t_f (bug) darebbe r = c/o-1 nel giorno
    # del segnale, oppure 0 nel giorno t_f+1; entrambi != atteso
    assert abs(atteso_e - 0.0) > 1e-6, "fixture non discriminante (apertura=chiusura)"

    # l'uscita e' all'apertura del giorno T_x+1: r = o/cp - 1
    i_u = t_x + 1
    rec_u = rec_by_day[giorni[i_u]]
    atteso_u = float(barre[i_u][1]) / float(barre[i_u - 1][4]) - 1.0
    assert rec_u["switch"] and rec_u["pos"] == 0
    assert abs(rec_u["r_lordo"] - atteso_u) < 1e-12, "uscita non all'apertura di t_x+1"
    assert abs(rec_u["r"] - (atteso_u - e10.COSTO_RT)) < 1e-12
    assert abs(atteso_u - 0.0) > 1e-6, "fixture non discriminante (uscita)"

    # meccanica generale su TUTTI gli switch: entrate da flat, uscite da long, apertura usata
    n_ent = n_usc = 0
    for x in rec:
        if not x["switch"]:
            continue
        g = x["giorno"]
        t = giorni.index(g)  # la barra di etichetta g corrisponde al giorno g; il trigger e' g-1
        zi = z[t - 1]
        if x["pos"] == 1:
            assert zi is not None and zi >= 1.0, f"entrata in {g} non triggerata da z({giorni[t-1]})"
            n_ent += 1
        else:
            assert zi is not None and zi <= 0.0, f"uscita in {g} non triggerata da z({giorni[t-1]})"
            n_usc += 1
    assert n_ent >= 1 and n_usc >= 1, "fixture senza switch completi"


def test_costi_solo_allo_switch():
    n = 900
    ris = _pipeline(_stbl_fixture(n)[0], _barre_fixture(n))
    n_switch = 0
    for x in ris["rec"]:
        if x["switch"]:
            n_switch += 1
            assert abs(x["r"] - (x["r_lordo"] - e10.COSTO_RT)) < 1e-15
            assert abs(x["r_stress"] - (x["r_lordo"] - e10.COSTO_RT * 2.0)) < 1e-15
        else:
            assert x["r"] == x["r_lordo"] and x["r_stress"] == x["r_lordo"], \
                "costo applicato su un giorno senza switch"
    assert n_switch >= 2, "fixture senza switch"


# --- 5. invarianza end-to-end sotto perturbazione del FUTURO (+ controprova) -----------------

def test_e2e_invarianza_futuro_e_discriminante():
    n = 900
    tau = 600  # giorno-segnale di taglio
    barre = _barre_fixture(n)
    stbl, pattern = _stbl_fixture(n)
    ris = _pipeline(stbl, barre)

    # perturba TUTTO il futuro: supply dei giorni > tau e barre dei giorni > tau+1
    stbl2 = _stbl_perturbata(stbl, pattern, tau)
    barre2 = [list(r) for r in barre]
    for i in range(tau + 2, n):
        barre2[i][1] = barre2[i][1] * 1.3
        barre2[i][4] = barre2[i][4] * 1.3
    ris2 = _pipeline(stbl2, barre2)

    # 1) pos(t) per t <= tau: identiche
    for t in range(tau + 1):
        assert ris["pos"][t] == ris2["pos"][t], \
            f"pos({ris['giorni'][t]}) cambiata perturbando il futuro: look-ahead"
    # 2) z(t) per t <= tau: identiche
    for t in range(tau + 1):
        assert ris["z"][t] == ris2["z"][t], f"z({ris['giorni'][t]}) cambiata: look-ahead"
    # 3) r per barre con etichetta <= giorno(tau)+1: identici (prezzi <= barra tau+1 non toccati)
    limite = _giorno(tau + 1)
    visti = 0
    for a, b in zip(ris["rec"], ris2["rec"]):
        if a["giorno"] <= limite:
            visti += 1
            assert a["r"] == b["r"] and a["r_stress"] == b["r_stress"] \
                and a["pos"] == b["pos"] and a["switch"] == b["switch"], \
                f"rendimento {a['giorno']} cambiato perturbando il futuro: look-ahead"
    assert visti > 500

    # controprova (discriminante): la variante BACATA con finestra a t+1 NON e' invariante
    risb = _pipeline(stbl, barre, z_fn=_z_bacata)
    risb2 = _pipeline(stbl2, barre2, z_fn=_z_bacata)
    z_diff = any(a != b for a, b in zip(risb["z"], risb2["z"]) if a is not None and b is not None)
    pos_diff = any(a != b for a, b in zip(risb["pos"], risb2["pos"]))
    assert z_diff, "controprova non discriminante: la finestra a t+1 non sente il futuro"
    assert pos_diff, "controprova non discriminante: nessun flip di posizione sotto perturbazione"


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
