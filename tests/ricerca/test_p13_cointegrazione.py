"""Test P13 — cointegrazione pairs (regola della catena: PRIMA dei numeri).

Copre: anti-lookahead (z e decisioni non vedono il futuro), aritmetica del
percorso del denaro (sizing, P&L due gambe, costi), ADF/OLS/half-life,
screening con dati sintetici, vincolo di cassa, rotture, determinismo,
cancello (n<30, tutte-escluse, ddport) e caricamento funding.

Tutti i dati sono sintetici e DETERMINISTICI (seed fissato o serie esplicite):
nessun test dipende dal mercato o da un caso.
"""
import json

import numpy as np
import pytest

from money.ricerca import p13_cointegrazione as p13

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


def _coppia_precis(la, lb, ts0=TS0):
    """Una coppia di gambe allineate: la (gamba_a), lb (gamba_b)."""
    n = len(la)
    assert len(lb) == n
    return {
        "A": _preciso(la, ts0=ts0),
        "B": _preciso(lb, ts0=ts0),
    }


def _trend_e_spread(n, seed, phi, amp, drift=0.001, vol=0.02):
    """Gamba B = trend (random walk); gamba A = trend + spread AR(1) con phi.

    phi vicino a 1 → spread lento (stazionario debole, hl alta);
    phi piccolo → spread veloce (hl bassa). Deterministico (seed fissato).
    """
    rng = np.random.default_rng(seed)
    trend = drift * np.arange(n) + np.cumsum(rng.normal(0.0, vol, n))
    e = np.zeros(n)
    for t in range(1, n):
        e[t] = phi * e[t - 1] + rng.normal(0.0, 0.01)
    spread = amp * e
    return trend + spread, trend


def _scelta(coppia="A/B", beta=1.0, t_rho=-8.0, hl=6.0):
    return {"coppia": coppia, "gamba_a": "A", "gamba_b": "B",
            "beta": beta, "t_rho": t_rho, "half_life_giorni": hl,
            "r2": 0.9, "n": 400, "rho": -0.1,
            "beta_f1": 1.0, "beta_f2": 1.0, "delta_beta_rel": 0.01,
            "pass_t": True, "pass_hl": True, "pass_stab": True, "pass": True}


def _allineate(precis, scelta):
    return {scelta["coppia"]: p13.allinea(precis, scelta)}


def _giorni(precis, scelta, da=None, fino=None):
    d = p13.allinea(precis, scelta)
    ts = d["ts"]
    if da is not None:
        ts = ts[ts >= da]
    if fino is not None:
        ts = ts[ts < fino]
    return ts


# ---------- z_seriesi: anti-lookahead ---------------------------------------------

def test_z_anti_lookahead_il_futuro_non_cambia_il_passato():
    rng = np.random.default_rng(7)
    spread = np.cumsum(rng.normal(0, 0.01, 200))
    z = p13.z_seriesi(spread, 60)
    fut = spread.copy()
    fut[100:] += 50.0  # rompo tutto il futuro
    z2 = p13.z_seriesi(fut, 60)
    assert np.allclose(z[:100], z2[:100]), "z(t) non puo' dipendere da t+1, t+2, ..."
    # il futuro cambia solo il futuro
    assert not np.allclose(z[100:], z2[100:])


def test_z_prima_finestra_zero_e_sd_nullo_zero():
    flat = np.zeros(100)
    z = p13.z_seriesi(flat, 60)
    assert np.allclose(z[:59], 0.0), "meno di 60 osservazioni: nessun segnale"
    assert np.allclose(z[59:], 0.0), "sd=0 (spread piatto): nessun segnale, mai inventato"


def test_z_formula_finestra():
    # spread con un solo valore diverso nella finestra: z noto dalla formula
    spread = np.zeros(80)
    spread[59] = 1.0  # l'ultimo elemento della prima finestra completa [0..59]
    z = p13.z_seriesi(spread, 60)
    for t in (59, 60):
        i0 = t - 60 + 1
        finestra = spread[i0:t + 1]
        media = finestra.mean()
        sd = finestra.std(ddof=1)
        assert abs(z[t] - (spread[t] - media) / sd) < 1e-9, \
            f"z({t}) deve valere (x-media)/sd con varianza di campionamento"
    # z[60]: finestra [1..60] contiene ancora lo spike a 59 → NON zero
    assert z[60] < 0.0, "lo spike resta in finestra: z negativo (sotto media)"


# ---------- OLS / ADF / half-life ---------------------------------------------------

def test_ols_esatta():
    x = np.arange(100, dtype=float)
    y = 2.0 + 0.5 * x
    a, b, r2 = p13.ols_beta(x, y)
    assert abs(a - 2.0) < 1e-9 and abs(b - 0.5) < 1e-9 and r2 > 1 - 1e-9


def test_adf_bianco_rossore_non_stazionario():
    rng = np.random.default_rng(11)
    x = np.cumsum(rng.normal(0, 1, 800))  # random walk
    t_rho, rho = p13.adf_statistica(x)
    assert abs(t_rho) < p13.SOGLIA_T_ROHOGA, \
        "un random walk non deve superare la soglia EG di stazionarieta'"


def test_adf_ar1_veloce_stazionario():
    rng = np.random.default_rng(12)
    n = 800
    x = np.zeros(n)
    for t in range(1, n):
        x[t] = 0.5 * x[t - 1] + rng.normal(0, 1)  # AR(1) phi=0.5
    t_rho, rho = p13.adf_statistica(x)
    assert abs(t_rho) > p13.SOGLIA_T_ROHOGA, "AR(1) veloce: oltre la soglia EG"
    assert rho < -0.3, "coefficiente ADF negativo"


def test_half_life():
    # rho_adf = phi - 1; phi=0.9 → rho=-0.1 → hl = ln2/ln(1.1) ≈ 6.58g
    hl = p13.half_life_giorni(-0.1)
    assert abs(hl - np.log(2) / -np.log(0.9)) < 1e-9
    assert p13.half_life_giorni(0.0) is None   # rho=0 → no convergenza
    assert p13.half_life_giorni(-1.5) is None  # base fuori (0,1)


def test_adf_deterministico():
    rng = np.random.default_rng(99)
    x = np.zeros(300)
    for t in range(1, 300):
        x[t] = 0.8 * x[t - 1] + rng.normal(0, 0.5)
    a = p13.adf_statistica(x)
    b = p13.adf_statistica(x)
    assert a == b, "stesso input, stessi numeri"


# ---------- screening ----------------------------------------------------------------

def test_screening_cointegrata_passa_indipendente_no():
    n = 700
    la, lb = _trend_e_spread(n, seed=42, phi=0.9, amp=1.0)   # spread AR(1) lento
    precis = _coppia_precis(la, lb)
    res = p13.screening_coppie(precis, da=TS0, fino=TS0 + n * GIORNO)
    assert len(res) == 1
    r = res[0]
    assert r["pass_t"], "cointegrata: |t_rho| deve superare la soglia"
    assert r["pass"], "coppia cointegrata con hl in [3,30] deve passare"

    # gamba B indipendente da A (nessuna relazione) → deve fallire
    rng = np.random.default_rng(5)
    b_ind = 3.0 + np.cumsum(rng.normal(0.001, 0.02, n))
    res2 = p13.screening_coppie(_coppia_precis(la, b_ind),
                                da=TS0, fino=TS0 + n * GIORNO)
    assert not res2[0]["pass"], "coppia indipendente non puo' passare l'EG"


def test_screening_stabilita_beta_rifiuta_beta_mobile():
    # beta diverso nelle due metà: prima A = B + e1, poi A = 2*B + e2
    n = 800
    rng = np.random.default_rng(21)
    trend = np.cumsum(rng.normal(0.001, 0.02, n))
    e = np.zeros(n)
    for t in range(1, n):
        e[t] = 0.9 * e[t - 1] + rng.normal(0, 0.01)
    la = np.concatenate([trend[:400] + e[:400], 2.0 * trend[400:] + e[400:]])
    lb = trend
    res = p13.screening_coppie(_coppia_precis(la, lb),
                               da=TS0, fino=TS0 + n * GIORNO)
    assert res[0]["delta_beta_rel"] > 0.30, "beta 1 → 2 deve essere rilevato"
    assert not res[0]["pass_stab"]
    assert not res[0]["pass"]


def test_seleziona_cap_e_ordine_deterministico():
    base = _scelta()
    r = []
    for i, c in enumerate(["A/B", "C/D", "E/F", "G/H", "I/J"]):
        r.append({**base, "coppia": c, "t_rho": -(5.0 - i * 0.1)})
    scelte = p13.seleziona(r)
    assert len(scelte) == p13.MASIMO_COPIE
    assert [s["coppia"] for s in scelte] == ["A/B", "C/D", "E/F"]
    # parita' di |t_rho|: vince l'ordine lessicografico
    r2 = [{**base, "coppia": "Z/Z", "t_rho": 4.0}, {**base, "coppia": "A/B", "t_rho": -4.0}]
    assert [s["coppia"] for s in p13.seleziona(r2)][0] == "A/B"


# ---------- motore: anti-lookahead e aritmetica del denaro ---------------------------

def test_engine_anti_lookahead_il_futuro_non_cambia_le_decisioni():
    n = 400
    la, lb = _trend_e_spread(n, seed=3, phi=0.5, amp=1.5)
    precis = _coppia_precis(la, lb)
    s = _scelta()
    allin = _allineate(precis, s)
    giorni = _giorni(precis, s)
    base = p13.simula_portafoglio([s], allin, giorni, capitale=1000.0)

    # rompo l'ULTIMA barra: le decisioni fino a penultimo close non possono cambiare
    la2, lb2 = la.copy(), lb.copy()
    la2[-1] += 0.5
    precis2 = _coppia_precis(la2, lb2)
    allin2 = _allineate(precis2, s)
    mod = p13.simula_portafoglio([s], allin2, giorni, capitale=1000.0)
    assert len(base["ops"]) == len(mod["ops"])
    for o1, o2 in zip(base["ops"], mod["ops"]):
        assert o1.ts_ingresso == o2.ts_ingresso
        assert o1.lato == o2.lato
        assert abs(o1.z_ingresso - o2.z_ingresso) < 1e-12


def test_engine_aritmetica_due_gambe_costi_e_sizing():
    # costruzione a mano (pulita, senza rumore): spread -0.05 per 20 barre da t=100
    n = 300
    trend = 3.0 + 0.001 * np.arange(n)
    spread = np.zeros(n)
    spread[100:120] = -0.05
    la = trend + spread
    s = _scelta(beta=1.0)
    precis = _coppia_precis(la, trend)
    allin = _allineate(precis, s)
    giorni = _giorni(precis, s)
    res = p13.simula_portafoglio([s], allin, giorni, capitale=1000.0)
    assert len(res["ops"]) >= 1, "il calo deve generare almeno un ingresso"
    o = res["ops"][0]
    # sizing: equity al momento della decisione = 1000 (nessuna posizione)
    assert abs(o.nozionale - p13.ALLOCAZIONE * 1000.0) < 1e-9
    # esecuzione: decisione allo close di 100 → ingresso all'APERTURA di 101
    assert o.lato == "long_spread", "calo dello spread (z<0) → long spread"
    assert o.ts_ingresso == TS0 + 101 * GIORNO, "esecuzione t+1 all'apertura"
    # P&L: segno(long_spread=+1) * noz/2 * (sp_out - sp_ing), prezzi di APERTURA
    d = allin["A/B"]
    i_ing = int(np.searchsorted(d["ts"], o.ts_ingresso))
    i_out = int(np.searchsorted(d["ts"], o.ts_uscita))
    sp_ing = d["oa"][i_ing] - d["lb"][i_ing]
    sp_out = d["oa"][i_out] - d["lb"][i_out]
    assert abs(o.pnp_lordo - 1.0 * o.nozionale / 2.0 * (sp_out - sp_ing)) < 1e-9
    assert abs(o.pnp_netto - (o.pnp_lordo - p13.CICLO_COSTO * o.nozionale)) < 1e-9


def test_engine_nessuna_posizione_prima_finestra_e_vincolo_cassa():
    n = 100
    la, lb = _trend_e_spread(n, seed=5, phi=0.5, amp=2.0)
    precis = _coppia_precis(la, lb)
    s = _scelta()
    allin = _allineate(precis, s)
    giorni = _giorni(precis, s)
    res = p13.simula_portafoglio([s], allin, giorni, capitale=1000.0)
    for o in res["ops"]:
        assert o.ts_ingresso >= TS0 + (p13.Z_MEDIA_GIORNI) * GIORNO, \
            "nessun ingresso prima di 60 osservazioni"
    # vincolo di cassa: con ALLOCAZIONE temporaneamente alta, il secondo ingresso salta
    vecchio = p13.ALLOCAZIONE
    p13.ALLOCAZIONE = 0.6
    try:
        s2 = _scelta(coppia="A/B")
        # due "coppie" identiche non si possono sovrapporre (chiave); uso 1 coppia e
        # verifico che la cassa non vada MAI negativa nella curva
        res2 = p13.simula_portafoglio([s2], allin, giorni, capitale=100.0)
        assert all(eq >= 0.0 for _, eq in res2["curva"]), "la cassa non puo' andare negativa"
        assert res2["capitale_finale"] > 0.0
    finally:
        p13.ALLOCAZIONE = vecchio


def test_engine_ingresso_salto_cassa():
    n = 300
    la, lb = _trend_e_spread(n, seed=6, phi=0.6, amp=1.5)
    precis = _coppia_precis(la, lb)
    s = _scelta()
    allin = _allineate(precis, s)
    giorni = _giorni(precis, s)
    vecchio = p13.ALLOCAZIONE
    p13.ALLOCAZIONE = 0.9  # quasi tutto il capitale per posizione
    try:
        res = p13.simula_portafoglio([s], allin, giorni, capitale=100.0)
    finally:
        p13.ALLOCAZIONE = vecchio
    # con 0.9 di alloc, dopo il primo ingresso resta 10; un secondo ingresso (0.9*equity)
    # non ha cassa → saltate (la stessa coppia non rientra finche' aperta, quindi il
    # conto resta coerente: nessuna operazione senza cassa)
    assert res["capitale_finale"] > 0.0
    assert all(eq >= 0.0 for _, eq in res["curva"])


def test_engine_determinismo():
    n = 400
    la, lb = _trend_e_spread(n, seed=8, phi=0.7, amp=1.2)
    precis = _coppia_precis(la, lb)
    s = _scelta()
    allin = _allineate(precis, s)
    giorni = _giorni(precis, s)
    r1 = p13.simula_portafoglio([s], allin, giorni, capitale=1000.0)
    r2 = p13.simula_portafoglio([s], allin, giorni, capitale=1000.0)
    assert r1["capitale_finale"] == r2["capitale_finale"]
    assert len(r1["ops"]) == len(r2["ops"])
    for a, b in zip(r1["ops"], r2["ops"]):
        assert a == b, "stessi input, stessi numeri"


def test_engine_funding_differenziale():
    # 120 barre di spread che scende a 100 e resta: una posizione aperta
    n = 150
    trend = 3.0 + 0.001 * np.arange(n)
    spread = np.zeros(n)
    spread[100:130] = -2.0  # calo che resta → posizione long aperta piu' giorni
    la = trend + spread
    s = _scelta(beta=1.0)
    precis = _coppia_precis(la, trend)
    allin = _allineate(precis, s)
    giorni = _giorni(precis, s)
    # funding: A paga 0.01% al giorno, B paga 0.001% → per long_spread (long A, short B):
    # diff = fb - fa = -0.00009 → il funding fa perdere (A e' la gamba costosa)
    fondi = {"A": {int(t): 0.0001 for t in giorni},
             "B": {int(t): 0.00001 for t in giorni}}
    senza = p13.simula_portafoglio([s], allin, giorni, capitale=1000.0)
    con = p13.simula_portafoglio([s], allin, giorni, capitale=1000.0,
                                 funding_per_giorno=fondi)
    assert con["funding_totale"] < 0.0, "funding A > funding B su long A: flusso negativo"
    assert con["capitale_finale"] < senza["capitale_finale"]


# ---------- rotture --------------------------------------------------------------------

def test_engine_rottura_stop_senza_rientro():
    # step che resta alto: entry (z>2), stop immediato (z>=4), poi z decade lentamente
    # e NON rientra in |z|<=0.5 entro 30 giorni → rottura
    n = 200
    spread = np.zeros(n)
    spread[100:] = 5.0  # step: z parte ~7.7 (entry), poi stop, poi decade
    trend = 3.0 + 0.001 * np.arange(n)
    s = _scelta(beta=1.0)
    precis = _coppia_precis(trend + spread, trend)
    allin = _allineate(precis, s)
    giorni = _giorni(precis, s)
    res = p13.simula_portafoglio([s], allin, giorni, capitale=1000.0)
    stops = [o for o in res["ops"] if o.motivo_uscita == "stop"]
    assert stops, "z alto immediato deve generare un episodio di stop"
    assert all(o.rotture for o in stops), \
        "step costante: z non rientra in 0.5 entro 30g → tutte rotture"


def test_engine_no_rottura_con_rientro():
    # step BREVE (8gg) che rientra: |z| torna <= 0.5 entro 30g dallo stop → non rottura
    n = 300
    spread = np.zeros(n)
    spread[100:108] = 5.0  # step 8 giorni, poi ritorno a 0
    trend = 3.0 + 0.001 * np.arange(n)
    s = _scelta(beta=1.0)
    precis = _coppia_precis(trend + spread, trend)
    allin = _allineate(precis, s)
    giorni = _giorni(precis, s)
    res = p13.simula_portafoglio([s], allin, giorni, capitale=1000.0)
    stops = [o for o in res["ops"] if o.motivo_uscita == "stop"]
    assert stops, "z alto all'improvviso deve generare un episodio di stop"
    assert not stops[0].rotture, "rientro in |z|<=0.5 entro 30g: non e' una rottura"


# ---------- cancello --------------------------------------------------------------------

def test_cancello_n_zero_insufficiente():
    # spread piatto: nessun segnale, zero operazioni
    n = 200
    trend = 3.0 + 0.001 * np.arange(n)
    s = _scelta(beta=1.0)
    precis = _coppia_precis(trend, trend)  # spread = 0 ovunque
    allin = _allineate(precis, s)
    giorni = _giorni(precis, s)
    v = p13.valuta_verifica([s], allin, giorni, capitale=1000.0)
    assert v["n"] == 0
    assert v["esito"] == "insufficiente"
    assert any("n=0" in m for m in v["motivi"])
    assert v["t_stat"] == 0.0


def test_cancello_tutte_escluse_archiviata():
    # step costante → 1 stop, 1 rottura (100% > 20%) → coppia esclusa → archiviata
    n = 200
    spread = np.zeros(n)
    spread[100:] = 5.0
    trend = 3.0 + 0.001 * np.arange(n)
    s = _scelta(beta=1.0)
    precis = _coppia_precis(trend + spread, trend)
    allin = _allineate(precis, s)
    giorni = _giorni(precis, s)
    v = p13.valuta_verifica([s], allin, giorni, capitale=1000.0)
    assert v["per_coppia"]["A/B"]["esclusa"]
    assert v["esito"] == "archiviata", "tutte le coppie escluse → archiviata, a prescindere"


def test_cancello_promossa_con_spread_veloce():
    # spread AR(1) veloce (phi=0.3), campione ampio: la reversione batte i costi
    n = 1000
    la, lb = _trend_e_spread(n, seed=17, phi=0.3, amp=3.5)
    s = _scelta(beta=1.0)
    precis = _coppia_precis(la, lb)
    allin = _allineate(precis, s)
    giorni = _giorni(precis, s)
    v = p13.valuta_verifica([s], allin, giorni, capitale=1000.0)
    assert v["n"] >= 30, "spread veloce su 1000 barre: campione sufficiente"
    assert v["criteri"]["exp_ok"], "reversione forte: expectancy deve superare 3x pedaggio"
    assert v["criteri"]["dd_ok"], "market-neutral: il DDport non deve esplodere"
    assert v["criteri"]["n_ok"]
    assert v["esito"] == "promossa"
    # metà: stessa relazione in entrambe → nessun cambio di segno
    assert not v["cambio_segno_meze"]
    assert v["profit_factor"] > 1.0


def test_cancello_ddport_e_campione_rispettato():
    n = 700
    la, lb = _trend_e_spread(n, seed=18, phi=0.3, amp=3.0)
    s = _scelta(beta=1.0)
    precis = _coppia_precis(la, lb)
    allin = _allineate(precis, s)
    giorni = _giorni(precis, s)
    v = p13.valuta_verifica([s], allin, giorni, capitale=1000.0)
    # la metà non puo' avere operazioni piu' del totale
    assert v["meze"]["prima"]["n"] + v["meze"]["seconda"]["n"] == v["n"]
    # il DDport e' in [0, 1]
    assert 0.0 <= v["ddport"] <= 1.0


# ---------- caricamenti ------------------------------------------------------------------

def test_carica_funding(tmp_path):
    p = tmp_path / "f.jsonl"
    p.write_text("\n".join([
        json.dumps({"simbolo": "BTC/USD:USD-310404", "ts": 100, "funding": 0.0001}),
        json.dumps({"simbolo": "BTC/USD:USD-310404", "ts": 100, "funding": 0.999}),  # dup
        json.dumps({"simbolo": "ETH/USD:USD-310404", "ts": 200, "funding": -0.0002}),
    ]), encoding="utf-8")
    fondi = p13.carica_funding(str(p))
    assert set(fondi) == {"BTC", "ETH"}
    assert fondi["BTC"][100] == 0.0001, "dedup: resta la PRIMA riga"
    assert fondi["ETH"][200] == -0.0002


def test_carica_funding_manca_file():
    assert p13.carica_funding("/non/esiste/funding.jsonl") == {}


def test_carica_usdt_lungo_manca(tmp_path):
    with pytest.raises(FileNotFoundError):
        p13.carica_usdt_lungo(str(tmp_path), ["BTC"])


def test_carica_usdt_lungo_corto(tmp_path):
    f = tmp_path / "okx_eea_BTC-USDT_1d.json"
    f.write_text(json.dumps({"barre": [[TS0 + i, 1, 1, 1, 1, 1] for i in range(10)]}),
                 encoding="utf-8")
    with pytest.raises(ValueError):
        p13.carica_usdt_lungo(str(tmp_path), ["BTC"])


# ---------- report -------------------------------------------------------------------------

def test_report_screening_vuoto():
    testo = p13.report_testo(None, [], [], "x → y", "y → z")
    assert "ARCHIVIATA" in testo
    assert "NESSUNA COPIA PASSA" in testo


def test_report_json_serializzabile():
    n = 200
    trend = 3.0 + 0.001 * np.arange(n)
    s = _scelta(beta=1.0)
    precis = _coppia_precis(trend, trend)
    allin = _allineate(precis, s)
    giorni = _giorni(precis, s)
    v = p13.valuta_verifica([s], allin, giorni, capitale=1000.0)
    out = p13.report_json(v, [], [s])
    payload = json.loads(out)  # nessuna NaN, nessun numpy
    assert payload["verifica"]["n"] == v["n"]
    assert "griglia_congelata" in payload
