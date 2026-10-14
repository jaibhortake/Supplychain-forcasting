"""Demo data seeding: catalogue, context events, synthetic sales and planner overrides."""

from __future__ import annotations

import logging
import random
from datetime import date, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.core.calendar import week_start
from app.models import AuditLog, ContextEvent, DataVersion, Override, Product, Region, SalesRecord
from app.services import audit
from app.services.excel_import import parse_events_frame, read_table
from app.services.festivals import festival_event_rows
from app.services.forecast_service import ForecastService, clear_cache, to_spec
from app.services.synthetic import PRODUCTS, REGIONS, generate_sales

log = logging.getLogger(__name__)
SEED_ACTOR = "system:seed"


def planner_events(history_end: date) -> list[dict]:
    """Extra realistic events on top of the Excel sheet; one-offs are placed relative to today."""

    def rel(weeks: int) -> date:
        return week_start(history_end) + timedelta(weeks=weeks)

    def ev(name, event_type, description, start, end, mult, product=None, region=None, recurring=False):
        return {
            "name": name,
            "event_type": event_type,
            "description": description,
            "product_code": product,
            "category": None,
            "region": region,
            "start_date": start,
            "end_date": end,
            "multiplier": mult,
            "recurring_yearly": recurring,
            "source": "seed",
        }

    return [
        ev(
            "Pre-summer AC Exchange Offer",
            "promotion",
            "Old-AC exchange discount ahead of summer.",
            date(2023, 3, 15),
            date(2023, 4, 10),
            1.18,
            product="AC-X1",
            recurring=True,
        ),
        ev(
            "Summer Fridge Fest",
            "promotion",
            "Retailer-funded refrigerator promotion in the West.",
            date(2023, 5, 1),
            date(2023, 5, 21),
            1.15,
            product="REF-C3",
            region="West",
            recurring=True,
        ),
        ev(
            "Year-end Clearance",
            "promotion",
            "Year-end TV clearance across all regions.",
            date(2023, 12, 26),
            date(2024, 1, 8),
            1.12,
            product="TV-S2",
            recurring=True,
        ),
        ev(
            "Warehouse stockout - REF-C3 North",
            "stockout",
            "Lucknow warehouse ran dry for a week.",
            rel(-30),
            rel(-30) + timedelta(days=6),
            0.6,
            product="REF-C3",
            region="North",
        ),
        ev(
            "New distributor onboarding - East",
            "distributor",
            "12 new distributors onboarded in Odisha & WB.",
            rel(-20),
            rel(-17) + timedelta(days=6),
            1.12,
            product="TV-S2",
            region="East",
        ),
        ev(
            "Compressor supply delay",
            "stockout",
            "Supplier warned of a two-week compressor shortage.",
            rel(3),
            rel(4) + timedelta(days=6),
            0.8,
            product="AC-X1",
            region="South",
        ),
        ev(
            "Mega distributor scheme",
            "distributor",
            "Quarter-end distributor incentive scheme.",
            rel(6),
            rel(7) + timedelta(days=6),
            1.15,
            product="REF-C3",
        ),
    ]


OPTIMISTIC_REASONS = [
    "Festive season - expect strong sell-through",
    "Distributor feedback says demand is picking up",
    "Gut feel: last year's peak was bigger",
    "Sales team pushing for higher allocation",
]
INFORMED_REASONS = [
    "Key account confirmed a bulk order",
    "Local heat forecast well above normal",
    "Competitor launched a price cut nearby",
    "Channel check: dealer inventory already high",
]


def _seed_overrides(session: Session, seed: int) -> None:
    """Historical planner overrides: mostly optimistic gut-feel, sometimes genuinely informed."""
    rng = random.Random(seed)
    service = ForecastService(session)
    for product_code, region in service.series_keys():
        analysis = service.analyze(product_code, region)
        rows = [r for r in analysis.backtest if r.horizon == 1]
        if not rows:
            continue
        for r in rng.sample(rows, k=min(2, len(rows))):
            informed = rng.random() < 0.35
            if informed:
                value = r.actual * rng.uniform(0.94, 1.06)
                reason = rng.choice(INFORMED_REASONS)
            else:
                value = r.context * rng.uniform(1.12, 1.35)
                reason = rng.choice(OPTIMISTIC_REASONS)
            session.add(
                Override(
                    product_code=product_code,
                    region=region,
                    week_start=r.week,
                    value=round(value),
                    system_value=round(r.context, 1),
                    reason=reason,
                    author=rng.choice(["anita.sharma", "rahul.iyer", "planner.east", "vikram.patil"]),
                )
            )
        # one upcoming override per series for a third of the series
        if rng.random() < 0.34:
            pts = service.forecast_points(analysis, 3, use_overrides=False)
            target = pts[-1]
            session.add(
                Override(
                    product_code=product_code,
                    region=region,
                    week_start=target["week"],
                    value=round(target["context"] * 1.15),
                    system_value=target["context"],
                    reason="Distributor pre-booking higher than usual",
                    author="anita.sharma",
                )
            )


def reset_database(session: Session) -> None:
    for model in (Override, SalesRecord, ContextEvent, AuditLog, DataVersion, Product, Region):
        session.execute(delete(model))
    session.commit()
    clear_cache()


def seed_database(session: Session, settings: Settings | None = None, today: date | None = None) -> bool:
    """Populate an empty database with demo data. Returns False if data already exists."""
    settings = settings or get_settings()
    if session.scalar(select(func.count()).select_from(Product)):
        return False

    today = today or date.today()
    history_end = week_start(today) - timedelta(weeks=1)  # last complete week

    session.add_all(Product(**p) for p in PRODUCTS)
    session.add_all(Region(code=r, name=r) for r in REGIONS)

    event_rows: list[dict] = []
    excel = settings.seed_excel_path
    if excel.exists():
        result = parse_events_frame(read_table(excel.read_bytes(), excel.name))
        event_rows += result.events
        for err in result.errors:
            log.warning("Seed Excel: %s", err)
    event_rows += planner_events(history_end)
    event_rows += festival_event_rows()
    events = [ContextEvent(**row) for row in event_rows]
    session.add_all(events)
    session.flush()

    sales = generate_sales([to_spec(e) for e in events], history_end, seed=settings.random_seed)
    session.add_all(
        SalesRecord(product_code=p, region=r, week_start=w, units=u)
        for (p, r), series in sales.items()
        for w, u in series
    )
    audit.record(
        session,
        SEED_ACTOR,
        "seed",
        "database",
        "-",
        f"Seeded {len(PRODUCTS)} products x {len(REGIONS)} regions, {len(events)} context events, "
        f"sales history up to {history_end:%d %b %Y}",
    )
    session.commit()

    _seed_overrides(session, settings.random_seed)
    audit.record(session, SEED_ACTOR, "seed", "override", "-", "Seeded example planner overrides")
    session.commit()
    log.info("Demo data seeded (history up to %s)", history_end)
    return True
