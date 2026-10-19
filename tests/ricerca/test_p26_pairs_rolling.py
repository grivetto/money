"""Test P26 — cointegrazione v2 rolling (regola della catena: PRIMA dei numeri).

Copre i criteri del contratto di consegna della spec:
- EG due passi su serie sintetiche cointegrate NOTE: assert su t_rho e half-life
  ATTESI (formule esplicite nel test, non valori magici); senza implementazione
  i test falliscono (il modulo non esiste -> import fallito).
- Anti-lookahead sulle finestre rolling: le statistiche a t usano solo
  osservazioni <= t (ricalcolo manuale su marker + appendo barre future e
  verifico che le finestre gia' calcolate non cambino).
- Conteggio episodi/rotture su serie sintetiche con attesi ESATTI a mano.
- Screening riproducibile a parita' di dati; zero ordini, zero chiavi, zero
  scritture su exchange (nessun I/O di rete in alcun test).
- Motore end-to-end: un episodio esatto (ingresso close t -> apertura t+1),
  uscita per rientro e per relazione, P&L netto calcolato a mano nel test.

Tutti i dati sono sintetici e DETERMINISTICI (seed fissato o serie esplicite):
nessun test dipende dal mercato o da un caso.
"""
import json
import math

import numpy as np
import pytest

from money.ricerca import p26_pairs_rolling as p26

GIORNO = 86_400_000
TS0 = 1_700_000_000_000  # 2023-11-14T22:13Z (arbitrario, solo per i test)


# ---------- helper: serie sintetiche deterministiche ------------------------------

def _preciso(log_chiusura, log_apertura=None, ts0=TS0):
    n = len(log_chiusura)
    if log_apertura is None:
        log_apertura = log_chiusura  # apertura = chiusura (prezzo piatto intraday)
    return {"ts": (ts0 + np.arange(n) * GIORNO).astype(np.int64),
            "log_apertura": np.asarray(log_apertura, float),
            "log_chiusura": np.asarray(log_chiusura, float)}


def _allineata(la, lb, ts0=TS0):
    """Coppia allineata nel formato del motore: {"ts", "la", "lb", "oa", "ob"}."""
    n = len(la)
    assert len(lb) == n
    ts = (ts0 + np.arange(n) * GIORNO).astype(np.int64)
    return {"ts": ts, "la": np.asarray(la, float), "lb": np.asarray(lb, float),
            "oa": np.asarray(la, float), "ob": np.asarray(lb, float)}


def _trend_e_spread(n, seed, phi, amp=1.0, vol=0.02, rumore=0.01):
    """Gamba B = trend (random walk); gamba A = trend + spread AR(1) con phi.

    phi vicino a 1 → spread lento (stazionario debole, hl alta);
    phi piccolo → spread veloce (hl bassa). Deterministico (seed fissato).
    """
    rng = np.random.default_rng(seed)
    trend = np.cumsum(rng.normal(0.0, vol, n))
    e = np.zeros(n)
    for t in range(1, n):
        e[t] = phi * e[t - 1] + rng.normal(0.0, rumore)
    spread = amp * e
    return trend + spread, trend


def _z_manuale(spread, w=60):
    """Ricalcolo INDIPENDENTE (nel test) della z rolling con ddof=1: il marker
    con cui si confronta la z del modulo. Identico per costruzione alla formula
    della spec: media e sd su [t-w+1, t], solo osservazioni <= t."""
    n = len(spread)
    z = np.zeros(n)
    if n < w:
        return z
    c1 = np.concatenate(([0.0], np.cumsum(spread)))
    c2 = np.concatenate(([0.0], np.cumsum(spread * spread)))
    for t in range(w - 1, n):
        s = c1[t + 1] - c1[t + 1 - w]
        s2 = c2[t + 1] - c2[t + 1 - w]
        m = s / w
        var = (s2 - w * m * m) / (w - 1.0)
        sd = math.sqrt(var) if var > 0 else 0.0
        z[t] = 0.0 if sd < 1e-12 else (spread[t] - m) / sd
    return z


def _scelta(coppia="A/B", beta=1.0, W=120):
    return {"coppia": coppia, "gamba_a": "A", "gamba_b": "B",
            "W": W, "quota_viva": 1.0, "beta": beta}


# ---------- 1. costanti della griglia congelata -----------------------------------

def test_epoch_addestramento_effettivo():
    # 2020-10-01T00:00Z = 18536 giorni dall'epoch (calcolo a mano nel test)
    assert p26.ADDESTRAMENTO_INIZIO_MS == 18536 * 86_400_000
    # 2024-06-01T00:00Z = 19875 giorni dall'epoch (calcolo a mano nel test)
    assert p26.ADDESTRAMENTO_FINE_MS == 19875 * 86_400_000


# ---------- 2. EG: OLS, ADF, half-life su serie sintetiche NOTE --------------------

def test_ols_beta_esatta():
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    y = 2.0 + 3.0 * x
    a, b, r2 = p26.ols_beta(x, y)
    assert abs(a - 2.0) < 1e-9
    assert abs(b - 3.0) < 1e-9
    assert abs(r2 - 1.0) < 1e-9


def test_adf_rho_e_half_life_attesi():
    # e_t = 0.9 * e_{t-1} + eps  →  rho teorico = 0.9 - 1 = -0.1
    # half-life attesa = -ln2 / ln(1 + rho) = -ln2 / ln(0.9)  (formula a mano)
    hl_attesa = -math.log(2.0) / math.log(0.9)
    rng = np.random.default_rng(7)
    e = np.zeros(2000)
    for t in range(1, 2000):
        e[t] = 0.9 * e[t - 1] + rng.normal(0.0, 0.01)
    t_rho, rho = p26.adf_statistica(e)
    hl = p26.half_life_giorni(rho)
    # SE(rho) ≈ sqrt((1-0.9^2)/2000) ≈ 0.0097 → tolleranza 5 sigma sul rho
    assert abs(rho - (-0.1)) < 0.05
    # banda della half-life derivata dalla TOLERANZA sul rho (formula a mano):
    # rho in [-0.15, -0.05] → hl in [-ln2/ln(0.85), -ln2/ln(0.95)]
    hl_lo = -math.log(2.0) / math.log(0.85)
    hl_hi = -math.log(2.0) / math.log(0.95)
    assert hl_lo <= hl <= hl_hi
    assert abs(hl_attesa - 6.578813478960585) < 1e-9   # sanity del calcolo a mano
    # con n=2000 il t e' fortemente significativo
    assert t_rho <= -6.0


def test_eg_finestra_cointegrata_viva():
    # la = 0.5 + 1.3*lb + e, e AR(1) con phi=0.9 (hl ≈ 6.6g, dentro [5,90])
    rng = np.random.default_rng(11)
    lb = np.cumsum(rng.normal(0.0, 0.02, 2000))
    e = np.zeros(2000)
    for t in range(1, 2000):
        e[t] = 0.9 * e[t - 1] + rng.normal(0.0, 0.005)
    la = 0.5 + 1.3 * lb + e
    eg = p26.eg_finestra(la, lb)
    assert eg["viva"] is True
    assert abs(eg["beta"] - 1.3) < 0.08
    assert eg["t_rho"] <= -6.0
    assert 5.0 <= eg["half_life_giorni"] <= 90.0


def test_eg_finestra_non_viva_per_hl_troppo_veloce():
    # phi=0.5 → hl ≈ 1g: il |t| e' enorme ma la relazione e' troppo veloce
    # per lo z-60g: il criterio half-life [5,90] deve ESCLUDERLA.
    rng = np.random.default_rng(13)
    lb = np.cumsum(rng.normal(0.0, 0.02, 2000))
    e = np.zeros(2000)
    for t in range(1, 2000):
        e[t] = 0.5 * e[t - 1] + rng.normal(0.0, 0.01)
    la = lb + e
    eg = p26.eg_finestra(la, lb)
    assert abs(eg["t_rho"]) >= 5.0           # significativo...
    assert eg["half_life_giorni"] < 5.0      # ...ma troppo veloce
    assert eg["viva"] is False


def test_eg_finestra_non_viva_per_random_walk():
    # residui = random walk: nessuna cointegrazione → viva False
    rng = np.random.default_rng(17)
    lb = np.cumsum(rng.normal(0.0, 0.02, 2000))
    e = np.cumsum(rng.normal(0.0, 0.01, 2000))
    la = lb + e
    eg = p26.eg_finestra(la, lb)
    assert eg["viva"] is False


# ---------- 3. finestre rolling: griglia, ancoraggio, anti-lookahead ---------------

def test_finestre_rolling_griglia_ancorata_alla_fine():
    n = 520
    rng = np.random.default_rng(47)
    la = np.cumsum(rng.normal(0.0, 0.02, n))
    lb = np.cumsum(rng.normal(0.0, 0.02, n))
    al = _allineata(la, lb)
    da = TS0
    fino = TS0 + 400 * GIORNO
    finestre = p26.finestre_rolling(al, 120, da, fino)
    # griglia ancorata alla fine: (400 - 120)/5 + 1 = 57 finestre
    assert len(finestre) == 57
    assert finestre[0]["fine_ts"] == da + 120 * GIORNO
    assert finestre[-1]["fine_ts"] == fino
    # serie giornaliere contigue: ogni finestra ha esattamente W osservazioni
    assert all(f["n"] == 120 for f in finestre)
    assert all(f["valida"] for f in finestre)


def test_finestre_rolling_anti_lookahead_e_marker_manuale():
    rng = np.random.default_rng(19)
    n = 520
    la = np.cumsum(rng.normal(0.0, 0.02, n))
    lb = np.cumsum(rng.normal(0.0, 0.02, n))
    al = _allineata(la, lb)
    da = TS0
    fino = TS0 + 400 * GIORNO
    prima = p26.finestre_rolling(al, 120, da, fino)

    # ricalcolo MANUALE della finestra che termina a ``fino`` (indici 280..399):
    # beta OLS a mano: cov(lb, la)/var(lb); poi ADF indipendente sui residui.
    i0, i1 = 280, 400
    lb_w = lb[i0:i1]
    la_w = la[i0:i1]
    mu_b = lb_w.mean()
    mu_a = la_w.mean()
    beta_atteso = float(((lb_w - mu_b) * (la_w - mu_a)).sum()
                        / ((lb_w - mu_b) ** 2).sum())
    alfa_atteso = mu_a - beta_atteso * mu_b
    res = la_w - (alfa_atteso + beta_atteso * lb_w)

    def adf_manuale(y):
        n_y = len(y)
        p = int(math.floor(12.0 * (n_y / 100.0) ** 0.25))
        p = min(max(p, 1), 25)
        dy = np.diff(y)
        r0 = p
        yy = dy[r0:]
        colonne = [np.ones(len(yy)), y[r0:n_y - 1]]
        for i in range(1, p + 1):
            colonne.append(dy[r0 - i:n_y - 1 - i])
        X = np.column_stack(colonne)
        theta, *_ = np.linalg.lstsq(X, yy, rcond=None)
        residui = yy - X @ theta
        dof = len(yy) - X.shape[1]
        cov = (float(residui @ residui) / dof) * np.linalg.inv(X.T @ X)
        se = math.sqrt(max(cov[1, 1], 1e-300))
        return float(theta[1] / se), float(theta[1])

    t_rho_atteso, rho_atteso = adf_manuale(res)
    ultima = prima[-1]
    assert abs(ultima["beta"] - beta_atteso) < 1e-9
    assert abs(ultima["alfa"] - alfa_atteso) < 1e-9
    assert abs(ultima["t_rho"] - t_rho_atteso) < 1e-9
    assert abs(ultima["rho"] - rho_atteso) < 1e-9

    # appendo 10 barre FUTURE (oltre ``fino``): le finestre gia' calcolate
    # (che finiscono <= fino) non devono cambiare in nessun campo.
    al2 = _allineata(
        np.concatenate([la, rng.normal(0.0, 0.02, 10)]),
        np.concatenate([lb, rng.normal(0.0, 0.02, 10)]))
    dopo = p26.finestre_rolling(al2, 120, da, fino)
    assert json.dumps(prima, sort_keys=True) == json.dumps(dopo, sort_keys=True)


def test_serie_relazione_anti_lookahead():
    # ricalcolo giornaliero della relazione: il valore a i non deve cambiare
    # quando arrivano barre future.
    n = 520
    rng = np.random.default_rng(23)
    lb = np.cumsum(rng.normal(0.0, 0.02, n))
    e = np.zeros(n)
    for t in range(1, n):
        e[t] = 0.9 * e[t - 1] + rng.normal(0.0, 0.005)
    la = lb + e
    al = _allineata(la, lb)
    rel_prima = p26.serie_relazione(al, 120)
    al2 = _allineata(
        np.concatenate([la, la[-10:]]),
        np.concatenate([lb, lb[-10:]]))
    rel_dopo = p26.serie_relazione(al2, 120)
    assert np.array_equal(rel_prima, rel_dopo[:n])


# ---------- 4. screening: struttura e riproducibilita' ------------------------------

def test_screening_rolling_riproducibile():
    rng = np.random.default_rng(29)
    n = 320
    preci = {}
    base = np.cumsum(rng.normal(0.0, 0.02, n))
    for s in ["A", "B", "C", "D"]:
        rng2 = np.random.default_rng({"A": 31, "B": 37, "C": 41, "D": 43}[s])
        preci[s] = _preciso(base + np.cumsum(rng2.normal(0.0, 0.01, n)))
    da = TS0
    fino = TS0 + 300 * GIORNO
    primo = p26.screening_rolling(preci, ["A", "B", "C", "D"], da, fino)
    secondo = p26.screening_rolling(preci, ["A", "B", "C", "D"], da, fino)
    assert json.dumps(primo, sort_keys=True) == json.dumps(secondo, sort_keys=True)
    # struttura: C(4,2) = 6 coppie x 2 W = 12 righe; ogni coppia esattamente 2 W
    coppie = sorted({r["coppia"] for r in primo})
    assert len(coppie) == 6
    for c in coppie:
        righe = [r for r in primo if r["coppia"] == c]
        assert sorted(r["W"] for r in righe) == [120, 180]
    for r in primo:
        assert 0.0 <= r["quota_viva"] <= 1.0
        assert isinstance(r["pass"], bool)
        assert r["n_valide"] <= r["n_finestre"]


def test_eleggibilita_selezione_esatta():
    def riga(coppia, W, quota, ultima):
        parti = coppia.split("/")
        gamba_a = parti[0]
        gamba_b = parti[1] if len(parti) > 1 else coppia
        return {"coppia": coppia, "gamba_a": gamba_a,
                "gamba_b": gamba_b, "W": W, "quota_viva": quota,
                "ultima_viva": ultima, "n_vive": 0, "n_valide": 100,
                "n_finestre": 100, "beta_ultima": 1.0, "alfa_ultima": 0.0,
                "t_rho_ultima": -5.0, "half_life_ultima": 10.0,
                "pass": quota >= 0.60 and ultima}

    risultati = [
        # P1: W*=120 (quota 0.70 > 0.50) → passa, terza per quota
        riga("P1", 120, 0.70, True), riga("P1", 180, 0.50, True),
        # P2: passa solo su W=180 → prima (quota 0.80)
        riga("P2", 120, 0.55, False), riga("P2", 180, 0.80, True),
        # P3: W*=180 (W=120 non e' viva nell'ultima) → passa, seconda (0.65)
        riga("P3", 120, 0.65, False), riga("P3", 180, 0.65, True),
        # P4: quota altissima ma ultima NON viva su entrambe → NON passa
        riga("P4", 120, 0.90, False), riga("P4", 180, 0.85, False),
        # P5: quota sotto il 60% → NON passa
        riga("P5", 120, 0.59, True), riga("P5", 180, 0.59, True),
        # P6: passa (0.61) ma resta fuori dal cap 3
        riga("P6", 120, 0.61, True), riga("P6", 180, 0.61, True),
    ]
    scelte = p26.eleggibilita(risultati)
    assert [(r["coppia"], r["W"]) for r in scelte] == [
        ("P2", 180), ("P1", 120), ("P3", 180)]
    assert all(r["beta"] == 1.0 for r in scelte)


# ---------- 5. rotture: classificazione esatta --------------------------------------

def test_classifica_rotture_esatta():
    n = 120
    z = np.full(n, 2.0)          # |z| > 0.5 ovunque di default
    # stop a i=10: rientro (|z|<=0.5) a i=12, entro 30 giorni → NON rotta
    z[12] = 0.0
    # stop a i=50: nessun rientro per 40 giorni → ROTTA
    # stop a i=90: rientro a i=119 (29 giorni dopo) → NON rotta
    z[119] = 0.0
    ts = (TS0 + np.arange(n) * GIORNO).astype(np.int64)
    per_coppia = {"A/B": {"z": z, "d": {"ts": ts}}}
    stops = [("A/B", 10), ("A/B", 50), ("A/B", 90)]
    ops = [
        p26.Operazione(coppia="A/B", lato="short_spread", ts_ingresso=ts[9],
                       ts_uscita=ts[10], z_ingresso=4.5, z_uscita=4.5,
                       motivo_uscita="stop", nozionale=250.0,
                       pnp_lordo=0.0, pnp_netto=-0.75),
        p26.Operazione(coppia="A/B", lato="short_spread", ts_ingresso=ts[49],
                       ts_uscita=ts[50], z_ingresso=4.5, z_uscita=4.5,
                       motivo_uscita="stop", nozionale=250.0,
                       pnp_lordo=0.0, pnp_netto=-0.75),
        p26.Operazione(coppia="A/B", lato="short_spread", ts_ingresso=ts[89],
                       ts_uscita=ts[90], z_ingresso=4.5, z_uscita=4.5,
                       motivo_uscita="stop", nozionale=250.0,
                       pnp_lordo=0.0, pnp_netto=-0.75),
        p26.Operazione(coppia="A/B", lato="long_spread", ts_ingresso=ts[0],
                       ts_uscita=ts[5], z_ingresso=-2.5, z_uscita=-0.4,
                       motivo_uscita="rientro", nozionale=250.0,
                       pnp_lordo=1.0, pnp_netto=0.25),
    ]
    out = p26.classifica_rotture(per_coppia, stops, ops)
    rotture = [o.rotture for o in out if o.motivo_uscita == "stop"]
    assert rotture == [False, True, False]
    # le operazioni non-stop non vengono mai marcate
    assert all(o.rotture is False for o in out if o.motivo_uscita != "stop")


# ---------- 6. motore end-to-end: sequenza di episodi ESATTA (a mano) ----------------

def _ops_manuali(z, al, beta, n_giorni, capitale=1000.0, costo=p26.CICLO_COSTO,
                 rel=None):
    """Replica INDIPENDENTE del motore (una coppia, nessun funding): ricalcola a
    mano la sequenza attesa di operazioni dalla z sui primi ``n_giorni`` giorni.
    Esecuzione all'apertura t+1 della decisione al close t; uscite prima degli
    ingressi; fine serie alla chiusura dell'ultima barra. Ritorna
    (ops, cassa_finale, ddport)."""
    n = n_giorni
    la, lb, oa, ob = al["la"], al["lb"], al["oa"], al["ob"]
    ops = []
    cassa = capitale
    aperta = None
    programma = None  # (azione, z_dec, motivo) decisa al close k-1
    picco = capitale
    dd = 0.0
    equity_close_prev = capitale
    for k in range(n):
        # 1) esecuzione all'apertura k
        if programma is not None and programma[0] == "exit" and aperta is not None:
            sp_out = oa[k] - beta * ob[k]
            lordo = aperta["segno"] * aperta["noz"] / 2.0 * (sp_out - aperta["sp_ing"])
            netto = lordo - costo * aperta["noz"]
            cassa += aperta["noz"] + netto
            ops.append(dict(lato=aperta["lato"], segno=aperta["segno"],
                            z_ing=aperta["z_ing"], z_out=programma[1],
                            motivo=programma[2], k_ing=aperta["k_ing"], k_out=k,
                            noz=aperta["noz"], lordo=lordo, netto=netto))
            aperta = None
        if programma is not None and programma[0] == "entry" and aperta is None:
            if abs(programma[1]) >= p26.Z_IN:
                noz = p26.ALLOCAZIONE * equity_close_prev
                if noz > 0 and cassa >= noz:
                    cassa -= noz
                    segno = 1.0 if programma[1] < 0 else -1.0
                    aperta = dict(lato=("long_spread" if segno > 0 else "short_spread"),
                                  segno=segno, noz=noz, z_ing=programma[1], k_ing=k,
                                  sp_ing=oa[k] - beta * ob[k])
        programma = None
        # 2) MTM al close k
        mtm = 0.0
        if aperta is not None:
            sp = la[k] - beta * lb[k]
            mtm = aperta["noz"] + aperta["segno"] * aperta["noz"] / 2.0 * (sp - aperta["sp_ing"])
        equity = cassa + mtm
        picco = max(picco, equity)
        if picco > 0:
            dd = max(dd, 1.0 - equity / picco)
        # 3) funding assente nei test
        # 4) decisioni al close k per l'apertura k+1
        if k + 1 < n:
            zt = z[k]
            if aperta is not None:
                if abs(zt) <= p26.Z_OUT:
                    programma = ("exit", zt, "rientro")
                elif abs(zt) >= p26.Z_STOP:
                    programma = ("exit", zt, "stop")
                elif rel is not None and not bool(rel[k]):
                    programma = ("exit", zt, "relazione")
            elif abs(zt) >= p26.Z_IN:
                programma = ("entry", zt, "")
        equity_close_prev = equity
    # fine serie: chiusura all'ultima chiusura
    if aperta is not None:
        k = n - 1
        sp_ult = la[k] - beta * lb[k]
        lordo = aperta["segno"] * aperta["noz"] / 2.0 * (sp_ult - aperta["sp_ing"])
        netto = lordo - costo * aperta["noz"]
        cassa += aperta["noz"] + netto
        ops.append(dict(lato=aperta["lato"], segno=aperta["segno"],
                        z_ing=aperta["z_ing"], z_out=z[k],
                        motivo="fine_serie", k_ing=aperta["k_ing"], k_out=k,
                        noz=aperta["noz"], lordo=lordo, netto=netto))
    return ops, cassa, dd


def _scenario_ar1(n=400, amp=5.0, seed=41):
    """Spread AR(1) STAZIONARIO (phi=0.9, media 0): z supera 2 in piu'
    escursioni senza mai toccare il 4 (nessuno stop), ogni ciclo chiude al
    rientro vicino alla media (cassa mai sotto il nozionale: zero saltate).
    Il test ricalcola la sequenza attesa A MANO e confronta il motore."""
    rng = np.random.default_rng(seed)
    lb = np.zeros(n)
    la = np.zeros(n)
    for t in range(1, n):
        la[t] = 0.9 * la[t - 1] + rng.normal(0.0, 0.02)
    return _allineata(la, lb)


def _confronta_motore(al, beta, giorni, relazione=None, costo=p26.CICLO_COSTO,
                      capitale=1000.0):
    """Esegue il motore e lo confronta campo per campo con la replica manuale."""
    spread = al["la"] - beta * al["lb"]
    z = _z_manuale(spread)
    assert np.allclose(p26.z_seriesi(spread), z, atol=1e-12), "z del modulo != manuale"
    rel = relazione["A/B"] if relazione else None
    ops_attesi, cassa_attesa, dd_atteso = _ops_manuali(
        z, al, beta, len(giorni), capitale, costo, rel)
    scelte = [_scelta(coppia="A/B", beta=beta)]
    res = p26.simula_portafoglio(scelte, {"A/B": al}, giorni,
                                 capitale=capitale,
                                 relazione=relazione, costo=costo)
    assert res["n"] == len(ops_attesi)
    assert res["saltate"] == 0
    for op, att in zip(res["ops"], ops_attesi):
        assert op.motivo_uscita == att["motivo"]
        assert op.lato == att["lato"]
        assert op.ts_ingresso == int(al["ts"][att["k_ing"]])
        assert op.ts_uscita == int(al["ts"][att["k_out"]])
        assert abs(op.z_ingresso - att["z_ing"]) < 1e-12
        assert abs(op.z_uscita - att["z_out"]) < 1e-12
        assert abs(op.nozionale - att["noz"]) < 1e-9
        assert abs(op.pnp_lordo - att["lordo"]) < 1e-9
        assert abs(op.pnp_netto - att["netto"]) < 1e-9
    assert abs(res["capitale_finale"] - cassa_attesa) < 1e-9
    assert abs(res["ddport"] - dd_atteso) < 1e-9
    return res


def test_engine_sequenza_esatta_e_pnl_manuale():
    al = _scenario_ar1(n=400)
    giorni = al["ts"]
    res = _confronta_motore(al, beta=1.0, giorni=giorni)
    # la serie sinusoidale genera piu' episodi, tutti a chiusura del rientro:
    # nessuno stop (max |z| < 4) e piu' di un episodio (la z supera 2 piu' volte)
    assert res["n"] >= 3
    assert all(o.motivo_uscita in ("rientro", "fine_serie") for o in res["ops"])
    # determinismo: due run identici
    scelte = [_scelta(coppia="A/B", beta=1.0)]
    res2 = p26.simula_portafoglio(scelte, {"A/B": al}, giorni, capitale=1000.0)
    assert json.dumps([o.__dict__ for o in res["ops"]], sort_keys=True) == \
        json.dumps([o.__dict__ for o in res2["ops"]], sort_keys=True)


def test_engine_uscita_relazione_esatta():
    n = 400
    al = _scenario_ar1(n=n)
    spread = al["la"] - 1.0 * al["lb"]
    z = _z_manuale(spread)
    entry = next(k for k in range(60, n - 2) if abs(z[k]) >= p26.Z_IN)
    # giorno del ricalcolo: prima chiusura a posizione aperta con 0.5 < |z| < 4
    # (il test garantisce che prima di quel giorno non ci siano uscite naturali)
    rel_day = entry + 1
    while rel_day < n - 2 and not (p26.Z_OUT < abs(z[rel_day]) < p26.Z_STOP):
        assert abs(z[rel_day]) > p26.Z_OUT, "scenario rotto: uscita naturale prima"
        assert abs(z[rel_day]) < p26.Z_STOP, "scenario rotto: stop prima"
        rel_day += 1
    assert p26.Z_OUT < abs(z[rel_day]) < p26.Z_STOP
    # tronco la serie subito dopo l'esecuzione dell'uscita: niente decisioni dopo
    giorni = al["ts"][:rel_day + 2]
    rel = np.ones(len(al["ts"]), dtype=bool)
    rel[rel_day] = False
    relazione = {"A/B": rel}
    res = _confronta_motore(al, beta=1.0, giorni=giorni, relazione=relazione)
    assert res["n"] == 1
    op = res["ops"][0]
    assert op.motivo_uscita == "relazione"
    assert op.ts_uscita == int(al["ts"][rel_day + 1])
    # ingresso e uscita allo stesso prezzo possibile → lordo determinato dalla
    # replica manuale; qui il controllo e' gia' in _confronta_motore (P&L esatto)


# ---------- 7. verdetto: esiti ammessi e scenario stress ----------------------------

def test_valuta_verifica_insufficiente_per_n_e_stress():
    al = _scenario_ar1(n=400)
    scelte = [_scelta(coppia="A/B", beta=1.0)]
    giorni = al["ts"]
    v = p26.valuta_verifica(scelte, {"A/B": al}, giorni, capitale=1000.0)
    # il numero di operazioni coincide con la replica manuale
    spread = al["la"] - 1.0 * al["lb"]
    ops_attesi, _, _ = _ops_manuali(_z_manuale(spread), al, 1.0, len(giorni), 1000.0)
    assert v["n"] == len(ops_attesi)
    # n < 30 → "insufficiente", mai "candidata_su_evidenza"
    assert v["esito"] == "insufficiente"
    assert not v["criteri"]["n_ok"]
    assert any("n=" in m for m in v["motivi"])
    # scenario stress riportato sempre, con il costo dichiarato e atteso a mano
    assert v["stress"]["costo"] == p26.COSTO_STRESS
    assert v["stress"]["n"] == len(ops_attesi)
    expi_stress_attesi = [(o["lordo"] - p26.COSTO_STRESS * o["noz"]) / o["noz"]
                          for o in ops_attesi]
    attesa_stress = float(np.mean(expi_stress_attesi))
    assert abs(v["stress"]["expectancy_netta"] - attesa_stress) < 1e-12
    # criterio 8 riportato con n_blocchi = min(3, n)
    assert v["criterio8"] is not None
    assert v["criterio8"]["n_blocchi"] == min(3, len(ops_attesi))


def test_criterio8_dipende_da_un_solo_blocco():
    # tutto il rendimento nel primo blocco: togliendolo l'expectancy <= 0
    ritorni = [0.10] * 10 + [-0.001] * 20
    c8 = p26.criterio8_serie(ritorni, n_blocchi=3)
    assert c8["dipende_da_un_solo_blocco"] is True
    assert abs(c8["expectancy_senza_migliore"] - (-0.001)) < 1e-12
    # edge distribuito: togliendo il blocco migliore resta positiva
    ritorni2 = [0.01] * 30
    c8b = p26.criterio8_serie(ritorni2, n_blocchi=3)
    assert c8b["dipende_da_un_solo_blocco"] is False
    # serie vuota → criterio non applicabile
    assert p26.criterio8_serie([]) is None


# ---------- 8. dati: caricamento cache e funding (offline, file temporanei) ---------

def test_carica_usdt_lungo_cache_temporaneo(tmp_path):
    cache = str(tmp_path)
    n = 300
    for s in ["AAA", "BBB"]:
        barre = [[TS0 + i * GIORNO, 10.0 + i * 0.1, 10.0, 9.0, 10.5 + i * 0.1, 100.0]
                 for i in range(n)]
        with open(f"{cache}/okx_eea_{s}-USDT_1d.json", "w") as f:
            json.dump({"barre": barre}, f)
    prezzi = p26.carica_usdt_lungo(cache, ["AAA", "BBB"])
    assert set(prezzi) == {"AAA", "BBB"}
    assert len(prezzi["AAA"]["ts"]) == n
    assert abs(prezzi["AAA"]["log_chiusura"][0] - math.log(10.5)) < 1e-12
    with pytest.raises(FileNotFoundError):
        p26.carica_usdt_lungo(cache, ["CCC"])


def test_carica_funding_dedup_prima_riga(tmp_path):
    p = tmp_path / "funding_xperp.jsonl"
    p.write_text("\n".join([
        json.dumps({"simbolo": "BTC/USD:USD-310404", "ts": TS0, "funding": 0.0001}),
        json.dumps({"simbolo": "BTC/USD:USD-310404", "ts": TS0, "funding": 0.0002}),
        json.dumps({"simbolo": "BTC/USD:USD-310404", "ts": TS0 + GIORNO,
                    "funding": 0.0003}),
        json.dumps({"simbolo": "ETH/USD:USD-310404", "ts": TS0, "funding": 0.0004}),
    ]) + "\n")
    fondi = p26.carica_funding(str(p))
    assert fondi["BTC"][TS0] == 0.0001          # prima riga vince (deterministico)
    assert fondi["BTC"][TS0 + GIORNO] == 0.0003
    assert fondi["ETH"][TS0] == 0.0004
    assert p26.carica_funding(str(tmp_path / "assente.jsonl")) == {}
