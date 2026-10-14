"""FastAPI application entry point.

Run locally:  uvicorn app.main:app --reload
API docs:     http://localhost:8000/docs
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import analytics, chat, events, forecast, meta, overrides, sales
from app.config import get_settings
from app.db import SessionLocal, init_db
from app.services.forecast_service import NotFoundError
from app.services.seed import seed_database

settings = get_settings()
logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if settings.seed_on_startup:
        with SessionLocal() as session:
            if seed_database(session):
                log.info("Seeded demo database")
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Context-aware demand forecasting: statistical baseline + business events + planner overrides, "
    "with Forecast Value Added, prediction intervals, stock recommendations and a grounded LLM assistant.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(NotFoundError)
@app.exception_handler(LookupError)
async def not_found_handler(_: Request, exc: LookupError):
    return JSONResponse(status_code=404, content={"detail": str(exc.args[0]) if exc.args else "Not found"})


for module in (meta, forecast, analytics, events, overrides, sales, chat):
    app.include_router(module.router, prefix="/api")
