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
        "dsr_selezione": dsr,
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
    """Chiave corrente (`dsr_selezione`) in due forme + fallback sui vecchi artefatti."""
    assert IPV._dsr_valore({"dsr_selezione": 0.9}) == 0.9
    assert IPV._dsr_valore({"dsr_selezione": {"dsr": 0.8}}) == 0.8
    assert IPV._dsr_valore({"dsr_selezione": None}) is None
    assert IPV._dsr_valore({"dsr_oos": 0.85}) == 0.85   # pre-fix: sola lettura cronologia


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


# --- correzioni Manus 03/11 (P1a: DSR cumulativo; fail-closed; PASS_PAPER) ---------------

def _sel_sharpe(sharpe=0.25, n_tr=250, n_cum=None, dsr_loc=0.99):
    """Selezione con Sharpe di addestramento: serve al ricalcolo DSR cumulativo."""
    s = _sel(dsr=dsr_loc)
    s["train"]["sharpe"] = sharpe
    s["train"]["n"] = n_tr
    return s


def test_dsr_cambia_col_perimetro_cumulativo():
    """Il DSR che decide deve CAMBIARE quando si aggiungono tentativi storici (non solo
    il campo dell'artefatto): piu' prove -> benchmark Sharpe piu' alto -> DSR piu' basso."""
    sel = _sel_sharpe()
    var = 0.02
    eff_piccolo, loc1, cum1 = IPV.dsr_effettivo(sel, n_cumulativo=24, varianza_sharpe=var)
    eff_grande, loc2, cum2 = IPV.dsr_effettivo(sel, n_cumulativo=400, varianza_sharpe=var)
    assert cum1 is not None and cum2 is not None
    assert cum2 < cum1, "con piu' tentativi il DSR cumulativo deve scendere"
    assert eff_grande <= eff_piccolo
    assert eff_grande == min(loc2, cum2)   # il piu' prudente fra locale e cumulativo


def test_dsr_cumulativo_none_senza_ingredienti_fail_closed():
    """Senza Sharpe di addestramento il DSR cumulativo NON si calcola: deve essere None,
    non il locale (altrimenti il controllo cumulativo salta in silenzio)."""
    sel = _sel(dsr=0.99)               # nessun train.sharpe
    eff, loc, cum = IPV.dsr_effettivo(sel, n_cumulativo=400, varianza_sharpe=0.02)
    assert cum is None and eff is None and loc == 0.99


def test_verdetto_fail_closed_se_dsr_effettivo_none():
    """Chiave presente ma None = DSR non calcolabile -> RESPINTA, NON ricadere sul locale."""
    sel = _sel(dsr=0.99)
    sel["dsr_effettivo"] = None
    v, m = IPV.verdetto(sel, min_op=30, soglia_dsr=0.95)
    assert v == "RESPINTA" and "DSR" in m


def test_verdetto_legacy_senza_chiave_usa_dsr_selezione():
    """Artefatti legacy senza `dsr_effettivo`: si legge il DSR di selezione (compat)."""
    sel = _sel(dsr=0.97)
    assert "dsr_effettivo" not in sel
    v, _ = IPV.verdetto(sel, min_op=30, soglia_dsr=0.95)
    assert v == "PROMOSSA"


def test_cumulativo_puo_solo_abbassare_il_dsr():
    """Il DSR decisionale non puo' essere PIU' permissivo del locale."""
    sel = _sel_sharpe(dsr_loc=0.80)
    eff, loc, cum = IPV.dsr_effettivo(sel, n_cumulativo=24, varianza_sharpe=0.02)
    assert eff <= loc
