"""Test della caccia continua (S4): limiti, frontiera, contabilita' cumulativa, candidati.

Nessuna rete: strutture sintetiche costruite a mano.
"""
from __future__ import annotations

import json

import pytest

from money.ricerca import caccia_continua as C
from money.statistica import sharpe_deflazionato, varianza_da_tentativi


def _trial(chiave: str, famiglia: str, params: dict, simbolo: str,
           tn, te, tsh, on, oe, osh, ot=None) -> dict:
    return {
        "chiave": chiave, "famiglia": famiglia, "params": params, "simbolo": simbolo,
        "train": {"n": tn, "expectancy": te, "sharpe": tsh, "t_stat": 1.0},
        "oos": {"n": on, "expectancy": oe, "sharpe": osh, "t_stat": ot},
    }


def test_limiti_dichiarati():
    assert C.dentro_limiti({"famiglia": "sma_cross", "fast": 10, "slow": 30})
    assert C.dentro_limiti({"famiglia": "macd", "fast": 12, "slow": 26, "segnale": 9})
    assert not C.dentro_limiti({"famiglia": "sma_cross", "fast": 400, "slow": 500})
    assert not C.dentro_limiti({"famiglia": "sma_cross", "fast": 10, "slow": 600})
    assert not C.dentro_limiti({"famiglia": "macd", "fast": 12, "slow": 200, "segnale": 9})
    assert not C.dentro_limiti({"famiglia": "donchian", "n_in": 450, "n_out": 10})
    assert C.dentro_limiti({"famiglia": "turn_month", "pos": "primi", "k": 6})
    assert not C.dentro_limiti({"famiglia": "turn_month", "pos": "primi", "k": 7})
    assert not C.dentro_limiti({"famiglia": "turn_month", "pos": "meta'", "k": 2})
    assert not C.dentro_limiti({"famiglia": "sconosciuta", "x": 1})
    assert not C.dentro_limiti({"famiglia": "sma_cross", "fast": 10, "slow": 30, "boh": 1})


def test_vicini_dedup_e_dominio():
    vicini = C.vicini_caccia({"famiglia": "sma_cross", "fast": 10, "slow": 30})
    coppie = sorted((v["fast"], v["slow"]) for v in vicini)
    assert coppie == [(5, 30), (10, 20), (10, 40), (15, 30)]
    chiavi = [C.chiave(v) for v in vicini]
    assert len(chiavi) == len(set(chiavi))
    # turn_month: +-1 su k, pos invariata; k=1 in basso e' fuori dominio (k-1=0)
    vicini = C.vicini_caccia({"famiglia": "turn_month", "pos": "primi", "k": 1})
    assert [C.chiave(v) for v in vicini] == ["turn_month(k=2,pos=primi)"]
    # famiglia senza passi dichiarati: nessun vicino
    assert C.vicini_caccia({"famiglia": "weekday", "giorno": 3}) == []


def test_estrai_batch_best_first_deterministico():
    coda = [["b", {"famiglia": "mom_abs", "L": 10}, 0.05],
            ["a", {"famiglia": "mom_abs", "L": 10}, 0.05],
            ["c", {"famiglia": "mom_abs", "L": 10}, -0.1],
            ["d", {"famiglia": "mom_abs", "L": 10}, 0.2]]
    fuori = C.estrai_batch(coda, 3)
    assert [x[0] for x in fuori] == ["d", "a", "b"]  # priorita' desc, pareggio per chiave
    assert [x[0] for x in coda] == ["c"]


def test_nuova_frontiera_dedup():
    viste = {"mom_abs(L=10)"}
    coda: list = []
    assert C.nuova_frontiera(coda, viste, {"famiglia": "mom_abs", "L": 10}, 0.01) == 1
    assert coda == [["mom_abs(L=20)", {"famiglia": "mom_abs", "L": 20}, 0.01]]
    assert "mom_abs(L=20)" in viste
    # tutti i vicini gia' visti: zero aggiunti (dedup)
    assert C.nuova_frontiera(coda, viste, {"famiglia": "mom_abs", "L": 10}, 0.01) == 0
    # priorita' mancante -> sentinella
    coda2: list = []
    C.nuova_frontiera(coda2, set(), {"famiglia": "mom_abs", "L": 30}, None)
    assert coda2[0][2] == C.PRIO_NULL


def test_accumulo_statistiche_incrementali():
    acc = C.Accumulo()
    acc.aggiungi(None)
    assert acc.n == 0 and acc.varianza == 0.0  # None scartato; n<2 -> varianza 0
    for s in (0.5, -0.25, 1.0, 0.75):
        acc.aggiungi(s)
    assert acc.n == 4
    assert acc.varianza == pytest.approx(varianza_da_tentativi([0.5, -0.25, 1.0, 0.75]))
    # round-trip dei conti
    ricaricato = C.Accumulo.da_dict(json.loads(json.dumps(acc.a_dict())))
    assert ricaricato.a_dict() == acc.a_dict()


def test_semi_da_artefatti():
    doc = {"results": {"trials": [
        _trial("mom_abs(L=10)", "mom_abs", {"L": 10}, "BTC/USDT", 100, 0.01, 0.4, 50, 0.0, 0.0),
        _trial("mom_abs(L=10)", "mom_abs", {"L": 10}, "ETH/USDT", 100, 0.03, 0.9, 50, 0.0, 0.0),
        _trial("mom_abs(L=5)", "mom_abs", {"L": 5}, "BTC/USDT", 12, 0.9, None, 4, None, None),
    ]}}
    semi, priori = C.semi_da_artefatti([doc, {}])
    assert set(semi) == {"mom_abs(L=10)", "mom_abs(L=5)"}
    assert C.chiave(semi["mom_abs(L=10)"]) == "mom_abs(L=10)"
    assert semi["mom_abs(L=10)"] == {"famiglia": "mom_abs", "L": 10}
    assert priori["mom_abs(L=10)"] == pytest.approx(0.03)  # massimo in addestramento
    assert priori.get("mom_abs(L=5)") is None  # n_train < 30: non valutabile (ripiego)


def test_record_da_trials_selezione_e_gate():
    trials = [
        _trial("mom_abs(L=10)", "mom_abs", {"L": 10}, "A", 100, 0.01, 0.5, 50, 0.02, 0.8, ot=2.0),
        _trial("mom_abs(L=10)", "mom_abs", {"L": 10}, "B", 100, 0.03, 0.9, 40, -0.01, -0.3, ot=-1.0),
        _trial("mom_abs(L=10)", "mom_abs", {"L": 10}, "C", 5, 0.9, None, 3, None, None),
    ]
    records = C.record_da_trials(trials)
    assert len(records) == 1
    rec = records[0]
    assert rec["stat"]["n"] == 2  # solo A e B sono valutabili in addestramento
    assert rec["sel"]["simbolo"] == "B"  # massima expectancy di addestramento
    assert not C.papabile(rec["sel"])  # ma in verifica B e' negativa: niente screening
    rec_a = C.record_da_trials([trials[0]])[0]
    assert C.papabile(rec_a["sel"])  # A in verifica: n>=30, exp>0, t>0


def test_valuta_candidati_promozione_declassamento_ripromozione():
    sel = {"simbolo": "A",
           "train": {"n": 100, "expectancy": 0.02, "sharpe": 0.6, "t_stat": 2.0},
           "oos": {"n": 60, "expectancy": 0.03, "sharpe": 1.0, "t_stat": 2.5}}
    acc_basso = C.Accumulo(n=1000, somma=0.0, somma2=10.0)      # varianza = 0.01
    acc_alto = C.Accumulo(n=1_000_000, somma=0.0, somma2=90000.0)  # varianza = 0.09

    # il DSR della caccia deve coincidere con la formula diretta
    atteso = sharpe_deflazionato(1.0, 60, 1000, 0.01)["dsr"]
    assert C.dsr_di(sel, acc_basso) == pytest.approx(atteso)
    assert atteso >= 0.95, "il caso di prova deve passare col conteggio basso"

    trans = C.valuta_candidati({"k": sel}, {}, acc_basso)
    assert [k for k, _ in trans["promossi"]] == ["k"]
    assert not trans["declassati"] and not trans["ripromossi"]

    # gia' "ok" e conta basso: nessuna transizione (niente rumore)
    trans = C.valuta_candidati({"k": sel}, {"k": {"stato": "ok"}}, acc_basso)
    assert not trans["promossi"] and not trans["declassati"] and not trans["ripromossi"]

    # col conteggio salito il DSR crolla: declassamento esplicito
    assert C.dsr_di(sel, acc_alto) < 0.95
    trans = C.valuta_candidati({"k": sel}, {"k": {"stato": "ok"}}, acc_alto)
    assert [k for k, _ in trans["declassati"]] == ["k"]
    assert not trans["promossi"]

    # un declassato che torna a passare: ripromozione
    trans = C.valuta_candidati({"k": sel}, {"k": {"stato": "declassato"}}, acc_basso)
    assert [k for k, _ in trans["ripromossi"]] == ["k"]


def test_stato_iniziale_serializzabile():
    semi = {"mom_abs(L=10)": {"famiglia": "mom_abs", "L": 10}}
    stato = C.stato_iniziale(semi, {"mom_abs(L=10)": 0.02}, creazione="2026-10-08 00:00Z")
    ricaricato = json.loads(json.dumps(stato))
    assert ricaricato["coda"] == [["mom_abs(L=20)", {"famiglia": "mom_abs", "L": 20}, 0.02]]
    assert ricaricato["viste"] == ["mom_abs(L=10)", "mom_abs(L=20)"]
    assert ricaricato["accumulo"] == {"n": 0, "somma": 0.0, "somma2": 0.0}
    assert ricaricato["papabili"] == {} and ricaricato["candidati"] == {}
