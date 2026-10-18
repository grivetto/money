#!/usr/bin/env python3
"""Test della serie equity del banco (ops/aggregator/infra_aggregator.py).

Il builder e' puro: righe (ts, eq, sav) -> finestre h24/d7/d14 + summary.
Niente rete, niente file: si testa la logica che disegna il grafico della
dashboard «IL MOTORE» (bucketing, delta dai punti reali, savings None).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_RADICE = Path(__file__).resolve().parents[1]


def _carica():
    spec = importlib.util.spec_from_file_location(
        "infra_aggregator_test", _RADICE / "ops" / "aggregator" / "infra_aggregator.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


agg = _carica()


def test_finestre_e_bucket():
    now = 2_000_000_000.0
    rows = []
    # 48 ore di punti ogni 5 minuti (576 punti), equity crescente, savings a meta'
    for i in range(576):
        ts = now - 48 * 3600 + i * 300
        rows.append((ts, 1000 + i * 0.1, 500 + i * 0.05 if i % 2 == 0 else None))
    out = agg.build_equity_series(rows, now)
    assert "h24" in out and "d7" in out and "d14" in out
    h24 = out["h24"]
    assert len(h24) >= 280, len(h24)           # ~288 bucket da 5'
    assert all(len(p) == 3 for p in h24)
    assert h24[0][0] >= now - 86400 - 300      # il primo punto h24 e' dentro la finestra
    assert h24[-1][0] == int(rows[-1][0])      # l'ultimo punto e' l'ultimo dato reale
    assert abs(h24[-1][1] - rows[-1][1]) < 0.01
    assert len(out["d7"]) >= 40                # ~48 bucket da 1h
    assert len(out["d14"]) >= 20               # ~24 bucket da 2h


def test_delta_e_summary():
    now = 1_800_000_000.0
    rows = [
        (now - 8 * 86400, 900.0, 400.0),
        (now - 7 * 86400, 950.0, 410.0),   # 7g fa: eq 950, sav 410
        (now - 86400, 1000.0, 480.0),      # 24h fa: eq 1000, sav 480
        (now, 1010.0, 485.0),              # ora: eq 1010, sav 485
    ]
    s = agg.build_equity_series(rows, now)["summary"]
    assert s["equity"] == 1010.0
    assert s["savings"] == 485.0
    assert s["d24"] == 10.0                # 1010 - 1000
    assert s["d7"] == 60.0                 # 1010 - 950
    assert s["earn_d24"] == 5.0            # 485 - 480
    assert s["earn_d7"] == 75.0            # 485 - 410
    assert s["n"] == 4
    assert s["first_ts"] == int(rows[0][0])


def test_savings_none_non_rompe():
    now = 1_800_000_000.0
    rows = [(now - 86400, 100.0, None), (now, 101.0, None)]
    out = agg.build_equity_series(rows, now)
    s = out["summary"]
    assert s["d24"] == 1.0
    assert s["earn_d24"] is None and s["earn_d7"] is None
    assert out["h24"][-1][2] is None
    # con soli 2 punti su 1h il Δ24h non ha un riferimento: None, non un numero inventato
    rows2 = [(now - 3600, 100.0, 50.0), (now, 101.0, 51.0)]
    s2 = agg.build_equity_series(rows2, now)["summary"]
    assert s2["d24"] is None and s2["d7"] is None


def test_vuoto():
    out = agg.build_equity_series([], 1_800_000_000.0)
    assert out["h24"] == [] and out["d7"] == [] and out["d14"] == []
    assert out["summary"]["equity"] is None
    assert out["summary"]["d24"] is None


def test_parse_riga_banco():
    ok = agg._parse_banco_row(
        '{"timestamp": "2026-10-18T20:01:09Z", "equity_eur": 1097.37, "equity_savings_eur": 744.6}')
    assert ok is not None
    ts, eq, sav = ok
    assert eq == 1097.37 and sav == 744.6
    assert ts > 1_790_000_000
    assert agg._parse_banco_row("non-json") is None
    assert agg._parse_banco_row('{"equity_eur": 1}') is None                        # senza timestamp
    assert agg._parse_banco_row('{"timestamp": "2026-10-18T20:01:09Z"}') is None    # senza equity
