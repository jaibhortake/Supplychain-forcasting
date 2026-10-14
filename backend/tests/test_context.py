from datetime import date

import pytest

from app.core.context import EventSpec, combine, event_effect_in_week, week_context


def ev(start, end, mult, recurring=False, name="e", **kw):
    return EventSpec(None, name, "promotion", start, end, mult, recurring, **kw)


def test_full_week_gets_full_effect():
    e = ev(date(2025, 11, 3), date(2025, 11, 9), 1.20)  # Mon-Sun
    assert event_effect_in_week(e, date(2025, 11, 3)) == pytest.approx(0.20)


def test_partial_week_is_scaled_by_days():
    e = ev(date(2025, 11, 7), date(2025, 11, 20), 1.14)  # Fri onwards: 3 of 7 days
    assert event_effect_in_week(e, date(2025, 11, 3)) == pytest.approx(0.14 * 3 / 7)


def test_recurring_event_repeats_and_crosses_new_year():
    e = ev(date(2023, 12, 26), date(2024, 1, 8), 1.10, recurring=True)
    assert event_effect_in_week(e, date(2026, 12, 28)) == pytest.approx(0.10)  # Dec 28 - Jan 3
    assert event_effect_in_week(e, date(2027, 1, 4)) == pytest.approx(0.10 * 5 / 7)  # Jan 4-8
    assert event_effect_in_week(e, date(2026, 6, 1)) == 0


def test_diminishing_returns_after_two_uplifts():
    effects = [
        (ev(None, None, 1.3, name="a"), 0.3),
        (ev(None, None, 1.2, name="b"), 0.2),
        (ev(None, None, 1.1, name="c"), 0.1),
    ]
    ctx = combine(effects)
    assert ctx.multiplier == pytest.approx(1.3 * 1.2 * 1.05)
    assert [d.damped for d in ctx.drivers] == [False, False, True]


def test_reductions_apply_in_full_and_total_is_clipped():
    ctx = combine([(ev(None, None, 0.1, name="x"), -0.9), (ev(None, None, 0.5, name="y"), -0.5)])
    assert ctx.multiplier == pytest.approx(0.2)  # clipped at the floor


def test_filters_match_product_category_region():
    e = ev(date(2025, 1, 1), date(2025, 1, 7), 1.1, category="television", region="South")
    assert e.applies_to("TV-S2", "television", "South")
    assert not e.applies_to("TV-S2", "television", "North")
    assert not e.applies_to("AC-X1", "air_conditioner", "South")
    assert week_context([e], date(2024, 12, 30)).multiplier > 1
