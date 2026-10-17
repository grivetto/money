"""Test di regressione P25-FIX — guardia sotto-periodo coerente nel KPI settimanale.

REQ-MERL-20261018-007: il run reale su finestra 10->17/10 produceva rendita 7g
+976,04 EUR (resto +990,32 EUR) = falso "+990 EUR" del capitale in transito: il
banco legge tutti i comparti coerentemente solo dal 14/10 (vedi guardia di
ops/report_mensile.py ~178-221). Il KPI non la replicava.

Fixture del caso reale: tests/P25_banco_reale_10_17.jsonl = tail -2500 del banco
vero (MARCODG1 logs/banco_secco.jsonl, 17/10/2026 22:33Z), byte-identico
all'input del run reale difettoso:
  sha256 = ece83219849f68fe429a73a01f3abeec363dbb6121a05023b9355f2c9053411a
  (stesso hash registrato in prove/P25_kpi_2026-10-18.json, campo
  hash_artefatti.banco_secco.jsonl del run reale).

Valori attesi (calcolati con il codice FIXATO, aritmetica deterministica sulla
fixture; procedura riproducibile: parse_banco -> attribuzione(rows, 7*86400) ->
genera_kpi(rows, None, giorni=7)):
  sotto-periodo coerente 2026-10-14T00:04:31Z -> 2026-10-17T22:33:11Z (3,94g su 7)
  delta -3,5444 EUR, cambio -3,1502 EUR, resto -0,3942 EUR
  (coerenti con la voce di registro del report mensile: resto ~-0,46 EUR su
   14->16/10, cambio -3,62 EUR — MAI il falso +990 EUR).

Zero rete, zero chiavi: il fixture e' un dump read-only del banco a secco.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ops"))
sys.path.insert(0, str(ROOT / "tests"))

import _p25_fixtures as fx  # noqa: E402
import kpi_settimanali as kpi  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "P25_banco_reale_10_17.jsonl"

# --- valori attesi sul caso reale (vedi docstring: procedura e coerenza) ---
HASH_FIXTURE_REALE = ("ece83219849f68fe429a73a01f3abeec363dbb6121a05023b9355f2c"
                      "9053411a")
DA_REALE = "2026-10-14T00:04:31Z"      # sotto-periodo coerente (copertura piena)
A_REALE = "2026-10-17T22:33:11Z"       # ultimo campione del banco
FINESTRA_DA_REALE = "2026-10-10T22:36:27Z"  # inizio finestra 7g richiesta
TS_DA_REALE = 1791936271.0
TS_A_REALE = 1792276391.0
DELTA_REALE = -3.5444049999998697
CAMBIO_REALE = -3.150182416242927
RESTO_REALE = -0.39422258375694286
RATE_DA_REALE = 0.8929699996600878
RATE_A_REALE = 0.8904000000896141
CAPITALE_REALE = 1096.44559
GIORNI_EFF_REALE = (TS_A_REALE - TS_DA_REALE) / 86400.0  # 3,9366 g
MENSILIZZATA_REALE = RESTO_REALE * 30.0 / GIORNI_EFF_REALE  # -3,0043 EUR/mese

# numeri del difetto (MAI piu' questi valori)
FALSO_DELTA = 976.041389
FALSO_RESTO = 990.3222171374418


@pytest.fixture(scope="module")
def banco_reale() -> list[dict]:
    testo = FIXTURE.read_text(encoding="utf-8")
    return kpi.parse_banco(testo)


# ---------------------------------------------------------------------------
# Caso reale 10->17/10: sotto-periodo ridotto, MAI +990
# ---------------------------------------------------------------------------

def test_fixture_reale_byte_identica_al_run_difettoso():
    h = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    assert h == HASH_FIXTURE_REALE, (
        "fixture diversa dall'input del run reale difettoso: la regressione non "
        "riproduce il difetto")


def test_regressione_attribuzione_sotto_periodo_coerente(banco_reale):
    attr = kpi.attribuzione(banco_reale, 7 * 86400)
    assert attr is not None
    assert attr.get("sotto_periodo") is True
    # il sotto-periodo parte il 14/10 (copertura comparti piena), non il 10/10
    assert attr["da"] == DA_REALE
    assert attr["a"] == A_REALE
    assert attr["ts_da"] == pytest.approx(TS_DA_REALE, rel=1e-12)
    assert attr["ts_a"] == pytest.approx(TS_A_REALE, rel=1e-12)
    # finestra richiesta dichiarata: 10/10 22:36 -> 17/10 22:33
    assert attr["finestra_richiesta"]["da"] == FINESTRA_DA_REALE
    assert attr["finestra_richiesta"]["a"] == A_REALE
    # valori attesi (metodologia watch_alerts sul sotto-periodo)
    assert attr["delta_eur"] == pytest.approx(DELTA_REALE, rel=1e-9)
    assert attr["cambio_eur"] == pytest.approx(CAMBIO_REALE, rel=1e-9)
    assert attr["resto_eur"] == pytest.approx(RESTO_REALE, rel=1e-9)
    assert attr["rate_da"] == pytest.approx(RATE_DA_REALE, rel=1e-9)
    assert attr["rate_a"] == pytest.approx(RATE_A_REALE, rel=1e-9)


def test_regressione_mai_falso_990(banco_reale):
    attr = kpi.attribuzione(banco_reale, 7 * 86400)
    # guardie esplicite contro il difetto: il delta/resto NON sono il +976/+990
    # del capitale in transito
    assert attr["delta_eur"] != pytest.approx(FALSO_DELTA, abs=1.0)
    assert attr["resto_eur"] != pytest.approx(FALSO_RESTO, abs=1.0)
    assert attr["delta_eur"] < 10.0
    assert attr["resto_eur"] < 10.0


def test_regressione_kpi_mensilizza_sul_sotto_periodo(banco_reale):
    k = kpi.genera_kpi(banco_reale, None, giorni=7, comando="test")
    assert k["rendita"]["stato"] == "ok"
    assert k["rendita"]["resto_eur"] == pytest.approx(RESTO_REALE, rel=1e-9)
    per = k["periodo_effettivo"]
    assert per["sotto_periodo"] is True
    assert per["da"] == DA_REALE and per["a"] == A_REALE
    # nel periodo_effettivo il valore e' arrotondato a 3 decimali (3,937)
    assert per["giorni_effettivi"] == pytest.approx(GIORNI_EFF_REALE, abs=1e-3)
    assert per["giorni_richiesti"] == 7
    assert "3,9g su 7" in per["nota"]
    # mensilizzazione sul sotto-periodo effettivo (30/3,94), NON su 7g
    be = k["break_even"]
    assert be["giorni_effettivi"] == pytest.approx(GIORNI_EFF_REALE, rel=1e-9)
    assert be["mensilizzata_eur_mese"] == pytest.approx(MENSILIZZATA_REALE, rel=1e-9)
    # resto negativo -> capitale di break-even non calcolabile (regola esistente)
    assert be["stato"] == "dati insufficienti"
    assert be["capitale_break_even_eur"] is None
    # nota esplicita del sotto-periodo presente anche con stato insufficiente
    assert "sotto-periodo 3,9g su 7" in be["nota"]
    assert k["capitale_attuale_eur"] == pytest.approx(CAPITALE_REALE, rel=1e-9)


def test_regressione_testo_senza_numeri_falsi(banco_reale):
    k = kpi.genera_kpi(banco_reale, None, giorni=7, comando="test")
    testo = kpi.componi_testo(k)
    assert "sotto-periodo coerente 3,9g su 7g richiesti" in testo
    assert "Rendita netta (sotto-periodo 3,9g su 7): -3.54 €" in testo
    assert "cambio -3.15 €" in testo and "resto -0.39 €" in testo
    assert "nota: sotto-periodo 3,9g su 7" in testo
    assert "976,04" not in testo
    assert "990,32" not in testo


# ---------------------------------------------------------------------------
# Finestra interamente coerente -> comportamento INVARIATO (fixture sintetiche
# P25, valori attesi a mano)
# ---------------------------------------------------------------------------

def test_coerente_attribuzione_invariata():
    rows = kpi.parse_banco(fx.testo_banco_2settimane())
    attr = kpi.attribuzione(rows, 7 * 86400)
    assert attr is not None
    assert "sotto_periodo" not in attr          # nessuna restrizione
    assert attr["delta_eur"] == pytest.approx(fx.DELTA_ATTESO, rel=1e-9)
    assert attr["cambio_eur"] == pytest.approx(fx.CAMBIO_ATTESO, rel=1e-9)
    assert attr["resto_eur"] == pytest.approx(fx.RESTO_ATTESO, rel=1e-9)


def test_coerente_kpi_mensilizzazione_30_7_invariata():
    rows = kpi.parse_banco(fx.testo_banco_2settimane())
    k = kpi.genera_kpi(rows, None, giorni=7, comando="test")
    assert k["rendita"]["stato"] == "ok"
    assert "sotto_periodo" not in k["rendita"]
    per = k["periodo_effettivo"]
    assert per.get("sotto_periodo") is not True
    assert per["giorni_effettivi"] == pytest.approx(7.0, rel=1e-12)
    be = k["break_even"]
    assert be["stato"] == "ok"
    assert be["mensilizzata_eur_mese"] == pytest.approx(
        fx.RESTO_ATTESO * 30 / 7, rel=1e-9)
    assert "nota" not in be
    testo = kpi.componi_testo(k)
    assert "Rendita netta 7g: +11.86 € (cambio +10.01 € · resto +1.85 €)" in testo
    assert "rendita mensilizzata (resto × 30/7)" in testo


# ---------------------------------------------------------------------------
# Caso sintetico deterministico: finestra che attraversa comparti non coerenti
# -> sotto-periodo ridotto (numeri calcolati a mano, 2g esatti di sotto-periodo)
# ---------------------------------------------------------------------------

def _banco_attraversa_non_coerente(t_fine: float) -> list[dict]:
    """7g di banco a 5': primi 5g solo funding (rate 0,92), ultimi 2g funding+
    savings (rate savings 0,93->0,931 lineare). Sotto-periodo coerente = 2g."""
    righe = []
    t0 = t_fine - 7 * 86400
    i = 0
    while True:
        ts = t0 + i * 300
        if ts > t_fine:
            break
        d = {"timestamp": fx._iso(ts)}
        if ts < t_fine - 2 * 86400:
            d.update({"equity_eur": 970.0, "equity_funding_eur": 920.0,
                      "saldi_funding": {"USDC": 1000.0}})
        else:
            f = (ts - (t_fine - 2 * 86400)) / (2 * 86400)
            r_s = 0.93 + f * 0.001
            d.update({"equity_eur": 920.0 + 2000.0 * r_s,
                      "equity_funding_eur": 920.0,
                      "equity_savings_eur": 2000.0 * r_s,
                      "saldi_funding": {"USDC": 1000.0},
                      "saldi_savings": {"USDC": 2000.0}})
        righe.append(d)
        i += 1
    return righe


def test_attraversa_non_coerente_sotto_periodo_ridotto():
    rows = _banco_attraversa_non_coerente(fx.T_FINE)
    attr = kpi.attribuzione(rows, 7 * 86400)
    assert attr is not None
    assert attr.get("sotto_periodo") is True
    # sotto-periodo = ultimi 2g (copertura piena), non l'intera finestra
    assert attr["da"] == fx._iso(fx.T_FINE - 2 * 86400)
    assert attr["a"] == fx._iso(fx.T_FINE)
    # valori attesi a mano: delta = 2000*(0,931-0,93) = 2,0;
    # cambio = (0,931-0,93) x (3000+3000)/2 = 3,0; resto = -1,0
    assert attr["delta_eur"] == pytest.approx(2.0, rel=1e-9)
    assert attr["cambio_eur"] == pytest.approx(3.0, rel=1e-9)
    assert attr["resto_eur"] == pytest.approx(-1.0, rel=1e-9)
    # 2g esatti NON sono < 2g: la rendita resta calcolabile (soglia inclusiva)
    k = kpi.genera_kpi(rows, None, giorni=7, comando="test")
    assert k["rendita"]["stato"] == "ok"
    assert k["periodo_effettivo"]["giorni_effettivi"] == pytest.approx(2.0, rel=1e-12)
    assert k["break_even"]["mensilizzata_eur_mese"] == pytest.approx(
        -1.0 * 30 / 2.0, rel=1e-9)


# ---------------------------------------------------------------------------
# Sotto-periodo coerente < 2g -> dati insufficienti (mai mensilizzare un
# campione incoerente/corto)
# ---------------------------------------------------------------------------

def _banco_sotto_periodo_corto(t_fine: float) -> list[dict]:
    """7g a 5': copertura piena (funding+savings) solo negli ULTIMI 1,5g."""
    righe = []
    t0 = t_fine - 7 * 86400
    i = 0
    while True:
        ts = t0 + i * 300
        if ts > t_fine:
            break
        d = {"timestamp": fx._iso(ts)}
        if ts < t_fine - 1.5 * 86400:
            d.update({"equity_eur": 970.0, "equity_funding_eur": 920.0,
                      "saldi_funding": {"USDC": 1000.0}})
        else:
            d.update({"equity_eur": 1850.0, "equity_funding_eur": 920.0,
                      "equity_savings_eur": 930.0,
                      "saldi_funding": {"USDC": 1000.0},
                      "saldi_savings": {"USDC": 1000.0}})
        righe.append(d)
        i += 1
    return righe


def test_sotto_periodo_inferiore_2g_dati_insufficienti():
    rows = _banco_sotto_periodo_corto(fx.T_FINE)
    attr = kpi.attribuzione(rows, 7 * 86400)
    assert attr is not None
    assert attr["stato"] == "dati insufficienti"
    assert "1,5g" in attr["motivo"] and "2g" in attr["motivo"]
    # nessun numero di rendita esposto su un campione incoerente/corto
    for campo in ("delta_eur", "cambio_eur", "resto_eur"):
        assert campo not in attr
    k = kpi.genera_kpi(rows, None, giorni=7, comando="test")
    assert k["rendita"]["stato"] == "dati insufficienti"
    assert k["break_even"]["stato"] == "dati insufficienti"
    assert k["periodo_effettivo"]["stato"] == "dati insufficienti"
    testo = kpi.componi_testo(k)
    assert "Rendita netta 7g: dati insufficienti" in testo
    assert "1,5g" in k["rendita"]["motivo"] and "2g" in k["rendita"]["motivo"]


def test_soglia_2g_giorni_min_personalizzabile():
    # con giorni_min=1.0 lo stesso sotto-periodo di 1,5g e' accettato
    rows = _banco_sotto_periodo_corto(fx.T_FINE)
    attr = kpi.attribuzione(rows, 7 * 86400, giorni_min=1.0)
    assert attr is not None
    assert "stato" not in attr or attr["stato"] != "dati insufficienti"
    assert attr["delta_eur"] == pytest.approx(0.0, rel=1e-9)  # equity costante
