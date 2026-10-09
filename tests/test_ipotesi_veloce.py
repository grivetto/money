"""Test dello screener: la logica di verdetto e la validazione dell'ipotesi.

Lo screener non reimplementa il motore (usa `money.ricerca.scansione`): qui si testa
SOLO cio' che aggiunge — la regola PROMOSSA/RESPINTA e il fail-closed sull'input.
Nessuna rete: le "selezioni" sono dizionari sintetici.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

RADICE = Path(__file__).resolve().parents[1]


def _carica():
    for p in ("src", "."):
        c = str(RADICE / p)
        if c not in sys.path:
            sys.path.insert(0, c)
    spec = importlib.util.spec_from_file_location("_ipv", RADICE / "scripts" / "ipotesi_veloce.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


IPV = _carica()


def _sel(*, n_oos=50, exp_oos=0.01, t_oos=2.0, dsr=0.98, n_train=80, exp_train=0.02):
    return {
        "chiave": "famiglia(x=1)", "simbolo": "BTC/USDT",
        "train": {"n": n_train, "expectancy": exp_train},
        "oos": {"n": n_oos, "expectancy": exp_oos, "t_stat": t_oos},
        "dsr_oos": dsr,
    }


def test_promossa_quando_tutto_ok():
    v, motivo = IPV.verdetto(_sel(), min_op=30, soglia_dsr=0.95)
    assert v == "PROMOSSA", motivo


def test_respinta_campione_insufficiente():
    v, _ = IPV.verdetto(_sel(n_oos=10), min_op=30, soglia_dsr=0.95)
    assert v == "RESPINTA"


def test_respinta_expectancy_non_positiva():
    v, m = IPV.verdetto(_sel(exp_oos=-0.001), min_op=30, soglia_dsr=0.95)
    assert v == "RESPINTA" and "expectancy" in m


def test_respinta_t_stat_non_positivo():
    v, m = IPV.verdetto(_sel(t_oos=-0.5), min_op=30, soglia_dsr=0.95)
    assert v == "RESPINTA" and "t-stat" in m


def test_respinta_dsr_sotto_soglia():
    v, m = IPV.verdetto(_sel(dsr=0.5), min_op=30, soglia_dsr=0.95)
    assert v == "RESPINTA" and "DSR" in m


def test_dsr_normalizzato_da_dict_o_float():
    """Il motore espone `dsr_oos` in due forme: entrambe devono funzionare."""
    assert IPV._dsr_valore({"dsr_oos": 0.9}) == 0.9
    assert IPV._dsr_valore({"dsr_oos": {"dsr": 0.8}}) == 0.8
    assert IPV._dsr_valore({"dsr_oos": None}) is None


def test_valida_rifiuta_ipotesi_incompleta():
    with pytest.raises(SystemExit):
        IPV.valida({"nome": "x"})  # mancano simboli/periodo/configs


def test_valida_rifiuta_famiglia_ignota():
    ip = {"nome": "x", "timeframe": "1d", "inizio": "2020-10-01", "fine": "2026-10-08",
          "confine": "2024-06-01", "simboli": ["BTC/USDT"],
          "configs": [{"famiglia": "magia", "x": 1}]}
    with pytest.raises(SystemExit):
        IPV.valida(ip)


def test_valida_accetta_ipotesi_corretta():
    ip = {"nome": "x", "timeframe": "1d", "inizio": "2020-10-01", "fine": "2026-10-08",
          "confine": "2024-06-01", "simboli": ["BTC/USDT"],
          "configs": [{"famiglia": "mom_abs", "L": 20}]}
    IPV.valida(ip)  # non solleva
