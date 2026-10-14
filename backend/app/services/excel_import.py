"""Import business context events from the planner Excel/CSV template.

Expected columns (same as the original PoC sheet):
    Product | Element Type | Event Description | Impact Window Type | Impact Window Start |
    Impact Window End | Impact Window Start Fixed | Impact Window End Fixed | Response Type |
    Impact Magnitude Formula | Impact filters | Activity Level

Impact Window Type:
    Fixed Yearly Occurrence -> Start/End Fixed dates, repeats every year
    From Event              -> Start/End Fixed dates, one-off
    Relative                -> Start Fixed + (Start..End) weeks offset, one-off
"""

from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import pandas as pd

REQUIRED_COLUMNS = {
    "Product",
    "Element Type",
    "Impact Window Type",
    "Impact Window Start Fixed",
    "Impact filters",
}

TYPE_ALIASES = {
    "promotion": "promotion",
    "promo": "promotion",
    "stockout": "stockout",
    "distributor": "distributor",
    "seasonal": "seasonal",
    "temperature": "temperature",
    "weather": "temperature",
    "festival": "festival",
}

# Used when a row has no numeric formula (Response Type = Categorical).
ACTIVITY_UPLIFT = {"low": 1.05, "medium": 1.10, "high": 1.20}
ACTIVITY_DROP = {"low": 0.95, "medium": 0.90, "high": 0.80}

_NUMBER_WITH_LABEL = re.compile(r"(\d+(?:\.\d+)?)\s*(?:\(\s*([A-Za-z ]+?)\s*\))?")


@dataclass
class ImportResult:
    events: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _blank(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v)) or (isinstance(v, str) and not v.strip())


def parse_date(v) -> date | None:
    if _blank(v):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, pd.Timestamp):
        return v.date()
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%d-%b-%Y", "%d %b %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date '{s}'")


def parse_filters(raw) -> dict[str, str]:
    """'product=AC-X1, region=North' -> {'product': 'AC-X1', 'region': 'North'}"""
    out = {}
    for part in str(raw or "").split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip().lower()] = v.strip()
    return out


def parse_multiplier(formula, activity_level, event_type: str) -> float:
    """Read the multiplier from e.g. 'Multiplier: 1.20 (High), 1.00 (Default)'.

    With labelled options, pick the one matching Activity Level, else 'Default', else the first.
    Without a formula, fall back to a standard uplift (or drop, for stockouts) by activity level.
    """
    level = str(activity_level or "").strip().lower()
    if not _blank(formula):
        options = [
            (float(num), (label or "").strip().lower()) for num, label in _NUMBER_WITH_LABEL.findall(str(formula))
        ]
        if options:
            by_label = {label: value for value, label in options if label}
            if level in by_label:
                return by_label[level]
            if "default" in by_label:
                return by_label["default"]
            return options[0][0]
    table = ACTIVITY_DROP if event_type == "stockout" else ACTIVITY_UPLIFT
    return table.get(level, 1.0)


def _int(v, default=0) -> int:
    return default if _blank(v) else int(float(v))


def parse_row(row: dict) -> dict:
    raw_type = str(row.get("Element Type", "")).strip().lower()
    event_type = TYPE_ALIASES.get(raw_type)
    if event_type is None:
        raise ValueError(f"unknown Element Type '{row.get('Element Type')}'")

    filters = parse_filters(row.get("Impact filters"))
    product = filters.get("product") or filters.get("item_group")
    region = filters.get("region")

    window_type = str(row.get("Impact Window Type", "")).strip().lower()
    fixed_start = parse_date(row.get("Impact Window Start Fixed"))
    fixed_end = parse_date(row.get("Impact Window End Fixed"))
    if fixed_start is None:
        raise ValueError("missing 'Impact Window Start Fixed'")

    if window_type == "relative":
        start = fixed_start + timedelta(weeks=_int(row.get("Impact Window Start")))
        end = fixed_start + timedelta(weeks=_int(row.get("Impact Window End")), days=6)
        recurring = False
    elif window_type in {"fixed yearly occurrence", "from event", "fixed"}:
        start, end = fixed_start, fixed_end or fixed_start
        recurring = window_type == "fixed yearly occurrence"
    else:
        raise ValueError(f"unknown Impact Window Type '{row.get('Impact Window Type')}'")
    if end < start and not recurring:
        raise ValueError("window ends before it starts")

    multiplier = parse_multiplier(row.get("Impact Magnitude Formula"), row.get("Activity Level"), event_type)
    if not 0.1 <= multiplier <= 5:
        raise ValueError(f"multiplier {multiplier} out of range")

    name = str(row.get("Product") or "").strip() or f"{event_type.title()} event"
    description = "" if _blank(row.get("Event Description")) else str(row["Event Description"]).strip()
    return {
        "name": name,
        "event_type": event_type,
        "description": description,
        "product_code": product.upper() if product else None,
        "category": None,
        "region": region.title() if region else None,
        "start_date": start,
        "end_date": end,
        "multiplier": round(multiplier, 4),
        "recurring_yearly": recurring,
        "source": "excel",
    }


def read_table(content: bytes, filename: str) -> pd.DataFrame:
    if filename.lower().endswith(".csv"):
        return pd.read_csv(io.BytesIO(content))
    return pd.read_excel(io.BytesIO(content))


def parse_events_frame(df: pd.DataFrame) -> ImportResult:
    df = df.rename(columns=lambda c: str(c).strip())
    missing = REQUIRED_COLUMNS - set(df.columns)
    result = ImportResult()
    if missing:
        result.errors.append(f"Missing columns: {', '.join(sorted(missing))}")
        return result
    for i, row in enumerate(df.to_dict(orient="records"), start=2):  # row 1 is the header
        if all(_blank(v) for v in row.values()):
            continue
        try:
            result.events.append(parse_row(row))
        except (ValueError, TypeError) as exc:
            result.errors.append(f"Row {i}: {exc}")
    return result
