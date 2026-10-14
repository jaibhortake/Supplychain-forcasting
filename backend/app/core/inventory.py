"""Prediction intervals and stock recommendations.

Forecast errors are modelled as log-normal around the point forecast (the median), with a
spread `sigma` estimated from backtest residuals and widening slowly with horizon.

Stock policy: periodic review, order-up-to level.
    protection interval = lead time + 1 review week
    order-up-to level   = expected demand over the interval + safety stock
    safety stock        = z(service level) * std-dev of demand over the interval
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist

_N = NormalDist()
Z_P10 = _N.inv_cdf(0.10)
Z_P90 = _N.inv_cdf(0.90)
HORIZON_GROWTH = 0.10
REVIEW_PERIOD_WEEKS = 1
SERVICE_LEVEL_TABLE = (0.90, 0.95, 0.98, 0.99)


def sigma_at(sigma: float, horizon: int) -> float:
    return sigma * math.sqrt(1 + HORIZON_GROWTH * (max(horizon, 1) - 1))


def interval(point: float, sigma: float, horizon: int) -> tuple[float, float]:
    s = sigma_at(sigma, horizon)
    return point * math.exp(Z_P10 * s), point * math.exp(Z_P90 * s)


def lognormal_mean_sd(median: float, s: float) -> tuple[float, float]:
    mean = median * math.exp(s * s / 2)
    sd = mean * math.sqrt(math.exp(s * s) - 1)
    return mean, sd


@dataclass
class StockPlan:
    service_level: float
    protection_weeks: int
    expected_demand: float
    demand_sd: float
    safety_stock: float
    order_up_to: float
    on_hand: float
    on_order: float
    recommended_order: int
    stockout_risk: float  # P(demand over interval > on_hand + on_order)
    days_of_cover: float | None


def stock_plan(
    points: list[float],
    sigma: float,
    lead_time_weeks: int,
    service_level: float = 0.95,
    on_hand: float = 0.0,
    on_order: float = 0.0,
) -> StockPlan:
    if not 0.5 <= service_level < 1.0:
        raise ValueError("service_level must be in [0.5, 1.0)")
    weeks = max(lead_time_weeks, 0) + REVIEW_PERIOD_WEEKS
    window = points[:weeks]
    means, variances = [], []
    for h, p in enumerate(window, start=1):
        m, sd = lognormal_mean_sd(max(p, 0.0), sigma_at(sigma, h))
        means.append(m)
        variances.append(sd * sd)
    mu = sum(means)
    sd_total = math.sqrt(sum(variances))
    z = _N.inv_cdf(service_level)
    safety = z * sd_total
    out = mu + safety
    position = on_hand + on_order
    risk = 1 - _N.cdf((position - mu) / sd_total) if sd_total > 0 else float(position < mu)
    weekly = mu / len(window) if window else 0
    cover = position / weekly * 7 if weekly > 0 else None
    return StockPlan(
        service_level=service_level,
        protection_weeks=weeks,
        expected_demand=mu,
        demand_sd=sd_total,
        safety_stock=safety,
        order_up_to=out,
        on_hand=on_hand,
        on_order=on_order,
        recommended_order=max(math.ceil(out - position), 0),
        stockout_risk=risk,
        days_of_cover=cover,
    )
