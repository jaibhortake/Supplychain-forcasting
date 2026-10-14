from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import ActorDep, SessionDep
from app.core.calendar import week_label, week_start
from app.models import AuditLog, Override, Product, Region
from app.schemas import AuditOut, OverrideIn, OverrideOut
from app.services import audit
from app.services.forecast_service import ForecastService

router = APIRouter(tags=["overrides & audit"])


@router.get("/overrides", response_model=list[OverrideOut])
def list_overrides(session: SessionDep, product_code: str | None = None, region: str | None = None):
    q = select(Override).order_by(Override.week_start.desc())
    if product_code:
        q = q.where(Override.product_code == product_code)
    if region:
        q = q.where(Override.region == region)
    return list(session.scalars(q))


@router.post("/overrides", response_model=OverrideOut, status_code=status.HTTP_201_CREATED)
def upsert_override(body: OverrideIn, session: SessionDep, actor: ActorDep):
    """Set (or replace) the planner forecast for one product/region/week. A reason is mandatory."""
    if session.get(Product, body.product_code) is None or session.get(Region, body.region) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown product or region")
    week = week_start(body.week_start)

    svc = ForecastService(session)
    analysis = svc.analyze(body.product_code, body.region)
    system_value = None
    if week > analysis.data.weeks[-1]:
        horizon = (week - analysis.data.weeks[-1]).days // 7
        if horizon > 52:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Overrides are limited to the next 52 weeks")
        system_value = svc.forecast_points(analysis, horizon, use_overrides=False)[-1]["context"]

    existing = session.scalar(
        select(Override).where(
            Override.product_code == body.product_code, Override.region == body.region, Override.week_start == week
        )
    )
    previous = existing.value if existing else None
    if existing:
        existing.value, existing.reason, existing.author = body.value, body.reason, actor
        existing.system_value = system_value
        ov = existing
    else:
        ov = Override(
            product_code=body.product_code,
            region=body.region,
            week_start=week,
            value=body.value,
            system_value=system_value,
            reason=body.reason,
            author=actor,
        )
        session.add(ov)
    session.flush()
    audit.record(
        session,
        actor,
        "update" if existing else "create",
        "override",
        ov.id,
        f"{body.product_code} {body.region} {week_label(week)}: {previous if previous is not None else system_value} "
        f"-> {body.value:g} ({body.reason})",
        {"previous": previous, "system_value": system_value, "value": body.value, "reason": body.reason},
    )
    session.commit()
    return ov


@router.delete("/overrides/{override_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_override(override_id: int, session: SessionDep, actor: ActorDep):
    ov = session.get(Override, override_id)
    if ov is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Override not found")
    session.delete(ov)
    audit.record(
        session,
        actor,
        "delete",
        "override",
        override_id,
        f"Removed override {ov.product_code} {ov.region} {week_label(ov.week_start)} ({ov.value:g})",
    )
    session.commit()


@router.get("/audit", response_model=list[AuditOut])
def audit_log(
    session: SessionDep,
    entity_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    q = select(AuditLog).order_by(AuditLog.timestamp.desc(), AuditLog.id.desc()).limit(limit).offset(offset)
    if entity_type:
        q = q.where(AuditLog.entity_type == entity_type)
    return list(session.scalars(q))
