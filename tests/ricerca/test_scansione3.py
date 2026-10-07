"""Test della caccia adattiva S3 (griglia estesa, vicini dichiarati, correzione unita).

Nessuna rete: serie sintetiche costruite a mano.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from money.dati import Barra, SerieBarre
from money.ricerca import scansione3 as S3


def barre_da_chiusure(chiusure, da: str = "2024-01-01") -> SerieBarre:
    inizio = datetime.fromisoformat(da).replace(tzinfo=timezone.utc)
    barre = []
    for i, c in enumerate(chiusure):
        ts = int((inizio + timedelta(days=i)).timestamp() * 1000)
        a = chiusure[i - 1] if i > 0 else chiusure[0]
        barre.append(Barra(ts=ts, apertura=a, massimo=max(a, c), minimo=min(a, c),
                           chiusura=c, volume=1.0))
    return SerieBarre(barre, venue="test", simbolo="T", timeframe="1d")


def test_griglia_s3_dichiarata_e_unica():
    assert len(S3.GRIGLIA_S3) == 61
    chiavi = [S3.chiave_config(c) for c in S3.GRIGLIA_S3]
    assert len(chiavi) == len(set(chiavi))
    famiglie = {c["famiglia"] for c in S3.GRIGLIA_S3}
    assert famiglie == {"sma_cross", "ema_cross", "macd", "mom_abs", "mom_trend",
                        "donchian", "reversion_z", "rsi2", "weekday", "turn_month"}


def test_vicini_un_passo_per_volta():
    cfg = {"famiglia": "sma_cross", "fast": 10, "slow": 30}
    vicini = S3.vicini_config(cfg)
    coppie = {(v["fast"], v["slow"]) for v in vicini}
    assert coppie == {(15, 30), (5, 30), (10, 40), (10, 20)}
    # ogni vicino differisce dal genitore in UN solo parametro, del passo dichiarato
    for v in vicini:
        diff = [k for k in ("fast", "slow") if v[k] != cfg[k]]
        assert len(diff) == 1


def test_vicini_dedup_e_dominio():
    # fast=5, slow=8: fast+5=10 >= slow -> fuori dominio; slow-10<3 -> fuori;
    # restano solo i vicini validi, mai duplicati.
    cfg = {"famiglia": "sma_cross", "fast": 5, "slow": 8}
    coppie = {(v["fast"], v["slow"]) for v in S3.vicini_config(cfg)}
    assert coppie == {(5, 18)}
    # donchian: n_out < n_in obbligatorio
    cfg2 = {"famiglia": "donchian", "n_in": 20, "n_out": 10}
    v2 = {(v["n_in"], v["n_out"]) for v in S3.vicini_config(cfg2)}
    assert v2 == {(30, 10), (20, 15), (20, 5)}   # (10,10) viola n_out<n_in
    assert all(b < a for a, b in v2)             # nessun vicino invalido sopravvissuto
    # reversion_z: k > 0 (k-0.25 con k=0.25 -> 0 escluso)
    cfg3 = {"famiglia": "reversion_z", "n": 10, "k": 0.25}
    v3 = S3.vicini_config(cfg3)
    assert {(v["n"], v["k"]) for v in v3} == {(15, 0.25), (5, 0.25), (10, 0.5)}


def test_vicini_famiglie_senza_passi():
    assert S3.vicini_config({"famiglia": "weekday", "giorno": 2}) == []


def test_seleziona_da_raffinare_top_k():
    def t(chiave, fam, exp, n=40, params=None):
        return {"chiave": chiave, "famiglia": fam, "params": params or {},
                "train": {"n": n, "expectancy": exp}, "oos": {}}

    trials = [
        t("mom_abs(L=10)", "mom_abs", 0.01, params={"L": 10}),
        t("mom_abs(L=20)", "mom_abs", 0.05, params={"L": 20}),
        t("mom_abs(L=60)", "mom_abs", 0.02, params={"L": 60}),
        t("mom_abs(L=90)", "mom_abs", 0.03, n=5, params={"L": 90}),      # sotto min_op
        t("rsi2(a)", "rsi2", 0.04, params={"periodo": 2, "soglia_in": 5.0, "soglia_out": 50.0}),
    ]
    scelte = S3.seleziona_da_raffinare(trials, top_k=2, min_op=30)
    chiavi = [x["chiave"] for x in scelte]
    assert chiavi == ["mom_abs(L=20)", "mom_abs(L=60)", "rsi2(a)"]


def test_stato_ema_cross_causale():
    chiusure = [100.0 + (i % 7) for i in range(60)]
    serie_a = barre_da_chiusure(chiusure)
    mutate = list(chiusure)
    mutate[-2], mutate[-1] = 999.0, 998.0
    serie_b = barre_da_chiusure(mutate)
    a = S3.stato_ema_cross(serie_a, 5, 20)
    b = S3.stato_ema_cross(serie_b, 5, 20)
    assert a[:-2] == b[:-2]
    assert any(x is True for x in a) or any(x is False for x in a)


def test_stato_macd_causale_e_warmup():
    chiusure = [100.0] * 60 + [100.0 + 0.5 * i for i in range(1, 41)]
    serie = barre_da_chiusure(chiusure)
    stato = S3.stato_macd(serie, 12, 26, 9)
    assert all(x is None for x in stato[:26])          # warmup slow
    assert any(x is True for x in stato)               # rampa in salita: MACD sopra segnale
    assert stato[-1] is True
    mutate = list(chiusure)
    mutate[-1] = 10.0
    b = S3.stato_macd(barre_da_chiusure(mutate), 12, 26, 9)
    assert stato[:-1] == b[:-1]


def test_stato_mom_trend_filtro():
    # serie in discesa: il filtro SMA non fa mai entrare
    chiusure = [200.0 - 0.5 * i for i in range(60)]
    serie = barre_da_chiusure(chiusure)
    stato = S3.stato_mom_trend(serie, 5, 20)
    assert not any(x is True for x in stato)
    # serie in salita: entra
    su = [100.0 + 0.5 * i for i in range(60)]
    stato_su = S3.stato_mom_trend(barre_da_chiusure(su), 5, 20)
    assert any(x is True for x in stato_su)


def test_caccia_end_to_end_e_unione_dei_tentativi():
    """Due stadi su serie finte: la correzione conta l'UNIONE di tutti i tentativi."""
    import math
    chiusure_a = [100.0 + 10.0 * math.sin(i / 3.0) for i in range(140)]
    chiusure_b = [100.0 + 8.0 * math.cos(i / 2.5) for i in range(140)]
    serie = {"A": barre_da_chiusure(chiusure_a), "B": barre_da_chiusure(chiusure_b)}
    griglia = (
        {"famiglia": "mom_abs", "L": 10},
        {"famiglia": "mom_abs", "L": 30},
        {"famiglia": "ema_cross", "fast": 5, "slow": 20},
    )
    res = S3.scansiona_adattiva(serie, griglia=griglia, confine="2024-03-01",
                                min_op=3, soglia_dsr=0.95, top_k=1)
    n1 = res["meta"]["n_configurazioni_stadio1"]
    n2 = res["meta"]["n_configurazioni_stadio2"]
    assert n1 == 3 and n2 >= 1
    assert res["meta"]["n_trials"] == (n1 + n2) * len(serie)
    # la verifica non e' nel conteggio: n_tentativi = valutabili dell'unione
    atteso = sum(1 for t in res["trials"]
                 if t["train"]["n"] >= 3 and t["train"]["sharpe"] is not None)
    assert res["meta"]["n_trials_valutabili"] == atteso
    # su una sinusoide (mercato "amico") un candidato PUO' esistere: se esiste, deve
    # rispettare il filtro dichiarato (n, expectancy, t e DSR oltre soglia); mai escluso a priori.
    for c in res["candidati"]:
        assert c["oos"]["n"] >= 3
        assert c["oos"]["expectancy"] > 0.0
        assert c["oos"]["t_stat"] > 0.0
        assert c["dsr_oos"]["dsr"] >= 0.95
    # le config raffinate sono dello stadio 1 e i vicini portano chiavi nuove
    assert set(res["meta"]["raffinate"]) <= {S3.chiave_config(c) for c in griglia}
    chiavi_unione = {(t["chiave"], t["simbolo"]) for t in res["trials"]}
    assert len(chiavi_unione) == len(res["trials"])
