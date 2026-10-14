"""Turns business context events into weekly demand multipliers.

Rules
-----
* An event affects a week in proportion to how many of its days fall in that week
  (a 1.20 promo covering 3 of 7 days gives 1 + 0.20 * 3/7).
* Recurring yearly events repeat on the same calendar dates every year
  (windows crossing New Year are handled).
* Several uplifts in the same week get diminishing returns: the two largest apply
  in full, every further uplift counts at 50%. Reductions (stockouts) always apply in full.
* The combined multiplier is clipped to [0.2, 3.0] to stop runaway stacking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from app.core.calendar import safe_replace_year

MIN_TOTAL_MULTIPLIER = 0.2
MAX_TOTAL_MULTIPLIER = 3.0
FULL_STRENGTH_UPLIFTS = 2
DIMINISHING_FACTOR = 0.5


@dataclass(frozen=True)
class EventSpec:
    id: int | None
    name: str
    event_type: str
    start: date
    end: date
    multiplier: float
    recurring_yearly: bool = False
    product_code: str | None = None
    category: str | None = None
    region: str | None = None

    def applies_to(self, product_code: str, category: str, region: str) -> bool:
        return (
            (self.product_code is None or self.product_code.lower() == product_code.lower())
            and (self.category is None or self.category.lower() == category.lower())
            and (self.region is None or self.region.lower() == region.lower())
        )

    def occurrences(self, first_year: int, last_year: int) -> list[tuple[date, date]]:
        if not self.recurring_yearly:
            return [(self.start, self.end)]
        span_years = self.end.year - self.start.year  # 1 when the window crosses New Year
        out = []
        for year in range(first_year - 1, last_year + 1):
            s = safe_replace_year(self.start, year)
            e = safe_replace_year(self.end, year + span_years)
            out.append((s, e))
        return out


@dataclass
class Driver:
    event_id: int | None
    name: str
    event_type: str
    raw_effect: float  # e.g. 0.12 for +12% this week (after partial-week scaling)
    applied_effect: float  # after diminishing returns
    damped: bool = False


@dataclass
class WeekContext:
    multiplier: float = 1.0
    drivers: list[Driver] = field(default_factory=list)


def overlap_days(a_start: date, a_end: date, b_start: date, b_end: date) -> int:
    lo, hi = max(a_start, b_start), min(a_end, b_end)
    return max((hi - lo).days + 1, 0)


def event_effect_in_week(event: EventSpec, week: date) -> float:
    """Fractional effect (multiplier - 1) of one event on the week starting `week`."""
    week_end = week + timedelta(days=6)
    days = 0
    for s, e in event.occurrences(week.year, week_end.year):
        days += overlap_days(s, e, week, week_end)
    days = min(days, 7)
    return (event.multiplier - 1.0) * days / 7.0


def combine(effects: list[tuple[EventSpec, float]]) -> WeekContext:
    uplifts = sorted((x for x in effects if x[1] > 0), key=lambda x: x[1], reverse=True)
    reductions = [x for x in effects if x[1] < 0]

    total = 1.0
    drivers: list[Driver] = []
    for i, (ev, eff) in enumerate(uplifts):
        damped = i >= FULL_STRENGTH_UPLIFTS
        applied = eff * DIMINISHING_FACTOR if damped else eff
        total *= 1.0 + applied
        drivers.append(Driver(ev.id, ev.name, ev.event_type, eff, applied, damped))
    for ev, eff in reductions:
        total *= 1.0 + eff
        drivers.append(Driver(ev.id, ev.name, ev.event_type, eff, eff))

    total = min(max(total, MIN_TOTAL_MULTIPLIER), MAX_TOTAL_MULTIPLIER)
    return WeekContext(multiplier=total, drivers=drivers)


def week_context(events: list[EventSpec], week: date) -> WeekContext:
    effects = [(ev, eff) for ev in events if abs(eff := event_effect_in_week(ev, week)) > 1e-9]
    return combine(effects)


def context_for_weeks(events: list[EventSpec], weeks: list[date]) -> list[WeekContext]:
    return [week_context(events, w) for w in weeks]
