from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import ActorDep, SessionDep
from app.config import get_settings
from app.models import SalesRecord
from app.schemas import MetaOut, ProductOut
from app.services import audit, llm
from app.services.forecast_service import ForecastService
from app.services.seed import reset_database, seed_database

router = APIRouter(tags=["meta"])

EVENT_TYPES = ["promotion", "stockout", "distributor", "seasonal", "temperature", "festival", "other"]


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "llm": {
            "available": llm.is_available(),
            "model": settings.ollama_model,
            "url": settings.ollama_url,
        },
    }


@router.get("/meta", response_model=MetaOut)
def meta(session: SessionDep) -> MetaOut:
    svc = ForecastService(session)
    return MetaOut(
        products=[ProductOut.model_validate(p) for p in svc.products()],
        regions=svc.regions(),
        event_types=EVENT_TYPES,
        last_actual_week=session.scalar(select(func.max(SalesRecord.week_start))),
        data_version=audit.current_version(session),
    )


@router.post("/admin/reset-demo")
def reset_demo(session: SessionDep, actor: ActorDep) -> dict:
    """Wipe everything and regenerate the demo dataset."""
    reset_database(session)
    seed_database(session)
    audit.record(session, actor, "reset", "database", "-", "Demo data reset")
    session.commit()
    return {"status": "reseeded"}
