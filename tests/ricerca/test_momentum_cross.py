"""Test del motore P10 — momentum cross-sectional long/flat (rotazione top-k).

PERCHE' QUESTI TEST ESISTONO
============================
La spec P10 e' costruita su quattro promesse che, se false, fanno misurare un'altra cosa:
  1. anti-lookahead: il ranking usa solo chiusure FINO a `i`, e si esegue all'apertura di `i+1`;
  2. timing: si ribilancia ogni `R` barre e si toccano SOLO i cambi di composizione;
  3. costi: una sola verita' (`money.costi`) + 4 bp per lato, una volta per giro;
  4. long-only / paniere: mai short, e chi resta in top-k non viene rivenduto per rientrare;
  5. caso degenere: con 0 candidati si e' flat; con meno di `k` si tengono i disponibili.
Questi test bloccano ognuna di quelle promesse su casi piccoli e determinati.
"""
from __future__ import annotations

import pytest

from money.costi import get_tariffa
from money.dati import Barra
from money.ricerca import momentum_cross as M
from money.ricerca.portafoglio import backtest_portafoglio

T0 = 1_700_000_000_000
PASSO = 86_400_000


def barre(piazze, ts0=T0):
    """piazze: lista di tuple (apertura, chiusura) -> Barra con high/low coerenti."""
    return [Barra(ts0 + i * PASSO, a, max(a, c), min(a, c), c, 1000.0)
            for i, (a, c) in enumerate(piazze)]


def da_chiusure(chiusure, aperture=None):
    """Serie costruita dalle chiusure; se le aperture non sono date coincidono (caso semplice)."""
    if aperture is None:
        aperture = list(chiusure)
    return barre(list(zip(aperture, chiusure)))


# ---------------------------------------------------------------------------
# 1) ANTI-LOOKAHEAD
# ---------------------------------------------------------------------------

def test_ranking_usa_solo_le_chiusure_fino_a_i():
    cfg = M.Config(k=1, lookback=2, ribilancio=2)
    orig = {"A": da_chiusure([100.0, 100.0, 110.0]),
            "B": da_chiusure([100.0, 100.0, 100.0])}
    # Aggiungere barre FUTURE non deve cambiare la composizione decisa alla chiusura di i=2.
    futuro = {"A": da_chiusure([100.0, 100.0, 110.0, 999.0, 999.0]),
              "B": da_chiusure([100.0, 100.0, 100.0, 1.0, 1.0])}
    assert M.composizione_target(orig, 2, cfg) == ["A"]
    assert M.composizione_target(futuro, 2, cfg) == ["A"]
    # Controllo non vacuo: cambiando la chiusura di i (non il futuro) il target cambia.
    diverso = {"A": da_chiusure([100.0, 100.0, 100.0]),
               "B": da_chiusure([100.0, 100.0, 110.0])}
    assert M.composizione_target(diverso, 2, cfg) == ["B"]


def test_esecuzione_all_apertura_della_barra_successiva():
    cfg = M.Config(k=1, lookback=2, ribilancio=10)
    serie = {
        "A": barre([(100.0, 100.0), (100.0, 100.0), (100.0, 110.0),
                    (123.0, 125.0), (130.0, 130.0)]),
        "B": barre([(100.0, 100.0), (100.0, 100.0), (100.0, 100.0),
                    (200.0, 200.0), (200.0, 200.0)]),
    }
    ops = M.operazioni_paniere(serie, cfg)
    assert [o.simbolo for o in ops] == ["A"]
    o = ops[0]
    assert o.indice_ingresso == 3                    # la barra DOPO il segnale (i=2)
    assert o.prezzo_ingresso == 123.0                # apertura di 3, NON la chiusura 110 di 2
    assert o.ts_ingresso == serie["A"][3].ts


# ---------------------------------------------------------------------------
# 2) TIMING DI RIBILANCIAMENTO
# ---------------------------------------------------------------------------

def test_ribilanciamento_ogni_R_barre_eseguito_all_apertura_successiva():
    cfg = M.Config(k=1, lookback=2, ribilancio=2)
    cA = [100, 100, 110, 110, 100, 100, 110, 110, 100]
    cB = [100, 100, 100, 100, 110, 110, 100, 100, 110]
    serie = {"A": da_chiusure(cA), "B": da_chiusure(cB)}
    ops = M.operazioni_paniere(serie, cfg)
    firma = [(o.simbolo, o.indice_ingresso, o.indice_uscita, o.motivo) for o in ops]
    assert firma == [("A", 3, 5, "ribilancio"),
                     ("B", 5, 7, "ribilancio"),
                     ("A", 7, 8, "fine serie")]
    # Nessuno scambio fuori dal calendario {L+1, L+1+R, ...} ne' dalla liquidazione finale.
    cambi = {o.indice_ingresso for o in ops} | {o.indice_uscita for o in ops}
    assert cambi <= {3, 5, 7, 8}


def test_target_invariato_non_genera_turnover():
    cfg = M.Config(k=1, lookback=2, ribilancio=2)
    serie = {"A": da_chiusure([100, 110, 120, 130, 140, 150, 160]),
             "B": da_chiusure([100, 100, 100, 100, 100, 100, 100])}
    ops = M.operazioni_paniere(serie, cfg)
    # A e' top-k a ogni giro: UNA sola operazione continua, non un giro di costi per barra.
    assert len(ops) == 1
    assert (ops[0].indice_ingresso, ops[0].indice_uscita) == (3, 6)


def test_griglia_dichiarata_e_otto_varianti_distinte():
    assert len(M.GRIGLIA_ADDESTRAMENTO) == 8
    assert len({M.Config(**p).chiave() for p in M.GRIGLIA_ADDESTRAMENTO}) == 8


# ---------------------------------------------------------------------------
# 3) APPLICAZIONE COSTI
# ---------------------------------------------------------------------------

def _scenario_un_giro():
    """Un solo round-trip A: entra all'apertura di 2 (101), esce all'apertura di 4 (110)."""
    cfg = M.Config(k=1, lookback=1, ribilancio=100)
    serie = {
        "A": barre([(100.0, 100.0), (100.0, 100.0), (101.0, 101.0),
                    (105.0, 105.0), (110.0, 110.0)]),
        "B": barre([(100.0, 100.0), (100.0, 100.0), (99.0, 99.0),
                    (98.0, 98.0), (97.0, 97.0)]),
    }
    return cfg, serie


def test_costi_da_money_costi_applicati_una_volta_per_giro():
    cfg, serie = _scenario_un_giro()
    ops = M.operazioni_paniere(serie, cfg)
    assert [(o.simbolo, o.indice_ingresso, o.indice_uscita) for o in ops] == [("A", 2, 4)]

    esito = M.backtest(serie, cfg)
    assert esito.operazioni_eseguite == 1

    tariffa = get_tariffa(M.TARIFFA_ASSUNTA)
    slip = M.SLIPPAGE_PER_LATO
    lordo = 110.0 / 101.0 - 1.0
    atteso = (1.0 - slip) * (1.0 + lordo) * (1.0 - slip) - 1.0 - tariffa.giro_misto
    assert esito.capitale_finale == pytest.approx(1000.0 * (1.0 + atteso), rel=1e-9)
    # Il pedaggio e' quello di money.costi alla tariffa ASSUNTA dal modulo (0,18% misto
    # con X-Perps, verifica live 06/10/2026), non un numero scritto a mano.
    assert tariffa.giro_misto == pytest.approx(0.0018)

    # Senza costi il risultato e' piu' alto: la differenza E' il costo, non rumore.
    senza = backtest_portafoglio(serie, {"A": ops}, esposizione=1.0,
                                 netto_fn=lambda lordo_lordo: lordo_lordo)
    assert senza.capitale_finale == pytest.approx(1000.0 * (1.0 + lordo), rel=1e-9)
    assert esito.capitale_finale < senza.capitale_finale

    # La tariffa "senza derivati" (okx_eea_spot, scenario di stress) e' piu' cara:
    # il risultato peggiora. Il pedaggio vero del conto e' quello assunto dal modulo.
    stress = M.backtest(serie, cfg, tariffa=get_tariffa("okx_eea_spot"))
    assert stress.capitale_finale < esito.capitale_finale


def test_hook_equipesato_alloca_equity_diviso_k():
    # Con k=2 e un solo candidato si investe meta' equity, non tutta: e' il contratto dichiarato.
    cfg = M.Config(k=2, lookback=1, ribilancio=100)
    serie = {"A": barre([(100.0, 100.0), (100.0, 100.0), (100.0, 100.0),
                         (110.0, 110.0)])}
    ops = M.operazioni_paniere(serie, cfg)
    esito = M.backtest(serie, cfg)
    slip = M.SLIPPAGE_PER_LATO
    tariffa = get_tariffa(M.TARIFFA_ASSUNTA)
    lordo = 110.0 / 100.0 - 1.0
    netto = (1.0 - slip) * (1.0 + lordo) * (1.0 - slip) - 1.0 - tariffa.giro_misto
    assert (ops[0].indice_ingresso, ops[0].indice_uscita) == (2, 3)
    assert esito.capitale_finale == pytest.approx(1000.0 + 500.0 * netto, rel=1e-9)


# ---------------------------------------------------------------------------
# 4) MAI SHORT + TENUTA DEL PANIERE
# ---------------------------------------------------------------------------

def _scenario_tenuta():
    cfg = M.Config(k=2, lookback=1, ribilancio=1)
    serie = {
        "A": da_chiusure([100, 110, 120, 130, 140, 150]),
        "B": da_chiusure([100, 100, 100, 100, 100, 100]),
        "C": da_chiusure([100, 90, 80, 130, 140, 150]),
    }
    return cfg, serie


def test_chi_resta_nel_paniere_non_viene_toccato():
    cfg, serie = _scenario_tenuta()
    ops = M.operazioni_paniere(serie, cfg)
    per = {o.simbolo: o for o in ops}
    assert set(per) == {"A", "B", "C"}
    # A resta in top-k a ogni giro: una sola operazione continua (niente vendita+rientro).
    assert len([o for o in ops if o.simbolo == "A"]) == 1
    assert (per["A"].indice_ingresso, per["A"].indice_uscita) == (2, 5)
    # B esce al ribilanciamento, C entra: solo i cambi, all'apertura di 4.
    assert per["B"].indice_uscita == 4 and per["B"].motivo == "ribilancio"
    assert per["C"].indice_ingresso == 4 and per["C"].motivo == "fine serie"


def test_mai_short_e_posizioni_non_sovrapposte():
    cfg, serie = _scenario_tenuta()
    ops = M.operazioni_paniere(serie, cfg)
    assert ops
    for o in ops:
        assert o.prezzo_ingresso > 0.0 and o.prezzo_uscita > 0.0
        assert o.indice_uscita > o.indice_ingresso           # compra prima, vende dopo
        assert o.ritorno_lordo == pytest.approx(o.prezzo_uscita / o.prezzo_ingresso - 1.0)
    per_simbolo = {}
    for o in ops:
        per_simbolo.setdefault(o.simbolo, []).append(o)
    for lista in per_simbolo.values():
        ordinati = sorted(lista, key=lambda x: x.indice_ingresso)
        for prima, dopo in zip(ordinati, ordinati[1:]):
            assert dopo.indice_ingresso >= prima.indice_uscita
    # Il conto non e' mai piu' investito del suo capitale ne' tiene piu' di k posizioni.
    esito = M.backtest(serie, cfg)
    assert esito.max_esposizione <= 1.0 + 1e-9
    assert esito.max_posizioni <= 2


# ---------------------------------------------------------------------------
# 5) CASO 0 CANDIDATI (E MENO DI k)
# ---------------------------------------------------------------------------

def test_zero_candidati_vale_flat_e_chiude_il_paniere():
    cfg = M.Config(k=2, lookback=1, ribilancio=1)
    # Le chiusure a i=2 sono nulle (nessun candidato valido), ma le APERTURE restano
    # eseguibili: serve a isolare il caso "0 candidati", non a rompere i prezzi.
    serie = {"A": barre([(100.0, 100.0), (100.0, 110.0), (110.0, 0.0),
                         (110.0, 0.0), (110.0, 0.0)]),
             "B": barre([(100.0, 0.0), (100.0, 0.0), (100.0, 0.0),
                         (100.0, 0.0), (100.0, 0.0)])}
    # i=1: A e' l'unico candidato valido -> entra; i=2: nessuna base valida -> target vuoto.
    assert M.composizione_target(serie, 1, cfg) == ["A"]
    assert M.composizione_target(serie, 2, cfg) == []
    ops = M.operazioni_paniere(serie, cfg)
    assert len(ops) == 1
    o = ops[0]
    assert (o.simbolo, o.indice_uscita, o.motivo) == ("A", 3, "ribilancio")
    # Dopo l'uscita non si rientra: un solo ingresso in tutto, e nessuno dopo la chiusura.
    esito = M.backtest(serie, cfg)
    assert esito.operazioni_eseguite == 1
    assert all(x[1].ts_ingresso <= o.ts_uscita for x in esito.esecuzioni)


def test_meno_di_k_candidati_tiene_i_disponibili():
    cfg = M.Config(k=3, lookback=1, ribilancio=10)
    serie = {"A": da_chiusure([100.0, 100.0, 110.0]),
             "B": da_chiusure([0.0, 0.0, 0.0]),      # base non valida
             "C": da_chiusure([0.0, 0.0, 0.0])}      # base non valida
    assert M.composizione_target(serie, 2, cfg) == ["A"]


def test_composizione_vuota_se_la_storia_non_basta():
    cfg = M.Config(k=2, lookback=5, ribilancio=1)
    serie = {"A": da_chiusure([100.0, 100.0, 100.0]),
             "B": da_chiusure([100.0, 100.0, 100.0])}
    assert M.composizione_target(serie, 3, cfg) == []
    assert M.rendimento_momentum(serie["A"], 3, 5) is None
