from datetime import timedelta

from fastapi import APIRouter, Query

from app.api.deps import ServiceDep
from app.core.context import EventSpec
from app.core.evaluation import fva_table
from app.schemas import ForecastOut, OverviewOut, ScenarioIn, ScenarioOut
from app.services.forecast_service import upcoming_events

router = APIRouter(tags=["forecast"])


@router.get("/forecast/{product_code}/{region}", response_model=ForecastOut)
def get_forecast(
    product_code: str,
    region: str,
    svc: ServiceDep,
    horizon: int = Query(default=12, ge=1, le=52),
    service_level: float = Query(default=0.95, ge=0.5, lt=1.0),
    on_hand: float | None = Query(default=None, ge=0),
    on_order: float = Query(default=0.0, ge=0),
    history_weeks: int = Query(default=78, ge=4, le=520),
):
    return svc.forecast(product_code, region, horizon, service_level, on_hand, on_order, history_weeks)


def _wape(layers: list[dict], name: str) -> float | None:
    return next((m["wape"] for m in layers if m["layer"] == name), None)


@router.get("/overview", response_model=OverviewOut)
def overview(svc: ServiceDep):
    series, all_rows = [], []
    open_anomalies = 0
    total_next = total_last = 0.0
    last_week = None
    for product_code, region in svc.series_keys():
        a = svc.analyze(product_code, region)
        pts = svc.forecast_points(a, 4)
        next4 = sum(p["final"] for p in pts)
        base4 = sum(p["baseline"] for p in pts)
        last4 = float(a.data.sales[-4:].sum())
        stock = svc.stock_plan(a, pts, 0.95, on_hand=round(pts[0]["final"]), on_order=0)
        naive, final = _wape(a.fva, "naive"), _wape(a.fva, "final")
        series.append(
            {
                "product_code": product_code,
                "product_name": a.data.product.name,
                "region": region,
                "next_4w_demand": round(next4, 1),
                "last_4w_actual": last4,
                "change_pct": round((next4 / last4 - 1) * 100, 1) if last4 else None,
                "context_uplift_pct": round((next4 / base4 - 1) * 100, 1) if base4 else 0.0,
                "wape": final,
                "fva_vs_naive": naive - final if naive is not None and final is not None else None,
                "anomalies": len(a.anomalies),
                "stockout_risk": stock["stockout_risk"],
                "sparkline": [float(x) for x in a.data.sales[-26:]] + [p["final"] for p in pts],
            }
        )
        all_rows += a.backtest
        open_anomalies += len(a.anomalies)
        total_next += next4
        total_last += last4
        last_week = a.data.weeks[-1]

    if last_week is None:
        raise LookupError("No sales data loaded")
    return {
        "last_actual_week": last_week,
        "total_next_4w": round(total_next, 1),
        "total_last_4w": total_last,
        "portfolio_accuracy": fva_table(all_rows),
        "open_anomalies": open_anomalies,
        "upcoming_events": upcoming_events(svc.session, last_week + timedelta(days=7), weeks=12),
        "series": series,
    }


@router.post("/scenarios/simulate", response_model=ScenarioOut)
def simulate(body: ScenarioIn, svc: ServiceDep):
    a = svc.analyze(body.product_code, body.region)
    extra = [EventSpec(None, ev.name, ev.event_type, ev.start_date, ev.end_date, ev.multiplier) for ev in body.events]
    current = svc.forecast_points(a, body.horizon)
    scenario = svc.forecast_points(a, body.horizon, extra_events=extra)
    on_hand = body.on_hand if body.on_hand is not None else round(current[0]["final"])
    total_current = sum(p["final"] for p in current)
    total_scenario = sum(p["final"] for p in scenario)
    return {
        "weeks": [p["label"] for p in current],
        "current": current,
        "scenario": scenario,
        "current_stock": svc.stock_plan(a, current, body.service_level, on_hand, 0),
        "scenario_stock": svc.stock_plan(a, scenario, body.service_level, on_hand, 0),
        "total_current": round(total_current, 1),
        "total_scenario": round(total_scenario, 1),
        "change_pct": round((total_scenario / total_current - 1) * 100, 2) if total_current else None,
    }
