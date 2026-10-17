"""Test offline P25 — KPI settimanali (ops/kpi_settimanali.py).

Zero rete, zero chiavi: solo fixture sintetiche (2 settimane) con numeri noti e
valori attesi calcolati a mano (vedi _p25_fixtures.py). Ogni test usa assert sui
valori attesi: senza l'implementazione i test non possono passare.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ops"))
sys.path.insert(0, str(ROOT / "tests"))

import _p25_fixtures as fx  # noqa: E402
import kpi_settimanali as kpi  # noqa: E402


# ---------------------------------------------------------------------------
# Attribuzione 7g — valori attesi a mano
# ---------------------------------------------------------------------------

def test_attribuzione_7g_scomposizione_attesa():
    rows = kpi.parse_banco(fx.testo_banco_2settimane())
    attr = kpi.attribuzione(rows, 7 * 86400)
    assert attr is not None
    assert attr["delta_eur"] == pytest.approx(fx.DELTA_ATTESO, rel=1e-9)      # 11.86
    assert attr["cambio_eur"] == pytest.approx(fx.CAMBIO_ATTESO, rel=1e-9)    # 10.01
    assert attr["resto_eur"] == pytest.approx(fx.RESTO_ATTESO, rel=1e-9)      # 1.85


def test_attribuzione_dichiara_periodo_effettivo():
    rows = kpi.parse_banco(fx.testo_banco_2settimane())
    attr = kpi.attribuzione(rows, 7 * 86400)
    assert attr is not None
    # il primo campione >= t_fine−7g è ESATTAMENTE la riga a t_fine−7g (step 300 s)
    assert attr["ts_da"] == pytest.approx(fx.T_FINE - fx.SETTIMANA_S, rel=1e-12)
    assert attr["ts_a"] == pytest.approx(fx.T_FINE, rel=1e-12)
    assert attr["da"].endswith("Z") and attr["a"].endswith("Z")


def test_attribuzione_meno_di_2_campioni_none():
    assert kpi.attribuzione([], 7 * 86400) is None
    una = fx.riga_banco(fx.T_FINE, 1000.0, 0.93)
    assert kpi.attribuzione([una], 7 * 86400) is None


def test_attribuzione_senza_rate_none():
    r1 = {"timestamp": "2026-10-11T09:00:00Z", "equity_eur": 100.0}
    r2 = {"timestamp": "2026-10-18T09:00:00Z", "equity_eur": 101.0}
    assert kpi.attribuzione([r1, r2], 7 * 86400) is None


def test_rate_implicito_fallback_funding():
    d = {"equity_funding_eur": 92.0, "saldi_funding": {"USDC": 100.0}}
    assert kpi.rate_implicito(d) == pytest.approx(0.92, rel=1e-12)


# ---------------------------------------------------------------------------
# Fee 7g — valori attesi a mano
# ---------------------------------------------------------------------------

def test_fee_somma_e_conteggi_attesi():
    righe = kpi.parse_ledger(fx.testo_fee_7g())
    t_da = fx.T_FINE - fx.SETTIMANA_S
    out = kpi.fee_da_ledger(righe, t_da, fx.T_FINE, fx.R1)
    assert out["stato"] == "ok"
    assert out["somma_eur"] == pytest.approx(fx.FEE_SOMMA_ATTESA, rel=1e-12)  # 0.844
    assert out["incluse"] == 4
    assert out["escluse_ccy"] == 1      # BTC: valuta non convertibile
    assert out["fuori_periodo"] == 1    # 0.40 USDC a 13 giorni


def test_fee_ledger_mancante_dati_insufficienti():
    out = kpi.fee_da_ledger(None, fx.T_FINE - fx.SETTIMANA_S, fx.T_FINE, fx.R1)
    assert out["stato"] == "dati insufficienti"
    assert "assente" in out["motivo"]


def test_fee_ledger_vuoto_dati_insufficienti():
    out = kpi.fee_da_ledger([], fx.T_FINE - fx.SETTIMANA_S, fx.T_FINE, fx.R1)
    assert out["stato"] == "dati insufficienti"
    assert "vuoto" in out["motivo"]


def test_fee_senza_rate_usdc_escluse_eur_incluse():
    righe = kpi.parse_ledger(fx.testo_fee_7g())
    out = kpi.fee_da_ledger(righe, fx.T_FINE - fx.SETTIMANA_S, fx.T_FINE, None)
    # EUR 0.10 inclusa; USDC 0.50 e USD 0.30 escluse (niente tasso); BTC esclusa;
    # USDC fee 0 inclusa (sono 0)
    assert out["somma_eur"] == pytest.approx(0.10, rel=1e-12)
    assert out["incluse"] == 2
    assert out["escluse_ccy"] == 3


def test_fee_riga_non_convertibile_conteggiata_a_parte():
    rows = kpi.parse_banco(fx.testo_banco_2settimane())
    k = kpi.genera_kpi(rows, kpi.parse_ledger(fx.testo_fee_7g()),
                       giorni=7, comando="test")
    testo = kpi.componi_testo(k)
    assert "escluse 1 voce (valuta non convertibile)" in testo
    assert "Fee 7g: 0.84 €" in testo


# ---------------------------------------------------------------------------
# Break-even — valori attesi a mano
# ---------------------------------------------------------------------------

def test_break_even_valori_attesi():
    be = kpi.break_even(fx.RESTO_ATTESO, fx.U1 * fx.R1, 16.0)
    mensilizzata_attesa = fx.RESTO_ATTESO * 30 / 7
    assert be["stato"] == "ok"
    assert be["mensilizzata_eur_mese"] == pytest.approx(mensilizzata_attesa, rel=1e-12)
    assert be["distanza_eur_mese"] == pytest.approx(mensilizzata_attesa - 16.0, rel=1e-12)
    assert be["capitale_break_even_eur"] == pytest.approx(
        16.0 * (fx.U1 * fx.R1) / mensilizzata_attesa, rel=1e-12)  # ≈ 1880.51
    assert be["capitale_attuale_eur"] == pytest.approx(fx.U1 * fx.R1, rel=1e-12)  # 931.86


def test_break_even_resto_non_positivo_non_calcolabile():
    be = kpi.break_even(-1.0, 931.86, 16.0)
    assert be["stato"] == "dati insufficienti"
    assert be["capitale_break_even_eur"] is None
    assert be["distanza_eur_mese"] == pytest.approx(-1.0 * 30 / 7 - 16.0, rel=1e-12)


def test_break_even_capitale_zero_non_calcolabile():
    be = kpi.break_even(1.85, 0.0, 16.0)
    assert be["stato"] == "dati insufficienti"


# ---------------------------------------------------------------------------
# Costi mensili — default e sovrascrittura
# ---------------------------------------------------------------------------

def test_costi_default_roadmap_d1():
    c = kpi.costi_mensili(None)
    assert c["valore_eur_mese"] == 16.0
    assert "ROADMAP D1" in c["fonte"]


def test_costi_sovrascritti_da_report_costi():
    c = kpi.costi_mensili('{"totale_mese_eur": 14.5, "voci": []}')
    assert c["valore_eur_mese"] == 14.5
    assert "report_costi.json" in c["fonte"]
    be = kpi.break_even(fx.RESTO_ATTESO, fx.U1 * fx.R1, c["valore_eur_mese"])
    assert be["costi_eur_mese"] == 14.5
    assert be["capitale_break_even_eur"] == pytest.approx(
        14.5 * (fx.U1 * fx.R1) / (fx.RESTO_ATTESO * 30 / 7), rel=1e-12)


def test_costi_report_invalido_usa_default():
    assert kpi.costi_mensili('{"totale_mese_eur": "abc"}')["valore_eur_mese"] == 16.0
    assert kpi.costi_mensili("non json")["valore_eur_mese"] == 16.0
    assert "nota" in kpi.costi_mensili("non json")


# ---------------------------------------------------------------------------
# Composizione end-to-end (JSON + testo) su fixture sintetiche
# ---------------------------------------------------------------------------

def test_genera_kpi_json_completo():
    rows = kpi.parse_banco(fx.testo_banco_2settimane())
    k = kpi.genera_kpi(rows, kpi.parse_ledger(fx.testo_fee_7g()),
                       giorni=7, comando="test",
                       hash_artefatti={"banco_secco.jsonl": "abc"})
    assert k["tipo"] == "kpi_settimanali"
    assert k["rendita"]["stato"] == "ok"
    assert k["rendita"]["resto_eur"] == pytest.approx(fx.RESTO_ATTESO, rel=1e-9)
    assert k["fee"]["stato"] == "ok"
    assert k["fee"]["somma_eur"] == pytest.approx(fx.FEE_SOMMA_ATTESA, rel=1e-12)
    assert k["break_even"]["stato"] == "ok"
    assert k["capitale_attuale_eur"] == pytest.approx(fx.U1 * fx.R1, rel=1e-9)
    assert k["costi"]["valore_eur_mese"] == 16.0
    assert k["periodo_effettivo"]["da"].endswith("Z")
    assert k["hash_artefatti"] == {"banco_secco.jsonl": "abc"}


def test_genera_kpi_fee_mancante_nessun_numero_inventato():
    rows = kpi.parse_banco(fx.testo_banco_2settimane())
    k = kpi.genera_kpi(rows, None, giorni=7, comando="test")
    assert k["fee"]["stato"] == "dati insufficienti"
    assert "somma_eur" not in k["fee"]
    testo = kpi.componi_testo(k)
    assert "Fee 7g: dati insufficienti" in testo
    # la rendita resta calcolabile (il banco c'è)
    assert k["rendita"]["stato"] == "ok"


def test_genera_kpi_banco_vuoto_tutto_insufficiente():
    k = kpi.genera_kpi([], None, giorni=7, comando="test")
    assert k["rendita"]["stato"] == "dati insufficienti"
    assert k["fee"]["stato"] == "dati insufficienti"
    assert k["break_even"]["stato"] == "dati insufficienti"
    testo = kpi.componi_testo(k)
    assert "dati insufficienti" in testo


def test_componi_testo_righe_chiave():
    rows = kpi.parse_banco(fx.testo_banco_2settimane())
    k = kpi.genera_kpi(rows, kpi.parse_ledger(fx.testo_fee_7g()),
                       giorni=7, comando="test")
    testo = kpi.componi_testo(k)
    assert "📈 Denaro — KPI settimanali (lunedì)" in testo
    assert "Periodo effettivo:" in testo
    assert "Rendita netta 7g: +11.86 € (cambio +10.01 € · resto +1.85 €)" in testo
    assert "Break-even:" in testo
    assert "distanza dal break-even" in testo
    assert "capitale break-even stimato" in testo
    assert "formula:" in testo
    assert "limite: campione corto" in testo
