"""Rolling-origin backtest, Forecast Value Added (FVA) and anomaly detection.

Backtest: every `step` weeks over the last `window` weeks, refit the baseline using only
data available at that time and forecast the next `horizon` weeks. Each forecast is recorded
for four layers, each built on the previous one:

    naive     same week last year (the benchmark)
    baseline  statistical model
    context   baseline x business-event multipliers
    final     planner override where one exists, else context

FVA asks whether each layer made the forecast better or worse than the layer before it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

import numpy as np

from app.core import metrics
from app.core.baseline import fit_baseline, seasonal_naive

LAYERS = ("naive", "baseline", "context", "final")
MIN_TRAIN_WEEKS = 26


@dataclass
class BacktestRow:
    week: date
    horizon: int
    actual: float
    naive: float
    baseline: float
    context: float
    final: float
    context_multiplier: float
    has_events: bool
    overridden: bool


def run_backtest(
    weeks: list[date],
    sales: np.ndarray,
    context_multipliers: np.ndarray,
    overrides: dict[date, float] | None = None,
    window: int = 52,
    horizon: int = 4,
    step: int | None = None,
) -> list[BacktestRow]:
    overrides = overrides or {}
    sales = np.asarray(sales, dtype=float)
    mult = np.asarray(context_multipliers, dtype=float)
    n = len(weeks)
    step = step or horizon
    first_origin = max(n - window, MIN_TRAIN_WEEKS)
    rows: list[BacktestRow] = []
    for origin in range(first_origin, n, step):
        model = fit_baseline(weeks[:origin], sales[:origin], mult[:origin])
        targets = list(range(origin, min(origin + horizon, n)))
        preds = model.predict([weeks[t] for t in targets])
        for h, (t, base) in enumerate(zip(targets, preds, strict=True), start=1):
            naive = seasonal_naive(sales, t)
            if naive is None:
                naive = float(sales[origin - 1])
            ctx = float(base * mult[t])
            ov = overrides.get(weeks[t])
            rows.append(
                BacktestRow(
                    week=weeks[t],
                    horizon=h,
                    actual=float(sales[t]),
                    naive=naive,
                    baseline=float(base),
                    context=ctx,
                    final=float(ov) if ov is not None else ctx,
                    context_multiplier=float(mult[t]),
                    has_events=abs(mult[t] - 1.0) > 1e-6,
                    overridden=ov is not None,
                )
            )
    return rows


def log_ratio(actual: float, forecast: float) -> float:
    return math.log((actual + 1.0) / (forecast + 1.0))


def residual_sigma(rows: list[BacktestRow]) -> float:
    return metrics.robust_sigma([log_ratio(r.actual, r.context) for r in rows])


def fva_table(rows: list[BacktestRow]) -> list[dict]:
    """Accuracy per layer plus the value each layer added versus the previous one."""
    if not rows:
        return []
    actual = [r.actual for r in rows]
    out, prev = [], None
    for layer in LAYERS:
        m = metrics.summary(actual, [getattr(r, layer) for r in rows])
        added = None
        if prev is not None and prev["wape"] is not None and m["wape"] is not None:
            added = prev["wape"] - m["wape"]  # percentage points of WAPE removed
        out.append({"layer": layer, **m, "fva": added})
        prev = m
    return out


def override_scorecard(rows: list[BacktestRow]) -> dict:
    """On weeks a planner overrode the system: how often did they beat it?"""
    touched = [r for r in rows if r.overridden]
    improved = sum(abs(r.final - r.actual) < abs(r.context - r.actual) for r in touched)
    actual = [r.actual for r in touched]
    return {
        "overrides": len(touched),
        "improved": improved,
        "worsened": len(touched) - improved,
        "wape_system": metrics.wape(actual, [r.context for r in touched]) if touched else None,
        "wape_override": metrics.wape(actual, [r.final for r in touched]) if touched else None,
    }


@dataclass
class Anomaly:
    week: date
    actual: float
    expected: float
    z_score: float
    direction: str  # "spike" | "drop"
    kind: str  # "unexplained" | "mis-sized"


def detect_anomalies(rows: list[BacktestRow], sigma: float, threshold: float = 2.5) -> list[Anomaly]:
    """Weeks where actuals fell far outside the context forecast.

    unexplained: no business event covered the week -> likely missing context.
    mis-sized:   an event was known but its multiplier was badly off.
    """
    seen: dict[date, BacktestRow] = {}
    for r in rows:  # keep the shortest-horizon forecast per week
        if r.week not in seen or r.horizon < seen[r.week].horizon:
            seen[r.week] = r
    found = []
    for r in sorted(seen.values(), key=lambda x: x.week):
        z = log_ratio(r.actual, r.context) / sigma if sigma > 0 else 0.0
        if abs(z) >= threshold:
            found.append(
                Anomaly(
                    week=r.week,
                    actual=r.actual,
                    expected=r.context,
                    z_score=z,
                    direction="spike" if z > 0 else "drop",
                    kind="mis-sized" if r.has_events else "unexplained",
                )
            )
    return found
