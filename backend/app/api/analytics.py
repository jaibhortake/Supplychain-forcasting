from fastapi import APIRouter, Query

from app.api.deps import ServiceDep
from app.config import get_settings
from app.core.calendar import week_label
from app.core.context import week_context
from app.core.evaluation import fva_table, override_scorecard
from app.schemas import AnomalyOut, FvaOut

router = APIRouter(tags=["analytics"])


def _selected(svc: ServiceDep, product_code: str | None, region: str | None):
    return [
        (p, r)
        for p, r in svc.series_keys()
        if (product_code is None or p == product_code) and (region is None or r == region)
    ]


@router.get("/fva", response_model=FvaOut)
def fva(svc: ServiceDep, product_code: str | None = None, region: str | None = None):
    """Forecast Value Added: does each layer (baseline, context, planner) improve on the one before?"""
    settings = get_settings()
    series, rows = [], []
    for p, r in _selected(svc, product_code, region):
        a = svc.analyze(p, r)
        series.append({"product_code": p, "region": r, "layers": a.fva})
        rows += a.backtest
    return {
        "portfolio": fva_table(rows),
        "overrides": override_scorecard(rows),
        "series": series,
        "backtest_weeks": settings.backtest_weeks,
        "horizon_weeks": settings.backtest_horizon,
    }


@router.get("/anomalies", response_model=list[AnomalyOut])
def anomalies(
    svc: ServiceDep,
    product_code: str | None = None,
    region: str | None = None,
    kind: str | None = Query(default=None, pattern="^(unexplained|mis-sized)$"),
):
    out = []
    for p, r in _selected(svc, product_code, region):
        a = svc.analyze(p, r)
        for an in a.anomalies:
            if kind and an.kind != kind:
                continue
            ctx = week_context(a.data.events, an.week)
            out.append(
                {
                    "product_code": p,
                    "region": r,
                    "week": an.week,
                    "label": week_label(an.week),
                    "actual": an.actual,
                    "expected": round(an.expected, 1),
                    "deviation_pct": round((an.actual / an.expected - 1) * 100, 1) if an.expected else 0.0,
                    "z_score": round(an.z_score, 2),
                    "direction": an.direction,
                    "kind": an.kind,
                    "events": [d.name for d in ctx.drivers],
                }
            )
    out.sort(key=lambda x: x["week"], reverse=True)
    return out
