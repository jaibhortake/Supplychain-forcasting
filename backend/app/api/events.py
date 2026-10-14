from datetime import date

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from sqlalchemy import delete, select

from app.api.deps import ActorDep, SessionDep
from app.models import ContextEvent
from app.schemas import EventIn, EventOut, ImportReport
from app.services import audit
from app.services.excel_import import parse_events_frame, read_table
from app.services.festivals import FESTIVAL_SOURCE, available_years, festival_event_rows, festival_occurrences

router = APIRouter(tags=["context events"])

MAX_UPLOAD_BYTES = 5 * 1024 * 1024


@router.get("/events", response_model=list[EventOut])
def list_events(
    session: SessionDep,
    product_code: str | None = None,
    region: str | None = None,
    event_type: str | None = None,
    source: str | None = None,
    active_from: date | None = Query(default=None, description="only events ending on/after this date (or recurring)"),
):
    q = select(ContextEvent).order_by(ContextEvent.start_date.desc())
    if product_code:
        q = q.where((ContextEvent.product_code == product_code) | (ContextEvent.product_code.is_(None)))
    if region:
        q = q.where((ContextEvent.region == region) | (ContextEvent.region.is_(None)))
    if event_type:
        q = q.where(ContextEvent.event_type == event_type)
    if source:
        q = q.where(ContextEvent.source == source)
    if active_from:
        q = q.where((ContextEvent.end_date >= active_from) | ContextEvent.recurring_yearly)
    return list(session.scalars(q))


@router.post("/events", response_model=EventOut, status_code=status.HTTP_201_CREATED)
def create_event(body: EventIn, session: SessionDep, actor: ActorDep):
    event = ContextEvent(**body.model_dump(), source="manual")
    session.add(event)
    session.flush()
    audit.record(
        session,
        actor,
        "create",
        "event",
        event.id,
        f"Added event '{event.name}' (x{event.multiplier})",
        body.model_dump(mode="json"),
    )
    session.commit()
    return event


@router.put("/events/{event_id}", response_model=EventOut)
def update_event(event_id: int, body: EventIn, session: SessionDep, actor: ActorDep):
    event = session.get(ContextEvent, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    before = EventIn.model_validate(event, from_attributes=True).model_dump(mode="json")
    for k, v in body.model_dump().items():
        setattr(event, k, v)
    audit.record(
        session,
        actor,
        "update",
        "event",
        event.id,
        f"Edited event '{event.name}'",
        {"before": before, "after": body.model_dump(mode="json")},
    )
    session.commit()
    return event


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(event_id: int, session: SessionDep, actor: ActorDep):
    event = session.get(ContextEvent, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
    snapshot = EventIn.model_validate(event, from_attributes=True).model_dump(mode="json")
    session.delete(event)
    audit.record(session, actor, "delete", "event", event_id, f"Deleted event '{event.name}'", snapshot)
    session.commit()


def _event_key(e: dict) -> tuple:
    keys = ("name", "event_type", "product_code", "category", "region", "start_date", "end_date", "multiplier")
    return tuple(e.get(k) for k in keys)


@router.post("/events/import", response_model=ImportReport)
async def import_events(session: SessionDep, actor: ActorDep, file: UploadFile = File(...)):
    """Upload the planner Excel/CSV template (same layout as data/dummy_data.xlsx)."""
    name = file.filename or "upload"
    if not name.lower().endswith((".xlsx", ".xls", ".csv")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Upload an .xlsx or .csv file")
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "File too large (max 5 MB)")
    try:
        frame = read_table(content, name)
    except Exception as exc:  # pandas raises many different types for bad files
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Could not read file: {exc}") from exc
    result = parse_events_frame(frame)
    existing = {_event_key(e.__dict__) for e in session.scalars(select(ContextEvent))}
    new_rows = []
    for row in result.events:
        if _event_key(row) in existing:
            result.errors.append(f"Skipped duplicate: '{row['name']}' ({row['start_date']} to {row['end_date']})")
            continue
        existing.add(_event_key(row))
        new_rows.append(row)
    result.events = new_rows
    session.add_all(ContextEvent(**row) for row in new_rows)
    audit.record(
        session,
        actor,
        "import",
        "event",
        name,
        f"Imported {len(result.events)} events from {name}",
        {"errors": result.errors},
    )
    session.commit()
    return ImportReport(created=len(result.events), errors=result.errors)


@router.get("/festivals")
def festivals(year: int | None = None) -> dict:
    years = [year] if year else None
    return {
        "years": available_years(),
        "festivals": [
            {
                "key": o.key,
                "name": o.name,
                "date": o.day,
                "window_start": o.window_start,
                "window_end": o.window_end,
                "regions": list(o.regions) if o.regions else ["All"],
                "uplift": o.uplift,
            }
            for o in festival_occurrences(years)
        ],
    }


@router.post("/festivals/sync", response_model=ImportReport)
def sync_festivals(session: SessionDep, actor: ActorDep) -> ImportReport:
    """Re-create all festival context events from data/festivals.json (after you edit it)."""
    session.execute(delete(ContextEvent).where(ContextEvent.source == FESTIVAL_SOURCE))
    rows = festival_event_rows()
    session.add_all(ContextEvent(**r) for r in rows)
    audit.record(session, actor, "sync", "event", "festivals", f"Synced {len(rows)} festival events")
    session.commit()
    return ImportReport(created=len(rows), errors=[])
