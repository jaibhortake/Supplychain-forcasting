import io

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlalchemy import select

from app.api.deps import ActorDep, SessionDep
from app.api.events import MAX_UPLOAD_BYTES
from app.core.calendar import week_start
from app.models import Product, Region, SalesRecord
from app.schemas import ImportReport
from app.services import audit

router = APIRouter(tags=["sales"])

SALES_COLUMNS = {"product_code", "region", "week_start", "units"}


@router.get("/sales/{product_code}/{region}")
def get_sales(product_code: str, region: str, session: SessionDep) -> list[dict]:
    rows = session.execute(
        select(SalesRecord.week_start, SalesRecord.units)
        .where(SalesRecord.product_code == product_code, SalesRecord.region == region)
        .order_by(SalesRecord.week_start)
    ).all()
    return [{"week_start": w, "units": u} for w, u in rows]


@router.post("/sales/import", response_model=ImportReport)
async def import_sales(session: SessionDep, actor: ActorDep, file: UploadFile = File(...)):
    """Load real weekly sales. CSV columns: product_code, region, week_start, units
    (optional: product_name, category). Existing weeks are overwritten; dates snap to Monday."""
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "File too large (max 5 MB)")
    try:
        df = (
            pd.read_csv(io.BytesIO(content))
            if (file.filename or "").lower().endswith(".csv")
            else pd.read_excel(io.BytesIO(content))
        )
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Could not read file: {exc}") from exc
    df.columns = [str(c).strip().lower() for c in df.columns]
    missing = SALES_COLUMNS - set(df.columns)
    if missing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Missing columns: {', '.join(sorted(missing))}")

    errors: list[str] = []
    created = 0
    existing = {(s.product_code, s.region, s.week_start): s for s in session.scalars(select(SalesRecord))}
    for i, row in enumerate(df.to_dict(orient="records"), start=2):
        try:
            code = str(row["product_code"]).strip().upper()
            region = str(row["region"]).strip().title()
            week = week_start(pd.to_datetime(row["week_start"]).date())
            units = float(row["units"])
            if pd.isna(units) or units < 0:
                raise ValueError("units must be a non-negative number")
        except (ValueError, TypeError) as exc:
            errors.append(f"Row {i}: {exc}")
            continue
        if session.get(Product, code) is None:
            session.add(
                Product(
                    code=code,
                    name=str(row.get("product_name") or code),
                    category=str(row.get("category") or "general"),
                    unit_cost=0.0,
                    lead_time_weeks=2,
                )
            )
            session.flush()
        if session.get(Region, region) is None:
            session.add(Region(code=region, name=region))
            session.flush()
        key = (code, region, week)
        if key in existing:
            existing[key].units = units
        else:
            rec = SalesRecord(product_code=code, region=region, week_start=week, units=units)
            session.add(rec)
            existing[key] = rec
        created += 1
    audit.record(
        session,
        actor,
        "import",
        "sales",
        file.filename or "upload",
        f"Imported {created} weekly sales rows",
        {"errors": errors[:50]},
    )
    session.commit()
    return ImportReport(created=created, errors=errors)
