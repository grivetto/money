"""test_carry_config.py — coerenza della configurazione COPPIE (scripts/carry_multi.py).

P27 — D3 step di scala carry: abilitazione LTC/AVAX (REQ-MERL-20261018-011).
Test OFFLINE (zero rete, zero chiavi): carica `scripts/carry_multi.py` via importlib
e verifica il dict COPPIE e il calcolo di contratti/quantita' con prezzi sintetici noti.
Nessuna chiamata exchange.

Caricamento via importlib invece che `import scripts.carry_multi`: `scripts/` non ha
`__init__.py` e `carry_multi.py` ha percorsi hardcoded per MARCODG1 (ROOT=/home/marco/money):
l'import non li usa, inserisce solo quei percorsi (eventualmente inesistenti) in sys.path,
che e' innocuo. Cosi' il test gira ovunque, anche su un checkout appena fatto.

Prova rosso-verde: senza LTC/AVAX in COPPIE i test sulle due coppie falliscono.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

#: Campi del dataclass Coppia (scripts/carry_multi.py) — le "chiavi" del dict.
CAMPI = ("nome", "inst_perp", "sym_perp", "sym_spot", "ct_val",
         "nozionale_eur", "payback_giorni", "ccy_spot")

#: Coppie attese dalla config (pre-esistenti + step D3). LTC/AVAX = P27.
COPPIE_ATTESE = ("DOT", "DOGE", "LINK", "ADA", "LTC", "AVAX")


def _carica_carry_multi():
    """Carica scripts/carry_multi.py come modulo (offline, a impatto zero su sys.modules).

    carry_multi fa `import ccxt` a livello di modulo; la suite ha un test (test_dati)
    che esige `"ccxt" not in sys.modules`. Qui ccxt viene stubato per l'import e alla
    fine sys.modules torna ESATTAMENTE allo stato precedente: il test di configurazione
    non deve inquinare il processo degli altri test.
    """
    import types

    percorso = REPO / "scripts" / "carry_multi.py"
    spec = importlib.util.spec_from_file_location("carry_multi_under_test", percorso)
    assert spec is not None and spec.loader is not None, f"modulo non trovato: {percorso}"
    precedenti = set(sys.modules)
    if "ccxt" not in sys.modules:
        sys.modules["ccxt"] = types.ModuleType("ccxt")
    try:
        modulo = importlib.util.module_from_spec(spec)
        # Registrare PRIMA di exec_module: il decoratore @dataclass(frozen=True) di
        # Python risale a sys.modules[cls.__module__] e fallisce se il nome e' assente.
        sys.modules[spec.name] = modulo
        spec.loader.exec_module(modulo)
    finally:
        for nome in set(sys.modules) - precedenti:
            del sys.modules[nome]
    return modulo


_cm = _carica_carry_multi()
COPPIE = _cm.COPPIE


# ---------------------------------------------------------------- presenza e coerenza

def test_tutte_le_coppie_attese_presenti():
    mancanti = set(COPPIE_ATTESE) - set(COPPIE)
    assert not mancanti, f"coppie mancanti in COPPIE: {sorted(mancanti)}"


def test_campi_obbligatori_presenti():
    for nome, c in COPPIE.items():
        assert c.nome == nome, f"{nome}: campo nome incoerente ({c.nome})"
        for campo in CAMPI:
            assert getattr(c, campo) is not None, f"{nome}.{campo} mancante"
        for campo in ("inst_perp", "sym_perp", "sym_spot", "ccy_spot"):
            v = getattr(c, campo)
            assert isinstance(v, str) and v.strip(), f"{nome}.{campo} vuoto"


def test_ct_val_e_nozionale_positivi():
    for nome, c in COPPIE.items():
        assert c.ct_val > 0, f"{nome}: ct_val {c.ct_val} <= 0"
        assert c.nozionale_eur > 0, f"{nome}: nozionale_eur {c.nozionale_eur} <= 0"


def test_quote_usdc():
    for nome, c in COPPIE.items():
        assert c.ccy_spot == "USDC", f"{nome}: ccy_spot {c.ccy_spot!r} != USDC"
        assert c.sym_spot.endswith("/USDC"), f"{nome}: sym_spot {c.sym_spot!r} non /USDC"


def test_inst_perp_unici():
    ids = [c.inst_perp for c in COPPIE.values()]
    assert len(ids) == len(set(ids)), f"inst_perp duplicati: {ids}"


def test_suffissi_inst_perp_e_sym_perp_coerenti():
    """Pattern esistente: inst_perp = <NOME>-USD_UM_XPERP-<S>, sym_perp = <NOME>/USD:USD-<S>."""
    for nome, c in COPPIE.items():
        assert c.inst_perp.startswith(f"{nome}-USD_UM_XPERP-"), f"{nome}: inst_perp {c.inst_perp!r}"
        assert c.sym_perp.startswith(f"{nome}/USD:USD-"), f"{nome}: sym_perp {c.sym_perp!r}"
        assert c.inst_perp.split("-")[-1] == c.sym_perp.split("-")[-1], (
            f"{nome}: suffissi diversi ({c.inst_perp!r} vs {c.sym_perp!r})")


# ---------------------------------------------------------------- LTC e AVAX (P27)

def test_ltc_parametri_attesi():
    c = COPPIE["LTC"]
    assert c.inst_perp == "LTC-USD_UM_XPERP-310404"
    assert c.sym_perp == "LTC/USD:USD-310404"
    assert c.sym_spot == "LTC/USDC"
    assert c.ct_val == 0.1
    assert c.nozionale_eur == 90.0
    assert c.payback_giorni == 22
    assert c.ccy_spot == "USDC"


def test_avax_parametri_attesi():
    c = COPPIE["AVAX"]
    assert c.inst_perp == "AVAX-USD_UM_XPERP-310530"
    assert c.sym_perp == "AVAX/USD:USD-310530"
    assert c.sym_spot == "AVAX/USDC"
    assert c.ct_val == 10.0
    assert c.nozionale_eur == 90.0
    assert c.payback_giorni == 23
    assert c.ccy_spot == "USDC"


def test_ltc_contratti_e_qty_prezzi_sintetici():
    """Spec P27: LTC px 59,3 -> 15 ct (90 / (0,1 * 59,3) = 15,18 -> round 15), qty 1,5."""
    c = COPPIE["LTC"]
    assert c.n_contratti(59.3) == 15
    assert c.qty_spot(59.3) == pytest.approx(1.5, abs=1e-12)


def test_avax_contratti_e_qty_prezzi_sintetici():
    """Spec P27: AVAX px 9,616 -> 1 ct (90 / (10 * 9,616) = 0,94 -> round 1), qty 10."""
    c = COPPIE["AVAX"]
    assert c.n_contratti(9.616) == 1
    assert c.qty_spot(9.616) == pytest.approx(10.0, abs=1e-12)


# ---------------------------------------------------------------- invarianti di calcolo

def test_n_contratti_mai_zero():
    """Un prezzo irrealisticamente alto non deve mai azzerare la gamba perp."""
    for nome, c in COPPIE.items():
        assert c.n_contratti(1e6) >= 1, f"{nome}: n_contratti(1e6) = {c.n_contratti(1e6)}"


def test_qty_spot_copre_esattamente_il_nozionale_perp():
    """qty_spot == n_contratti * ct_val: copertura delta-neutrale per costruzione."""
    for nome, c in COPPIE.items():
        for px in (0.1, 1.0, 9.616, 59.3, 100.0):
            assert c.qty_spot(px) == pytest.approx(c.n_contratti(px) * c.ct_val, abs=1e-12), (
                f"{nome} @ {px}: qty_spot {c.qty_spot(px)} != {c.n_contratti(px)} * {c.ct_val}")
