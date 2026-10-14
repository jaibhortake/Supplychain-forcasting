"""Forecast orchestration: loads data from the DB and runs the core models.

Per-series analysis (backtest, FVA, anomalies, fitted model) is cached in-process and keyed
by the DB data version, so any write anywhere invalidates it, even across workers.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.core import inventory
from app.core.baseline import BaselineModel, fit_baseline, seasonal_naive
from app.core.calendar import week_label, week_range
from app.core.context import EventSpec, WeekContext, context_for_weeks
from app.core.evaluation import (
    Anomaly,
    BacktestRow,
    detect_anomalies,
    fva_table,
    override_scorecard,
    residual_sigma,
    run_backtest,
)
from app.models import ContextEvent, Override, Product, Region, SalesRecord
from app.services.audit import current_version


class NotFoundError(LookupError):
    pass


@dataclass
class SeriesData:
    product: Product
    region: str
    weeks: list[date]
    sales: np.ndarray
    events: list[EventSpec]
    overrides: dict[date, Override]


@dataclass
class SeriesAnalysis:
    data: SeriesData
    history_context: list[WeekContext]
    model: BaselineModel
    backtest: list[BacktestRow]
    sigma: float
    fva: list[dict]
    scorecard: dict
    anomalies: list[Anomaly] = field(default_factory=list)


_cache: dict[tuple[int, str, str], SeriesAnalysis] = {}
_cache_lock = threading.Lock()


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def to_spec(e: ContextEvent) -> EventSpec:
    return EventSpec(
        id=e.id,
        name=e.name,
        event_type=e.event_type,
        start=e.start_date,
        end=e.end_date,
        multiplier=e.multiplier,
        recurring_yearly=e.recurring_yearly,
        product_code=e.product_code,
        category=e.category,
        region=e.region,
    )


def driver_dicts(ctx: WeekContext) -> list[dict]:
    return [
        {
            "event_id": d.event_id,
            "name": d.name,
            "event_type": d.event_type,
            "effect_pct": round(d.applied_effect * 100, 1),
            "raw_effect_pct": round(d.raw_effect * 100, 1),
            "damped": d.damped,
        }
        for d in ctx.drivers
    ]


class ForecastService:
    def __init__(self, session: Session, settings: Settings | None = None):
        self.session = session
        self.settings = settings or get_settings()

    # ---- loading -------------------------------------------------------
    def products(self) -> list[Product]:
        return list(self.session.scalars(select(Product).order_by(Product.code)))

    def regions(self) -> list[str]:
        return list(self.session.scalars(select(Region.code).order_by(Region.code)))

    def series_keys(self) -> list[tuple[str, str]]:
        rows = self.session.execute(
            select(SalesRecord.product_code, SalesRecord.region)
            .distinct()
            .order_by(SalesRecord.product_code, SalesRecord.region)
        )
        return [(p, r) for p, r in rows]

    def load_series(self, product_code: str, region: str) -> SeriesData:
        product = self.session.get(Product, product_code)
        if product is None:
            raise NotFoundError(f"Unknown product '{product_code}'")
        records = self.session.execute(
            select(SalesRecord.week_start, SalesRecord.units)
            .where(SalesRecord.product_code == product_code, SalesRecord.region == region)
            .order_by(SalesRecord.week_start)
        ).all()
        if not records:
            raise NotFoundError(f"No sales history for {product_code} / {region}")
        weeks = [r[0] for r in records]
        sales = np.array([r[1] for r in records], dtype=float)
        events = [
            spec
            for e in self.session.scalars(select(ContextEvent))
            if (spec := to_spec(e)).applies_to(product.code, product.category, region)
        ]
        overrides = {
            o.week_start: o
            for o in self.session.scalars(
                select(Override).where(Override.product_code == product_code, Override.region == region)
            )
        }
        return SeriesData(product, region, weeks, sales, events, overrides)

    # ---- analysis ------------------------------------------------------
    def analyze(self, product_code: str, region: str) -> SeriesAnalysis:
        key = (current_version(self.session), product_code, region)
        with _cache_lock:
            if key in _cache:
                return _cache[key]
        data = self.load_series(product_code, region)
        hist_ctx = context_for_weeks(data.events, data.weeks)
        mult = np.array([c.multiplier for c in hist_ctx])
        model = fit_baseline(data.weeks, data.sales, mult)
        rows = run_backtest(
            data.weeks,
            data.sales,
            mult,
            overrides={w: o.value for w, o in data.overrides.items()},
            window=self.settings.backtest_weeks,
            horizon=self.settings.backtest_horizon,
        )
        sigma = residual_sigma(rows)
        analysis = SeriesAnalysis(
            data=data,
            history_context=hist_ctx,
            model=model,
            backtest=rows,
            sigma=sigma,
            fva=fva_table(rows),
            scorecard=override_scorecard(rows),
            anomalies=detect_anomalies(rows, sigma, self.settings.anomaly_z_threshold),
        )
        with _cache_lock:
            for k in [k for k in _cache if k[0] != key[0]]:
                del _cache[k]
            _cache[key] = analysis
        return analysis

    # ---- forecasting ---------------------------------------------------
    def future_weeks(self, analysis: SeriesAnalysis, horizon: int) -> list[date]:
        return week_range(analysis.data.weeks[-1] + timedelta(weeks=1), horizon)

    def forecast_points(
        self,
        analysis: SeriesAnalysis,
        horizon: int,
        extra_events: list[EventSpec] | None = None,
        use_overrides: bool = True,
    ) -> list[dict]:
        data = analysis.data
        weeks = self.future_weeks(analysis, horizon)
        events = data.events + list(extra_events or [])
        contexts = context_for_weeks(events, weeks)
        base = analysis.model.predict(weeks)
        extended = np.concatenate([data.sales, np.full(horizon, np.nan)])
        n = len(data.sales)
        points = []
        for h, (w, b, ctx) in enumerate(zip(weeks, base, contexts, strict=True), start=1):
            context_value = float(b * ctx.multiplier)
            ov = data.overrides.get(w) if use_overrides else None
            final = float(ov.value) if ov else context_value
            lo, hi = inventory.interval(final, analysis.sigma, h)
            naive = seasonal_naive(extended, n + h - 1)
            points.append(
                {
                    "week": w,
                    "label": week_label(w),
                    "horizon": h,
                    "naive": None if naive is None or np.isnan(naive) else round(naive, 1),
                    "baseline": round(float(b), 1),
                    "context_multiplier": round(ctx.multiplier, 4),
                    "context": round(context_value, 1),
                    "final": round(final, 1),
                    "p10": round(lo, 1),
                    "p90": round(hi, 1),
                    "override": None
                    if not ov
                    else {"id": ov.id, "value": ov.value, "reason": ov.reason, "author": ov.author},
                    "drivers": driver_dicts(ctx),
                }
            )
        return points

    def history_points(self, analysis: SeriesAnalysis, weeks_back: int = 78) -> list[dict]:
        data = analysis.data
        backtest = {}
        for r in analysis.backtest:  # shortest-horizon backtest forecast per week
            if r.week not in backtest or r.horizon < backtest[r.week].horizon:
                backtest[r.week] = r
        start = max(len(data.weeks) - weeks_back, 0)
        out = []
        for i in range(start, len(data.weeks)):
            w = data.weeks[i]
            bt = backtest.get(w)
            out.append(
                {
                    "week": w,
                    "label": week_label(w),
                    "actual": float(data.sales[i]),
                    "forecast": round(bt.final, 1) if bt else None,
                    "baseline": round(bt.baseline, 1) if bt else None,
                    "context_multiplier": round(analysis.history_context[i].multiplier, 4),
                    "drivers": driver_dicts(analysis.history_context[i]),
                }
            )
        return out

    def stock_plan(
        self,
        analysis: SeriesAnalysis,
        points: list[dict],
        service_level: float,
        on_hand: float,
        on_order: float,
    ) -> dict:
        lead = analysis.data.product.lead_time_weeks
        finals = [p["final"] for p in points]
        main = inventory.stock_plan(finals, analysis.sigma, lead, service_level, on_hand, on_order)
        table = []
        for sl in inventory.SERVICE_LEVEL_TABLE:
            plan = inventory.stock_plan(finals, analysis.sigma, lead, sl, on_hand, on_order)
            table.append(
                {
                    "service_level": sl,
                    "safety_stock": round(plan.safety_stock),
                    "order_up_to": round(plan.order_up_to),
                    "recommended_order": plan.recommended_order,
                    "inventory_value": round(plan.order_up_to * analysis.data.product.unit_cost),
                }
            )
        return {
            "service_level": main.service_level,
            "lead_time_weeks": lead,
            "protection_weeks": main.protection_weeks,
            "expected_demand": round(main.expected_demand, 1),
            "demand_sd": round(main.demand_sd, 1),
            "safety_stock": round(main.safety_stock),
            "order_up_to": round(main.order_up_to),
            "on_hand": on_hand,
            "on_order": on_order,
            "recommended_order": main.recommended_order,
            "stockout_risk": round(main.stockout_risk, 4),
            "days_of_cover": None if main.days_of_cover is None else round(main.days_of_cover, 1),
            "unit_cost": analysis.data.product.unit_cost,
            "trade_off": table,
        }

    def forecast(
        self,
        product_code: str,
        region: str,
        horizon: int,
        service_level: float = 0.95,
        on_hand: float | None = None,
        on_order: float = 0.0,
        history_weeks: int = 78,
    ) -> dict:
        analysis = self.analyze(product_code, region)
        points = self.forecast_points(analysis, horizon)
        if on_hand is None:  # demo default: roughly one week of expected demand on hand
            on_hand = round(points[0]["final"]) if points else 0.0
        return {
            "product": product_dict(analysis.data.product),
            "region": region,
            "last_actual_week": analysis.data.weeks[-1],
            "sigma": round(analysis.sigma, 4),
            "history": self.history_points(analysis, history_weeks),
            "forecast": points,
            "stock": self.stock_plan(analysis, points, service_level, on_hand, on_order),
            "accuracy": analysis.fva,
        }


def product_dict(p: Product) -> dict:
    return {
        "code": p.code,
        "name": p.name,
        "category": p.category,
        "unit_cost": p.unit_cost,
        "lead_time_weeks": p.lead_time_weeks,
    }


def upcoming_events(session: Session, start: date, weeks: int, limit: int = 15) -> list[dict]:
    """Events overlapping the next `weeks` weeks; festival rows (one per category/region) are grouped."""
    end = start + timedelta(weeks=weeks)
    groups: dict[tuple[str, date], dict] = {}
    for e in session.scalars(select(ContextEvent)):
        for s, f in to_spec(e).occurrences(start.year, end.year):
            if s > end or f < start:
                continue
            g = groups.setdefault(
                (e.name, s),
                {"id": e.id, "type": e.event_type, "end": f, "mult": e.multiplier, "what": set(), "where": set()},
            )
            if abs(e.multiplier - 1) > abs(g["mult"] - 1):
                g["mult"] = e.multiplier
            g["what"].add(e.product_code or (e.category or "all products").replace("_", " "))
            g["where"].add(e.region or "all regions")
    out = [
        dict(
            id=g["id"],
            name=name,
            event_type=g["type"],
            start_date=s,
            end_date=g["end"],
            multiplier=g["mult"],
            scope=f"{', '.join(sorted(g['what']))} · {', '.join(sorted(g['where']))}",
        )
        for (name, s), g in groups.items()
    ]
    out.sort(key=lambda u: u["start_date"])
    return out[:limit]
