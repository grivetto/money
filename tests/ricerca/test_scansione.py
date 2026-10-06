"""Test della scansione esplorativa (motore, costi, causalita', correzione multipla).

Nessuna rete: serie sintetiche costruite a mano.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from money.dati import Barra, SerieBarre
from money.costi import get_tariffa
from money.ricerca import scansione as S
from money.ricerca.rsi_mean_reversion import SLIPPAGE_PER_LATO, TARIFFA_ASSUNTA, ritorno_netto


def barre_da_chiusure(chiusure, da: str = "2024-01-01", ore: int = 24) -> SerieBarre:
    """Barre giornaliere con apertura = chiusura precedente (semplice e deterministico).

    L'apertura della barra i e' la chiusura della barra i-1 (la prima apre sul primo prezzo):
    cosi' ingressi e uscite all'apertura sono calcolabili a mano nei test.
    """
    inizio = datetime.fromisoformat(da).replace(tzinfo=timezone.utc)
    barre = []
    for i, c in enumerate(chiusure):
        ts = int((inizio + timedelta(hours=ore * i)).timestamp() * 1000)
        a = chiusure[i - 1] if i > 0 else chiusure[0]
        barre.append(Barra(ts=ts, apertura=a, massimo=max(a, c), minimo=min(a, c),
                           chiusura=c, volume=1.0))
    return SerieBarre(barre, venue="test", simbolo="T", timeframe="1d")


def test_costi_e_convenzione_di_esecuzione():
    """Il netto e' quello della catena (fee del giro misto + slippage per lato)."""
    # stato: flat, poi long alla chiusura dell'indice 2, flat alla chiusura del 4
    chiusure = [100.0, 100.0, 100.0, 110.0, 110.0, 110.0]
    serie = barre_da_chiusure(chiusure)
    stato = [False, False, True, True, False, False]
    trades = S.simula(serie, stato)
    assert len(trades) == 1
    t = trades[0]
    # ingresso all'apertura della barra 3 (= chiusura 2 = 100), uscita all'apertura della 5
    # (= chiusura 4 = 110): lordo +10% esatto.
    assert t.i_in == 3 and t.i_out == 5
    assert t.lordo == pytest.approx(0.10)
    atteso = ritorno_netto(0.10, slippage_per_lato=SLIPPAGE_PER_LATO)
    assert t.netto == pytest.approx(atteso)
    # e il pedaggio e' quello del giro misto della tariffa assunta (conto reale)
    giro = get_tariffa(TARIFFA_ASSUNTA).giro_misto
    assert t.netto == pytest.approx((1 - SLIPPAGE_PER_LATO) * 1.10 * (1 - SLIPPAGE_PER_LATO)
                                    - 1.0 - giro)


def test_liquidazione_finale_all_apertura():
    """Chi resta dentro a fine finestra esce all'ultima apertura ('fine serie')."""
    chiusure = [100.0, 101.0, 102.0, 103.0, 104.0]
    serie = barre_da_chiusure(chiusure)
    trades = S.simula(serie, [True, True, True, True, True])
    assert trades and trades[-1].motivo == "fine serie"


def test_il_futuro_non_cambia_i_trade_passati():
    """Mutare le barre future non tocca le operazioni concluse prima."""
    chiusure = [100.0, 101.0, 102.0, 103.0, 102.0, 101.0, 100.0, 99.0,
                98.0, 97.0, 96.0, 95.0, 94.0, 93.0, 92.0, 91.0]
    serie_a = barre_da_chiusure(chiusure)
    mutate = list(chiusure)
    mutate[-2] = 999.0
    mutate[-1] = 998.0
    serie_b = barre_da_chiusure(mutate)
    stato = lambda bb: S.stato_mom_abs(bb, 2)  # noqa: E731
    ta = S.simula(serie_a, stato(serie_a))
    tb = S.simula(serie_b, stato(serie_b))
    # i trade che si chiudono PRIMA delle due barre mutate restano identici
    confine = serie_a[-2].ts
    a_chiusi = [t for t in ta if t.ts_out < confine]
    b_chiusi = [t for t in tb if t.ts_out < confine]
    assert a_chiusi, "il caso di prova deve contenere almeno un trade concluso (non vacuo)"
    assert [(t.i_in, t.i_out, t.netto) for t in a_chiusi] == \
           [(t.i_in, t.i_out, t.netto) for t in b_chiusi]


def test_soglie_di_sopravvivenza():
    """Il filtro dei candidati: n, expectancy, t e DSR — ognuno puo' escludere da solo."""
    base = {"chiave": "X", "simbolo": "S", "train": {}, "oos": {"n": 40, "expectancy": 0.01,
            "t_stat": 1.5}, "dsr_oos": {"dsr": 0.97}}
    assert len(S.seleziona_sopravvissuti([base])) == 1
    no_n = {**base, "oos": {**base["oos"], "n": 10}}
    no_exp = {**base, "oos": {**base["oos"], "expectancy": -0.001}}
    no_t = {**base, "oos": {**base["oos"], "t_stat": -0.2}}
    no_dsr = {**base, "dsr_oos": {"dsr": 0.90}}
    nessun_dsr = {**base, "dsr_oos": None}
    for s in (no_n, no_exp, no_t, no_dsr, nessun_dsr):
        assert S.seleziona_sopravvissuti([s]) == []


def test_dsr_punire_dopo_molti_tentativi():
    """Uno Sharpe che passa con pochi tentativi puo' NON passare con centinaia.

    Il benchmark E[max SR] cresce col numero di tentativi (Bailey & Lopez de Prado): lo
    stesso risultato osservato vale meno quando e' stato scelto tra molti. Il caso di prova
    e' costruito a meta' strada fra i due benchmark, con la varianza dei tentativi ampia:
    il discriminante non dipende da un numero magico.
    """
    from money.statistica import sharpe_atteso_massimo
    var = 0.02 ** 2
    sr0_pochi = sharpe_atteso_massimo(5, var)
    sr0_molti = sharpe_atteso_massimo(500, var)
    assert sr0_molti > sr0_pochi                     # il costo dei tentativi esiste
    sr = (sr0_pochi + sr0_molti) / 2 + 0.17
    pochi = S.sharpe_deflazionato(sr, 100, 5, var)
    molti = S.sharpe_deflazionato(sr, 100, 500, var)
    assert pochi["dsr"] > molti["dsr"]               # la correzione penalizza
    assert pochi["dsr"] >= 0.95 > molti["dsr"]       # e attraversa la soglia dichiarata


def test_griglia_dichiarata_e_unica():
    assert len(S.GRIGLIA) == len({S.chiave_config(c) for c in S.GRIGLIA})
    famiglie = {c["famiglia"] for c in S.GRIGLIA}
    assert famiglie == {"sma_cross", "mom_abs", "donchian", "reversion_z", "rsi2",
                        "weekday", "turn_month"}


def test_weekday_e_turn_month_causali():
    """I calendari marcano i giorni giusti (UTC) e non guardano il futuro."""
    serie = barre_da_chiusure([100.0] * 40, da="2024-01-01")  # 2024-01-01 e' un lunedi'
    lun = S.stato_weekday(serie, 0)
    assert lun[0] is True and lun[7] is True and lun[1] is False
    primi = S.stato_turn_month(serie, "primi", 2)
    assert primi[0] is True and primi[1] is True and primi[2] is False


def test_scansione_end_to_end_su_serie_finte():
    """Scansione completa su serie corte: struttura completa, nessun candidato per numerosita'."""
    chiusure = [100.0 + 0.2 * i for i in range(80)]  # trend regolare, 80 barre
    serie = {"A": barre_da_chiusure(chiusure), "B": barre_da_chiusure(
        [100.0 - 0.1 * i for i in range(80)])}  # noqa: E501
    griglia = (
        {"famiglia": "sma_cross", "fast": 5, "slow": 20},
        {"famiglia": "mom_abs", "L": 10},
    )
    results = S.scansiona(serie, griglia=griglia, confine="2024-02-01")
    assert results["meta"]["n_trials"] == 4  # 2 config x 2 simboli
    assert isinstance(results["selezioni"], list) and len(results["selezioni"]) <= 2
    # con la verifica troppo corta (< 30 op) non esistono candidati: il filtro e' dichiarato
    assert results["candidati"] == []
    for t in results["trials"]:
        assert set(t["train"]) >= {"n", "expectancy", "t_stat"}
        assert set(t["oos"]) >= {"n", "expectancy", "t_stat"}
