"""E9 funding-spread cross-venue carry, deterministic and read-only.

This module never connects to an exchange and never creates orders.  It measures
whether a pre-registered funding spread would have paid its declared execution
costs on aligned funding events.

Input rows are JSON objects with: ``venue``, ``simbolo`` (or ``symbol``),
``ts`` in milliseconds, and ``funding`` as a fraction per funding period.
"""
from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

EPOCH_MS = 8 * 60 * 60 * 1000
DEFAULT_SYMBOLS = ("DOT", "ADA", "LTC", "AVAX", "DOGE")
DEFAULT_WINDOW = 7
DEFAULT_OPEN_THRESHOLD = 0.000010  # 0.001% per epoch
DEFAULT_CLOSE_THRESHOLD = 0.000002  # 0.0002% per epoch
DEFAULT_FEE_PER_SIDE = 0.0005       # 5 bp per leg and direction
DEFAULT_SLIPPAGE_PER_SIDE = 0.0001  # 1 bp per leg in stress


@dataclass(frozen=True)
class FundingPoint:
    venue: str
    symbol: str
    ts: int
    funding: float


@dataclass(frozen=True)
class Trade:
    symbol: str
    venue_a: str
    venue_b: str
    opened_ts: int
    closed_ts: int
    sign: int
    epochs: int
    gross_funding: float
    base_net: float
    stress_net: float


@dataclass(frozen=True)
class PairMetrics:
    symbol: str
    venue_a: str
    venue_b: str
    observations: int
    aligned_epochs: int
    open_epochs: int
    trades: int
    mean_net_per_epoch: float
    t_stat: float | None
    ci90_low: float | None
    ci90_high: float | None
    mean_stress_per_epoch: float
    sign_consistency_months: float
    capital_per_symbol_eur: float
    annualized_base_return_on_allocated_capital: float
    annualized_stress_return_on_allocated_capital: float
    verdict: str


def _finite_float(value: object) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("non-finite funding")
    return result


def load_points(paths: Sequence[str | Path], *, symbols: Iterable[str] = DEFAULT_SYMBOLS) -> tuple[list[FundingPoint], int, int]:
    """Load and deduplicate JSONL points. Returns (points, malformed, read)."""
    allowed = {str(s).upper() for s in symbols}
    latest: dict[tuple[str, str, int], FundingPoint] = {}
    malformed = 0
    read = 0
    for path in paths:
        with Path(path).open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                read += 1
                try:
                    row = json.loads(line)
                    venue = str(row["venue"]).strip().lower()
                    symbol = str(row.get("simbolo", row.get("symbol"))).upper().replace("/USDT", "")
                    if symbol not in allowed:
                        continue
                    ts = int(row["ts"])
                    funding = _finite_float(row["funding"])
                    if not venue or ts < 0:
                        raise ValueError("invalid point")
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    malformed += 1
                    continue
                latest[(venue, symbol, ts)] = FundingPoint(venue, symbol, ts, funding)
    return sorted(latest.values(), key=lambda p: (p.symbol, p.ts, p.venue)), malformed, read


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _t_stat(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    sd = statistics.stdev(values)
    return None if sd == 0 else _mean(values) / (sd / math.sqrt(len(values)))


def _ci90(values: Sequence[float]) -> tuple[float | None, float | None]:
    if len(values) < 2:
        return None, None
    mean = _mean(values)
    half = 1.645 * statistics.stdev(values) / math.sqrt(len(values))
    return mean - half, mean + half


def _round_trip_cost(fee_per_side: float, slippage_per_side: float) -> float:
    # two legs, each opened and closed: four charged sides in total.
    return 4.0 * (fee_per_side + slippage_per_side)


def _month(ts: int) -> str:
    import datetime as dt
    return dt.datetime.fromtimestamp(ts / 1000, tz=dt.timezone.utc).strftime("%Y-%m")


def simulate_pair(
    points: Sequence[FundingPoint],
    venue_a: str,
    venue_b: str,
    symbol: str,
    *,
    capital_eur: float,
    allocated_fraction: float = 0.25,
    symbol_count: int = 5,
    window: int = DEFAULT_WINDOW,
    open_threshold: float = DEFAULT_OPEN_THRESHOLD,
    close_threshold: float = DEFAULT_CLOSE_THRESHOLD,
    fee_per_side: float = DEFAULT_FEE_PER_SIDE,
    stress_slippage_per_side: float = DEFAULT_SLIPPAGE_PER_SIDE,
) -> PairMetrics:
    """Simulate one pair. Every decision at t uses only diffs strictly before t."""
    by_key: dict[tuple[str, int], float] = {(p.venue, p.ts): p.funding for p in points if p.symbol == symbol}
    timestamps = sorted({ts for venue, ts in by_key if venue in {venue_a, venue_b}
                         and (venue_a, ts) in by_key and (venue_b, ts) in by_key})
    diffs = [by_key[(venue_a, ts)] - by_key[(venue_b, ts)] for ts in timestamps]
    capital = capital_eur * allocated_fraction / symbol_count
    base_rt = _round_trip_cost(fee_per_side, 0.0)
    stress_rt = _round_trip_cost(fee_per_side * 2.0, stress_slippage_per_side)
    open_state: dict[str, float | int] | None = None
    base_returns: list[float] = []
    stress_returns: list[float] = []
    trades: list[Trade] = []
    sign_months: dict[str, list[int]] = defaultdict(list)

    for i, ts in enumerate(timestamps):
        history = diffs[max(0, i - window):i]
        if len(history) < window:
            continue
        rolling = _mean(history)
        sign = 1 if rolling > 0 else -1
        close_signal = (abs(rolling) < close_threshold and len(history) >= 3
                        and all(abs(x) < close_threshold for x in history[-3:]))
        invert_signal = len(history) >= 2 and history[-1] * history[-2] < 0
        if open_state is None and abs(rolling) >= open_threshold:
            open_state = {"ts": ts, "sign": sign, "gross": 0.0, "epochs": 0}
        if open_state is not None:
            direction = int(open_state["sign"])
            gross = direction * diffs[i]
            open_state["gross"] = float(open_state["gross"]) + gross
            open_state["epochs"] = int(open_state["epochs"]) + 1
            base_returns.append(gross)
            stress_returns.append(gross)
            if close_signal or invert_signal:
                gross_total = float(open_state["gross"])
                trade = Trade(symbol, venue_a, venue_b, int(open_state["ts"]), ts, direction,
                              int(open_state["epochs"]), gross_total,
                              gross_total - base_rt, gross_total - stress_rt)
                trades.append(trade)
                base_returns[-1] -= base_rt
                stress_returns[-1] -= stress_rt
                open_state = None
        if rolling != 0:
            sign_months[_month(ts)].append(1 if rolling > 0 else -1)

    if open_state is not None and timestamps:
        ts = timestamps[-1]
        gross_total = float(open_state["gross"])
        trades.append(Trade(symbol, venue_a, venue_b, int(open_state["ts"]), ts,
                            int(open_state["sign"]), int(open_state["epochs"]), gross_total,
                            gross_total - base_rt, gross_total - stress_rt))
        base_returns[-1] -= base_rt
        stress_returns[-1] -= stress_rt

    month_consistency = []
    for signs in sign_months.values():
        majority = max(sum(s > 0 for s in signs), sum(s < 0 for s in signs))
        month_consistency.append(majority / len(signs))
    ci_low, ci_high = _ci90(base_returns)
    mean_base = _mean(base_returns)
    mean_stress = _mean(stress_returns)
    t_stat = _t_stat(base_returns)
    annual_base = mean_base * 3 * 365 / capital if capital else 0.0
    annual_stress = mean_stress * 3 * 365 / capital if capital else 0.0
    verdict = "PASS" if (len(base_returns) >= 200 and mean_base > 0 and (t_stat or 0) >= 2
                          and mean_stress > 0) else "FAIL"
    return PairMetrics(symbol, venue_a, venue_b, len(points), len(timestamps), len(base_returns),
                       len(trades), mean_base, t_stat, ci_low, ci_high, mean_stress,
                       _mean(month_consistency), capital, annual_base, annual_stress, verdict)


def report(points: Sequence[FundingPoint], *, venue_a: str, venue_b: str,
           capital_eur: float, symbols: Sequence[str] = DEFAULT_SYMBOLS) -> dict:
    results = [asdict(simulate_pair(points, venue_a, venue_b, symbol, capital_eur=capital_eur))
               for symbol in symbols]
    positives = sum(r["verdict"] == "PASS" for r in results)
    aggregate = {
        "venue_a": venue_a, "venue_b": venue_b, "capital_eur": capital_eur,
        "symbols": len(results), "positive_symbols": positives,
        "t1_t2_t3": positives >= 3 and all(r["verdict"] == "PASS" for r in results if r["aligned_epochs"] >= 200),
        "note": "Backtest/shadow only: no order placement and no profit guarantee.",
    }
    return {"meta": {"engine": "money.ricerca.funding_spread", "schema": 1},
            "aggregate": aggregate, "per_symbol": results}


def report_text(result: Mapping[str, object]) -> str:
    lines = ["E9 FUNDING-SPREAD CROSS-VENUE — BACKTEST/SHADOW READ-ONLY", "",
             "NESSUN ORDINE. Nessuna garanzia di profitto.", ""]
    agg = result["aggregate"]
    lines.append(f"venue: {agg['venue_a']} ↔ {agg['venue_b']} | capitale: {agg['capital_eur']:.2f} EUR")
    lines.append(f"simboli PASS: {agg['positive_symbols']}/{agg['symbols']} | gate aggregato: {agg['t1_t2_t3']}")
    lines.append("")
    lines.append("symbol | aligned | open | trades | mean/epoch | t | stress mean | consistency | verdict")
    for row in result["per_symbol"]:
        t = "n/a" if row["t_stat"] is None else f"{row['t_stat']:.2f}"
        lines.append(f"{row['symbol']:6} | {row['aligned_epochs']:7} | {row['open_epochs']:4} | {row['trades']:6} | "
                     f"{row['mean_net_per_epoch']:+.8f} | {t:>5} | {row['mean_stress_per_epoch']:+.8f} | "
                     f"{row['sign_consistency_months']:.2%} | {row['verdict']}")
    return "\n".join(lines) + "\n"
