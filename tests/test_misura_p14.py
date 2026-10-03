"""Test del runner P14 — regole pure e di selezione; nessuna rete, nessun ordine.

PERCHE' QUESTI TEST ESISTONO
============================
La spec P14 dichiara regole che, se violate, farebbero misurare un'altra cosa:
  1. la griglia e' dichiarata PRIMA: {k:3,5} x {L:60,120} x {R:7,14} = 8 varianti, tutte provate;
  2. la riga di riferimento (config P10: k=2, L=120, R=14) NON e' mai selezionabile;
  3. la candidabilita' richiede >= 30 operazioni eseguite in addestramento;
  4. la selezione sceglie il massimo `expectancy_netta / dd_portafoglio` tra i candidabili;
  5. gli artefatti sono JSON validi (inf/nan -> null) e le righe tabella marcano n>=30.
Questi test bloccano ognuna di quelle promesse su casi piccoli e determinati, senza rete.
"""
from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

_PERCORSO = Path(__file__).resolve().parents[1] / "scripts" / "misura_p14.py"
_spec = importlib.util.spec_from_file_location("misura_p14", _PERCORSO)
assert _spec is not None and _spec.loader is not None
P = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(P)


def _riga(k: int, lookback: int, ribilancio: int, *, eseguite: int = 40,
          rapporto: float = 1.0) -> dict:
    """Riga sintetica con la stessa forma di `misura_config` (per la selezione)."""
    return {
        "config": {"k": k, "lookback": lookback, "ribilancio": ribilancio},
        "chiave": f"k={k}_L={lookback}_R={ribilancio}",
        "descrizione": f"Config(k={k}, lookback={lookback}, ribilancio={ribilancio})",
        "n_operazioni_campione": eseguite, "eseguite": eseguite, "saltate": 0,
        "expectancy_netta": 0.01, "expectancy_lorda": 0.012,
        "dd_portafoglio": 0.1, "rapporto_exp_dd": rapporto,
        "max_esposizione": 1.0 / k, "max_posizioni": k, "capitale_finale": 1000.0,
        "rendimento_totale": 0.1, "giorni": 100.0, "esposizione_media_dichiarata": 1.0 / k,
        "t_stat": 1.0, "t_stat_newey_west": 1.0, "netti_eseguiti": [0.01] * eseguite,
        "tariffa": "okx_eea_spot",
    }


def test_griglia_dichiarata_esattamente_8_varianti():
    attesa = {(k, lookback, ribilancio)
              for k in (3, 5) for lookback in (60, 120) for ribilancio in (7, 14)}
    ottenuta = {(c["k"], c["lookback"], c["ribilancio"]) for c in P.GRIGLIA_ADDESTRAMENTO}
    assert ottenuta == attesa
    assert len(P.GRIGLIA_ADDESTRAMENTO) == 8


def test_riferimento_non_selezionabile(monkeypatch):
    """Anche col rapporto migliore, il riferimento resta fuori dalla selezione."""
    def finto(dati, config, *, i_da, i_a, tariffa_nome, capitale,
              slippage_per_lato=P.SLIPPAGE_BP_LATO):
        if (config.k, config.lookback, config.ribilancio) == (2, 120, 14):
            return _riga(2, 120, 14, rapporto=99.0)
        return _riga(config.k, config.lookback, config.ribilancio,
                     rapporto=1.0 + config.k / 10)

    monkeypatch.setattr(P, "misura_config", finto)
    scelta, righe, dati_righe, rif = P.allena({"x": []}, 10, "okx_eea_spot", 1000.0)
    assert scelta is not None
    assert scelta["config"] != P.CONFIG_RIFERIMENTO
    assert rif["config"] == P.CONFIG_RIFERIMENTO
    assert any("RIFERIMENTO P10 (non eleggibile)" in r for r in righe)


def test_selezione_richiede_min_operazioni(monkeypatch):
    """Le righe sotto 30 operazioni eseguite non sono candidabili, anche col rapporto migliore."""
    def finto(dati, config, *, i_da, i_a, tariffa_nome, capitale,
              slippage_per_lato=P.SLIPPAGE_BP_LATO):
        eseguite = 5 if config.k == 3 else 40
        return _riga(config.k, config.lookback, config.ribilancio, eseguite=eseguite,
                     rapporto=(10.0 if config.k == 3 else 1.0))

    monkeypatch.setattr(P, "misura_config", finto)
    scelta, _, _, _ = P.allena({"x": []}, 10, "okx_eea_spot", 1000.0)
    assert scelta is not None and scelta["config"]["k"] == 5


def test_selezione_senza_candidati_torna_none(monkeypatch):
    def finto(dati, config, *, i_da, i_a, tariffa_nome, capitale,
              slippage_per_lato=P.SLIPPAGE_BP_LATO):
        return _riga(config.k, config.lookback, config.ribilancio, eseguite=3, rapporto=-1.0)

    monkeypatch.setattr(P, "misura_config", finto)
    scelta, _, _, _ = P.allena({"x": []}, 10, "okx_eea_spot", 1000.0)
    assert scelta is None


def test_selezione_massimo_exp_dd(monkeypatch):
    def finto(dati, config, *, i_da, i_a, tariffa_nome, capitale,
              slippage_per_lato=P.SLIPPAGE_BP_LATO):
        return _riga(config.k, config.lookback, config.ribilancio, eseguite=40,
                     rapporto=config.lookback / 100.0)

    monkeypatch.setattr(P, "misura_config", finto)
    scelta, _, _, _ = P.allena({"x": []}, 10, "okx_eea_spot", 1000.0)
    assert scelta is not None and scelta["config"]["lookback"] == 120


def test_formattatori_p_n():
    assert P._p(0.01) == "+1,000%"
    assert P._p(None) == "n/d"
    assert P._p(float("nan")) == "n/d"
    assert P._n(123.456) == "123,46"
    assert P._n(None) == "n/d"


def test_riga_tabella_marca_soglia_n():
    assert "n>=30 si" in P._riga_tabella(_riga(3, 60, 7, eseguite=30))
    assert "n>=30 no" in P._riga_tabella(_riga(3, 60, 7, eseguite=29))


def test_scrivi_artefatti_json_valido(cartella):
    P._scrivi(cartella, ["riga1", "riga2"],
              {"a": math.inf, "b": float("nan"), "c": [1.0]})
    testo = (cartella / "P14_momentum_universo.txt").read_text(encoding="utf-8")
    assert "riga1" in testo and "riga2" in testo
    dati = json.loads((cartella / "P14_momentum_universo.json").read_text(encoding="utf-8"))
    assert dati["a"] is None and dati["b"] is None and dati["c"] == [1.0]


def test_pulito_ricorsivo():
    assert P._pulito({"x": float("inf")}) == {"x": None}
    assert P._pulito([1.0, float("nan")]) == [1.0, None]
