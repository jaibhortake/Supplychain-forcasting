"""Indian festival calendar -> context events."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from app.config import DATA_DIR

FESTIVAL_FILE = DATA_DIR / "festivals.json"
FESTIVAL_SOURCE = "festival_calendar"


@dataclass(frozen=True)
class FestivalOccurrence:
    key: str
    name: str
    day: date
    window_start: date
    window_end: date
    regions: tuple[str, ...] | None
    uplift: dict[str, float]


@lru_cache
def _load(path: Path = FESTIVAL_FILE) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["festivals"]


def festival_occurrences(years: list[int] | None = None) -> list[FestivalOccurrence]:
    out = []
    for f in _load():
        for year, day_str in f["dates"].items():
            if years is not None and int(year) not in years:
                continue
            day = date.fromisoformat(day_str)
            out.append(
                FestivalOccurrence(
                    key=f["key"],
                    name=f["name"],
                    day=day,
                    window_start=day - timedelta(days=f["days_before"]),
                    window_end=day + timedelta(days=f["days_after"]),
                    regions=tuple(f["regions"]) if f["regions"] else None,
                    uplift=dict(f["uplift"]),
                )
            )
    return sorted(out, key=lambda o: o.day)


def available_years() -> list[int]:
    return sorted({int(y) for f in _load() for y in f["dates"]})


def festival_event_rows(years: list[int] | None = None) -> list[dict]:
    """One context-event row per festival x year x region x product category."""
    rows = []
    for occ in festival_occurrences(years):
        for region in occ.regions or (None,):
            for category, mult in occ.uplift.items():
                rows.append(
                    {
                        "name": f"{occ.name} {occ.day.year}",
                        "event_type": "festival",
                        "description": f"{occ.name} on {occ.day:%d %b %Y}; shopping window "
                        f"{occ.window_start:%d %b} - {occ.window_end:%d %b}.",
                        "product_code": None,
                        "category": category,
                        "region": region,
                        "start_date": occ.window_start,
                        "end_date": occ.window_end,
                        "multiplier": mult,
                        "recurring_yearly": False,
                        "source": FESTIVAL_SOURCE,
                    }
                )
    return rows
