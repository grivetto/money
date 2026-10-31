import json
from datetime import datetime, timedelta, timezone

import pytest

from money.ricerca import funding_spread as e9


def ms(day: int, hour: int = 0) -> int:
    start = datetime(2026, 1, 1, hour, tzinfo=timezone.utc)
    return int((start + timedelta(days=day - 1)).timestamp() * 1000)


def write_jsonl(path, rows):
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    return str(path)


def points_for(diffs, *, a="bybit", b="binance", symbol="DOT"):
    rows = []
    for i, diff in enumerate(diffs):
        ts = ms(1 + i, 0)
        rows.extend([
            {"venue": a, "symbol": symbol, "ts": ts, "funding": diff},
            {"venue": b, "symbol": symbol, "ts": ts, "funding": 0.0},
        ])
    return [e9.FundingPoint(r["venue"], r["symbol"], r["ts"], r["funding"]) for r in rows]


def test_load_points_deduplicates_and_rejects_nonfinite(tmp_path):
    path = tmp_path / "funding.jsonl"
    write_jsonl(path, [
        {"venue": "BYBIT", "symbol": "DOT", "ts": 2, "funding": 0.2},
        {"venue": "bybit", "symbol": "DOT", "ts": 2, "funding": 0.3},
        {"venue": "binance", "symbol": "DOT", "ts": 2, "funding": 0.0},
        {"venue": "binance", "symbol": "DOT", "ts": 3, "funding": "NaN"},
        {"venue": "binance", "symbol": "BTC", "ts": 4, "funding": 0.0},
    ])
    points, malformed, read = e9.load_points([path])
    assert read == 5 and malformed == 1
    assert [(p.venue, p.ts, p.funding) for p in points] == [("binance", 2, 0.0), ("bybit", 2, 0.3)]


def test_decision_does_not_use_current_funding_event():
    # First seven history points are below threshold. A very large current
    # event must not open at that same event because history excludes index i.
    points = points_for([0.0] * 7 + [0.10])
    result = e9.simulate_pair(points, "bybit", "binance", "DOT", capital_eur=1000)
    assert result.open_epochs == 0
    assert result.trades == 0


def test_costs_are_charged_and_stress_is_not_more_favorable():
    points = points_for([0.0002] * 10 + [0.0, 0.0, 0.0])
    result = e9.simulate_pair(points, "bybit", "binance", "DOT", capital_eur=1000)
    assert result.trades == 1
    assert result.mean_stress_per_epoch < result.mean_net_per_epoch
    assert result.verdict == "FAIL"


def test_missing_venue_epochs_are_not_filled_with_zero():
    points = points_for([0.0002] * 9)
    points = [p for p in points if not (p.venue == "binance" and p.ts == ms(3))]
    result = e9.simulate_pair(points, "bybit", "binance", "DOT", capital_eur=1000)
    assert result.aligned_epochs == 8


def test_close_signal_uses_current_event_without_one_epoch_delay():
    # Seven prior positive observations open the spread at event 8. The
    # current event is the third sub-threshold event and must close now.
    points = points_for([0.0002] * 7 + [0.0002, 0.000001, 0.000001, 0.000001])
    result = e9.simulate_pair(points, "bybit", "binance", "DOT", capital_eur=1000)
    assert result.trades == 1
    assert result.open_epochs == 4


def test_observations_are_scoped_to_requested_symbol():
    points = points_for([0.0002] * 8, symbol="DOT") + points_for([0.0001] * 5, symbol="ADA")
    result = e9.simulate_pair(points, "bybit", "binance", "DOT", capital_eur=1000)
    assert result.observations == 16


def test_report_has_all_five_declared_symbols_and_is_fail_closed():
    points = points_for([0.0002] * 30)
    result = e9.report(points, venue_a="bybit", venue_b="binance", capital_eur=1000)
    assert len(result["per_symbol"]) == 5
    assert result["aggregate"]["positive_symbols"] == 0
    assert result["aggregate"]["t1_t2_t3"] is False
