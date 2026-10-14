from datetime import date

import numpy as np
import pytest

from app.config import DATA_DIR
from app.core import metrics
from app.core.baseline import fit_baseline, seasonal_naive
from app.core.calendar import week_range
from app.core.inventory import interval, stock_plan
from app.services.excel_import import parse_events_frame, parse_multiplier, read_table


def test_wape_and_bias():
    assert metrics.wape([100, 100], [90, 120]) == pytest.approx(15.0)
    assert metrics.bias([100, 100], [90, 120]) == pytest.approx(5.0)
    assert metrics.wape([0, 0], [1, 1]) is None
    assert metrics.mape([0, 100], [5, 110]) == pytest.approx(10.0)  # zero actuals skipped


def test_baseline_learns_seasonality_and_ignores_known_promos():
    weeks = week_range(date(2022, 1, 3), 156)
    season = np.array([1 + 0.5 * np.sin(2 * np.pi * w.isocalendar()[1] / 52) for w in weeks])
    sales = 100 * season
    mult = np.ones(len(weeks))
    mult[100] = 1.5  # a promo week, known to the model
    sales[100] *= 1.5
    model = fit_baseline(weeks, sales, mult)
    future = week_range(date(2025, 1, 6), 52)
    pred = model.predict(future)
    expected = np.array([100 * (1 + 0.5 * np.sin(2 * np.pi * w.isocalendar()[1] / 52)) for w in future])
    assert metrics.wape(expected, pred) < 8


def test_seasonal_naive():
    s = np.arange(60, dtype=float)
    assert seasonal_naive(s, 55) == 3.0
    assert seasonal_naive(s, 10) is None


def test_interval_contains_point_and_widens_with_horizon():
    lo1, hi1 = interval(100, 0.1, 1)
    lo4, hi4 = interval(100, 0.1, 4)
    assert lo1 < 100 < hi1
    assert hi4 - lo4 > hi1 - lo1


def test_stock_plan_orders_up_to_target():
    plan = stock_plan([100, 100, 100], sigma=0.1, lead_time_weeks=2, service_level=0.95, on_hand=50)
    assert plan.protection_weeks == 3
    assert plan.safety_stock > 0
    assert plan.recommended_order == pytest.approx(plan.order_up_to - 50, abs=1)
    assert plan.stockout_risk > 0.99
    higher = stock_plan([100, 100, 100], sigma=0.1, lead_time_weeks=2, service_level=0.99)
    assert higher.safety_stock > plan.safety_stock


@pytest.mark.parametrize(
    "formula,level,etype,expected",
    [
        ("Multiplier: 1.20 (High), 1.00 (Default)", "High", "distributor", 1.20),
        ("Multiplier: 1.20 (High), 1.00 (Default)", "Low", "distributor", 1.00),
        ("Multiplier: 0.85", "Low", "stockout", 0.85),
        (None, "Low", "seasonal", 1.05),
        (None, "High", "stockout", 0.80),
    ],
)
def test_parse_multiplier(formula, level, etype, expected):
    assert parse_multiplier(formula, level, etype) == pytest.approx(expected)


def test_original_excel_sheet_imports_cleanly():
    path = DATA_DIR / "dummy_data.xlsx"
    result = parse_events_frame(read_table(path.read_bytes(), path.name))
    assert result.errors == []
    assert len(result.events) == 8
    surge = next(e for e in result.events if e["name"].startswith("Distributor Surge"))
    assert surge["multiplier"] == pytest.approx(1.20)
    assert not surge["recurring_yearly"]
    diwali = next(e for e in result.events if e["name"] == "Diwali Festive Promo - TV-S2 South")
    assert diwali["recurring_yearly"] and diwali["region"] == "South" and diwali["product_code"] == "TV-S2"
