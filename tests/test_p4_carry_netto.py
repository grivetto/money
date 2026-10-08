"""Test del misuratore di carry funding (spec coda_catena/P4_funding_carry.md §5)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from money.carry_netto import (  # noqa: E402
    MS_GIORNO,
    netto_annuo_pct,
    osservazioni_indipendenti,
    verdetto,
)

T0 = (1_700_000_000_000 // MS_GIORNO) * MS_GIORNO  # ms, mezzanotte UTC (buckets di giorno puliti)
GIORNI = 30
PERIODI = 3


def _serie(funding_per_giorno: dict[int, list[float]] | float, giorni: int = GIORNI):
    """Serie sintetica: per ogni giorno, 3 osservazioni a 8h."""
    serie = []
    for g in range(giorni):
        valori = (
            [funding_per_giorno] * PERIODI
            if isinstance(funding_per_giorno, (int, float))
            else funding_per_giorno.get(g, [0.0] * PERIODI)
        )
        for i, f in enumerate(valori):
            serie.append((T0 + g * MS_GIORNO + i * 8 * 3_600_000, float(f)))
    return serie


def test_t1_uccisione_con_funding_zero():
    """T1: con funding a zero il netto deve essere <= 0 e il verdetto `archiviato`."""
    serie = _serie(0.0)
    netto = netto_annuo_pct(serie)
    assert netto["lordo_annuo_pct"] == pytest.approx(0.0, abs=1e-9)
    assert netto["netto_annuo_pct"] <= 0
    assert verdetto(netto) == "archiviato"


def test_t2_monotonia_dei_costi():
    """T2: aumentando il costo di ciclo il netto deve diminuire."""
    serie = _serie(0.0002)
    netti = [netto_annuo_pct(serie, costo_ciclo=c)["netto_annuo_pct"] for c in (0.0, 0.0007, 0.002)]
    assert netti[0] > netti[1] > netti[2]


def test_t3_oos_di_segno_opposto():
    """T3: se il netto OOS cambia segno il verdetto e' `insufficiente`."""
    serie = _serie(0.0002)
    netto = netto_annuo_pct(serie)
    netto_promosso = dict(netto, netto_annuo_pct=12.0, netto_oos_pct=3.0)
    assert verdetto(netto_promosso) == "promosso"
    netto_incoerente = dict(netto, netto_annuo_pct=12.0, netto_oos_pct=-1.0)
    assert verdetto(netto_incoerente) == "insufficiente"


def test_t4_ci_contiene_la_media():
    """T4: con seed fisso il CI95 e' deterministico e contiene il lordo puntuale."""
    serie = _serie(0.0002)
    netto = netto_annuo_pct(serie)
    lo, hi = netto["ci95"]
    assert lo <= netto["lordo_annuo_pct"] <= hi
    assert netto_annuo_pct(serie)["ci95"] == netto["ci95"]  # deterministico


def test_osservazioni_indipendenti():
    serie = _serie(0.0001)
    assert osservazioni_indipendenti(serie) == GIORNI
    # un giorno con sole 2 osservazioni non conta come indipendente
    corta = serie[:-1]
    corta[-1] = (corta[-1][0] + 3_600_000, corta[-1][1])
    assert osservazioni_indipendenti(corta) >= GIORNI - 1


def test_soglia_promozione():
    """Sopra soglia (8%) promosso, sotto soglia insufficiente."""
    serie = _serie(0.0002)  # lordo ~21.9% -> netto ~20.2% > 8%
    netto = netto_annuo_pct(serie)
    assert verdetto(netto) == "promosso"
    assert verdetto(netto, soglia_promozione=0.50) == "insufficiente"
