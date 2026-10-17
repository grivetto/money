"""Test per money.ricerca.carry_delta_neutral"""
import pytest
import json
from money.ricerca.carry_delta_neutral import (
    DEFAULT_CONFIG,
    carica_config,
    simula_carry_delta_neutral,
    TradeRecord,
    PosizioneAperta,
    EsitoCarry,
)


def test_default_config():
    """Verifica che la configurazione di default contenga le chiavi attese."""
    expected_keys = {
        "simboli",
        "perpetual_suffix",
        "timeframe_funding",
        "basis_entry_bps",
        "basis_exit_bps",
        "delta_threshold_pct",
        "slippage_per_side",
        "commission_taker",
        "commission_maker",
        "leverage_max",
        "margin_init_pct",
        "min_operazioni_train",
        "capitale_riferimento_eur",
    }
    assert set(DEFAULT_CONFIG.keys()) == expected_keys
    assert DEFAULT_CONFIG["simboli"] == ["BTC/USDT", "ETH/USDT"]
    assert DEFAULT_CONFIG["capitale_riferimento_eur"] == 1000.0


def test_carica_config_senza_file(tmp_path):
    """Se il file non esiste, deve tornare la configurazione di default."""
    cfg = carica_config(None)
    assert cfg == DEFAULT_CONFIG


def test_carica_config_con_file(tmp_path):
    """Se esiste un file JSON, deve sovrascrivere i valori."""
    config_file = tmp_path / "test_config.json"
    config_file.write_text(json.dumps({"basis_entry_bps": 10.0, "simboli": ["SOL/USDT"]}))
    cfg = carica_config(config_file)
    assert cfg["basis_entry_bps"] == 10.0
    assert cfg["simboli"] == ["SOL/USDT"]
    # le altre chiavi devono rimanere quelle di default
    assert cfg["capitale_riferimento_eur"] == 1000.0


def test_trade_record_creation():
    """Creazione di un TradeRecord con valori di esempio."""
    tr = TradeRecord(
        timestamp=1700000000000,
        simbolo="BTC/USDT",
        lato="long",
        asset="spot",
        prezzo=27000.0,
        size=0.01,
        notional=270.0,
        commissione=0.135,
        slippage_costo=0.054,
        totale_costo=0.189,
        funding_accrued=0.0,
        pnl=0.0,
        nota="apertura",
    )
    assert tr.simbolo == "BTC/USDT"
    assert tr.lato == "long"
    assert tr.prezzo == 27000.0
    assert tr.size == 0.01
    assert tr.notional == 270.0
    assert tr.totale_costo == 0.189


def test_posizione_aperta_creation():
    """Creazione di una PosizioneAperta."""
    trade_spot = TradeRecord(1700000000000, "BTC/USDT", "long", "spot", 27000.0, 0.01, 270.0, 0.135, 0.054, 0.189, 0.0, 0.0, "apertura spot")
    trade_perp = TradeRecord(1700000000000, "BTC/USDT", "short", "perp", 27000.0, 0.01, 270.0, 0.135, 0.054, 0.189, 0.0, 0.0, "apertura perp")
    pos = PosizioneAperta(
        simbolo="BTC/USDT",
        timestamp_apertura=1700000000000,
        size=0.01,
        prezzo_spot_apertura=27000.0,
        prezzo_perp_apertura=27000.0,
        notional=270.0,
        margine_impegnato=13.5,  # 270 * 0.05
        trade_apertura_spot=trade_spot,
        trade_apertura_perp=trade_perp,
    )
    assert pos.simbolo == "BTC/USDT"
    assert pos.size == 0.01
    assert pos.notional == 270.0
    assert pos.margine_impegnato == 13.5
    assert pos.funding_accumulato == 0.0


def test_simula_not_implemented():
    """La funzione di simulazione deve sollevare NotImplementedError finché non completata."""
    with pytest.raises(NotImplementedError):
        simula_carry_delta_neutral(
            data_inizio="2024-01-01",
            data_fine="2024-12-31",
        )


if __name__ == "__main__":
    # Esecuzione semplice dei test senza pytest
    test_default_config()
    test_carica_config_senza_file(None)
    test_carica_config_con_file(None)  # will skip, but okay
    test_trade_record_creation()
    test_posizione_aperta_creation()
    try:
        test_simula_not_implemented()
        print("TEST PASSED: simula raises NotImplementedError")
    except AssertionError as e:
        print(f"TEST FAILED: {e}")
    print("All tests completed")
