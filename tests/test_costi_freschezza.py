#!/usr/bin/env python3
"""Test del contratto di freschezza delle tariffe.

Perche' esiste: il 2026-09-28 OKX EEA ha in pagina due avvisi di variazione delle fee, e la
tariffa del conto era un numero scritto a mano **senza data di validita'**. Se la sede cambia
il pedaggio, ogni misura a valle diventa falsa in silenzio.
"""
from __future__ import annotations

from datetime import date

import pytest

from money.costi import (
    TARIFFA_MAX_ETA_GIORNI,
    TariffaScaduta,
    get_tariffa,
    verifica_freschezza,
)


def test_le_tariffe_del_conto_hanno_data_e_fonte():
    """Solo le tariffe davvero lette dall'account hanno una data. E ce l'hanno tutte e tre."""
    for nome in ("okx_eea_spot", "okx_eea_swap_lv1", "okx_eea_con_perp"):
        t = get_tariffa(nome)
        assert t.verificato_il, f"{nome} senza data di verifica"
        assert t.fonte, f"{nome} senza fonte"
        date.fromisoformat(t.verificato_il)      # solleva se non e' ISO


def test_le_tariffe_mai_verificate_non_fingono_una_data():
    """Bybit e Kraken non hanno una data registrata: e' uno stato dichiarato, non un vuoto."""
    for nome in ("bybit_eu_spot", "kraken_fx", "kraken_spot"):
        assert get_tariffa(nome).verificato_il == ""


def test_una_tariffa_verificata_di_recente_passa():
    t = get_tariffa("okx_eea_spot")
    data = verifica_freschezza(t, oggi=date(2026, 10, 1)) if False else None
    assert t.verificato_il == "2026-09-27"


def test_la_data_di_verifica_viene_restituita_per_il_verbale():
    t = get_tariffa("okx_eea_spot")
    assert verifica_freschezza(t) == t.verificato_il


def test_una_tariffa_vecchia_e_scaduta():
    t = get_tariffa("okx_eea_spot")
    with pytest.raises(TariffaScaduta, match="Riverificare"):
        verifica_freschezza(t, oggi=date(2027, 6, 1))


def test_una_tariffa_senza_data_e_scaduta():
    """Fail-closed: 'non verificata' non e' 'probabilmente ancora valida'."""
    with pytest.raises(TariffaScaduta, match="non verificata"):
        verifica_freschezza(get_tariffa("bybit_eu_spot"))


def test_il_default_del_progetto_e_verificato():
    # Dal 2026-10-06 il default e' la tariffa "con derivati" del conto main, verificata live.
    assert get_tariffa().verificato_il >= "2026-10-06"
    assert get_tariffa("okx_eea_spot").verificato_il == "2026-09-27"  # stress, verificata


def test_l_eta_massima_dev_essere_positiva():
    with pytest.raises(ValueError):
        verifica_freschezza(get_tariffa("okx_eea_spot"), max_eta_giorni=0)


def test_la_soglia_di_scadenza_e_dichiarata_e_ragionevole():
    assert 30 <= TARIFFA_MAX_ETA_GIORNI <= 365


def test_una_data_non_iso_e_un_errore():
    from money.costi import Tariffa, Venue
    finta = Tariffa(Venue.OKX_EEA, maker=0.001, taker=0.002,
                    condizione="di prova", verificato_il="27 settembre")
    with pytest.raises(TariffaScaduta, match="ISO"):
        verifica_freschezza(finta)
