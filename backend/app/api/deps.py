import re
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.db import get_session
from app.services.forecast_service import ForecastService

_SAFE_ACTOR = re.compile(r"[^A-Za-z0-9._@ -]")

SessionDep = Annotated[Session, Depends(get_session)]


def get_actor(x_user: Annotated[str | None, Header()] = None) -> str:
    """Who is making the change. Taken from the X-User header (no auth in this demo build)."""
    actor = _SAFE_ACTOR.sub("", (x_user or "").strip())[:80]
    return actor or "anonymous"


def get_service(session: SessionDep) -> ForecastService:
    return ForecastService(session)


ActorDep = Annotated[str, Depends(get_actor)]
ServiceDep = Annotated[ForecastService, Depends(get_service)]
