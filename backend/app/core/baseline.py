"""Statistical baseline forecaster.

A damped-trend Holt model with a multiplicative week-of-year seasonal profile
(Holt-Winters style), implemented in NumPy.

The key step is *de-contextualising* history before fitting: each week's sales are
divided by the multiplier of the business events known for that week. The baseline then
learns "normal" demand, and the context layer adds promotions, festivals etc. back on top.
Without this, last year's Diwali promo leaks into this year's baseline in the wrong week.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np

from app.core.calendar import iso_week_of_year

ALPHAS = (0.05, 0.1, 0.2, 0.35)
BETAS = (0.01, 0.05, 0.1)
PHI = 0.95  # trend damping
MIN_POINTS = 12
WARMUP = 8


@dataclass
class BaselineModel:
    level: float
    trend: float
    phi: float
    seasonal: np.ndarray  # index 1..52 -> multiplicative factor
    alpha: float
    beta: float
    last_week: date

    def predict(self, weeks: list[date]) -> np.ndarray:
        out = np.empty(len(weeks))
        for i, w in enumerate(weeks):
            h = max(round((w - self.last_week).days / 7), 1)
            damp_sum = sum(self.phi**k for k in range(1, h + 1))
            out[i] = max(self.level + self.trend * damp_sum, 0.0) * self.seasonal[iso_week_of_year(w)]
        return out


def _seasonal_profile(weeks: list[date], clean: np.ndarray) -> np.ndarray:
    """Week-of-year factors from ratio-to-moving-average; flat when < ~1.5 years of data."""
    profile = np.ones(53)
    n = len(clean)
    if n < 78:
        return profile

    # Centred 52-week moving average as the local level.
    kernel = np.ones(52) / 52
    ma = np.convolve(clean, kernel, mode="valid")  # length n - 51
    ma = np.convolve(ma, np.ones(2) / 2, mode="valid")  # 2x52 MA, length n - 52
    offset = 26
    ratios: dict[int, list[float]] = {}
    for j, level in enumerate(ma):
        i = j + offset
        if level > 0:
            ratios.setdefault(iso_week_of_year(weeks[i]), []).append(clean[i] / level)

    raw = np.ones(52)
    for woy in range(1, 53):
        if woy in ratios:
            raw[woy - 1] = float(np.median(ratios[woy]))

    # Circular smoothing over +/-1 week, then normalise to mean 1.
    smooth = (np.roll(raw, 1) + raw + np.roll(raw, -1)) / 3
    smooth /= smooth.mean()

    # Shrink toward flat when we only have a little more than one season of ratios.
    years_of_ratios = len(ma) / 52
    shrink = min(years_of_ratios / 2.0, 1.0)
    smooth = 1 + (smooth - 1) * shrink

    profile[1:] = smooth
    return profile


def _holt(y: np.ndarray, alpha: float, beta: float, phi: float) -> tuple[float, float, float]:
    """Run damped Holt; return (level, trend, one-step SSE after warm-up)."""
    level = float(np.mean(y[: min(WARMUP, len(y))]))
    trend = 0.0
    sse = 0.0
    for t, obs in enumerate(y):
        pred = level + phi * trend
        if t >= WARMUP:
            sse += (obs - pred) ** 2
        new_level = alpha * obs + (1 - alpha) * pred
        trend = beta * (new_level - level) + (1 - beta) * phi * trend
        level = new_level
    return level, trend, sse


def fit_baseline(weeks: list[date], sales: np.ndarray, context_multipliers: np.ndarray) -> BaselineModel:
    sales = np.asarray(sales, dtype=float)
    mult = np.asarray(context_multipliers, dtype=float)
    if len(sales) == 0:
        raise ValueError("Cannot fit a baseline on an empty series")

    clean = sales / np.where(mult > 0, mult, 1.0)

    if len(clean) < MIN_POINTS:
        level = float(np.mean(clean[-4:]))
        return BaselineModel(level, 0.0, PHI, np.ones(53), 0.0, 0.0, weeks[-1])

    seasonal = _seasonal_profile(weeks, clean)
    deseason = clean / np.array([seasonal[iso_week_of_year(w)] for w in weeks])

    best = None
    for a in ALPHAS:
        for b in BETAS:
            level, trend, sse = _holt(deseason, a, b, PHI)
            if best is None or sse < best[0]:
                best = (sse, a, b, level, trend)
    _, a, b, level, trend = best
    return BaselineModel(level, trend, PHI, seasonal, a, b, weeks[-1])


def seasonal_naive(sales: np.ndarray, index: int, season: int = 52) -> float | None:
    """Same week last year: the classic benchmark every forecast should beat."""
    j = index - season
    return float(sales[j]) if 0 <= j < len(sales) else None
