"""Synthetic but realistic weekly sales history for the demo catalogue.

The "true world" that generates sales:
* category seasonality (ACs peak in Apr-Jun, much more in the North than the South),
* per-series growth trend,
* business events, whose TRUE impact differs from the planner's multiplier
  (planners are never exactly right, which is what FVA should reveal),
* a few unexplained shocks (heatwave, strike, competitor price war) that no event explains,
  so anomaly detection has something to find,
* log-normal noise.

Everything is seeded and reproducible.
"""

from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache

import numpy as np

from app.core.calendar import week_range
from app.core.context import EventSpec, event_effect_in_week

PRODUCTS = [
    {
        "code": "AC-X1",
        "name": "Split AC 1.5 Ton",
        "category": "air_conditioner",
        "unit_cost": 32000.0,
        "lead_time_weeks": 3,
    },
    {"code": "TV-S2", "name": "43-inch Smart TV", "category": "television", "unit_cost": 24000.0, "lead_time_weeks": 2},
    {
        "code": "REF-C3",
        "name": "Double-Door Refrigerator",
        "category": "refrigerator",
        "unit_cost": 28000.0,
        "lead_time_weeks": 2,
    },
]
REGIONS = ["North", "South", "East", "West"]

BASE_LEVEL = {
    ("AC-X1", "North"): 120,
    ("AC-X1", "South"): 95,
    ("AC-X1", "East"): 80,
    ("AC-X1", "West"): 105,
    ("TV-S2", "North"): 150,
    ("TV-S2", "South"): 170,
    ("TV-S2", "East"): 110,
    ("TV-S2", "West"): 140,
    ("REF-C3", "North"): 90,
    ("REF-C3", "South"): 100,
    ("REF-C3", "East"): 80,
    ("REF-C3", "West"): 95,
}

AC_AMPLITUDE = {"North": 1.6, "East": 1.2, "West": 0.9, "South": 0.5}
AC_FLOOR = {"North": 0.35, "East": 0.45, "West": 0.55, "South": 0.75}

NOISE_SIGMA = 0.08
HISTORY_START = date(2023, 1, 2)


@dataclass(frozen=True)
class Shock:
    product_code: str
    region: str
    weeks_before_end: int
    factor: float
    label: str


# Things that happened but nobody recorded as a context event.
SHOCKS = [
    Shock("REF-C3", "East", 43, 0.55, "Transport strike"),
    Shock("TV-S2", "West", 34, 0.62, "Competitor price war"),
    Shock("AC-X1", "North", 21, 1.50, "Unforecast heatwave"),
    Shock("REF-C3", "South", 13, 1.65, "Bulk institutional order"),
]


def _gauss(x: float, mu: float, width: float) -> float:
    return math.exp(-(((x - mu) / width) ** 2))


def _raw_season(category: str, region: str, doy: int) -> float:
    if category == "air_conditioner":
        return AC_FLOOR[region] + AC_AMPLITUDE[region] * _gauss(doy, 135, 38)
    if category == "refrigerator":
        return 0.8 + 0.45 * _gauss(doy, 125, 45)
    # television: small cricket-season bump, monsoon lull; festivals come from events
    return 1.0 + 0.12 * _gauss(doy, 110, 20) - 0.08 * _gauss(doy, 205, 30)


@lru_cache
def _season_mean(category: str, region: str) -> float:
    return sum(_raw_season(category, region, d) for d in range(1, 366)) / 365


def seasonality(category: str, region: str, doy: int) -> float:
    return _raw_season(category, region, doy) / _season_mean(category, region)


def _event_family(ev: EventSpec) -> str:
    """Same festival in different years shares one 'true' effect size."""
    return re.sub(r"\s*\d{4}$", "", ev.name) + f"|{ev.category or ev.product_code}|{ev.region}"


def true_effect_scale(ev: EventSpec, seed: int) -> float:
    """How much the real impact differs from the planner's guess (0.6x .. 1.6x)."""
    return random.Random(f"{seed}:{_event_family(ev)}").uniform(0.6, 1.6)


def generate_sales(
    events: list[EventSpec],
    history_end: date,
    seed: int = 42,
    start: date = HISTORY_START,
) -> dict[tuple[str, str], list[tuple[date, float]]]:
    n_weeks = (history_end - start).days // 7 + 1
    weeks = week_range(start, n_weeks)
    rng = np.random.default_rng(seed)
    out: dict[tuple[str, str], list[tuple[date, float]]] = {}

    for p in PRODUCTS:
        for region in REGIONS:
            growth = rng.uniform(0.04, 0.12)
            base = BASE_LEVEL[(p["code"], region)]
            relevant = [e for e in events if e.applies_to(p["code"], p["category"], region)]
            shocks = {
                weeks[-1] - timedelta(weeks=s.weeks_before_end): s.factor
                for s in SHOCKS
                if s.product_code == p["code"] and s.region == region and s.weeks_before_end < n_weeks
            }
            series = []
            for t, w in enumerate(weeks):
                mid = w + timedelta(days=3)
                level = base * (1 + growth) ** (t / 52)
                season = seasonality(p["category"], region, mid.timetuple().tm_yday)
                ctx = 1.0
                for ev in relevant:
                    eff = event_effect_in_week(ev, w)
                    if eff:
                        ctx *= max(1 + eff * true_effect_scale(ev, seed), 0.05)
                noise = rng.lognormal(0, NOISE_SIGMA)
                units = level * season * ctx * shocks.get(w, 1.0) * noise
                series.append((w, float(max(round(units), 0))))
            out[(p["code"], region)] = series
    return out
