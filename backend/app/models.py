"""ORM models."""

from datetime import UTC, date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Product(Base):
    __tablename__ = "products"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(64))
    unit_cost: Mapped[float] = mapped_column(Float, default=0.0)
    lead_time_weeks: Mapped[int] = mapped_column(Integer, default=2)


class Region(Base):
    __tablename__ = "regions"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))


class SalesRecord(Base):
    __tablename__ = "sales"
    __table_args__ = (UniqueConstraint("product_code", "region", "week_start", name="uq_sales_series_week"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_code: Mapped[str] = mapped_column(ForeignKey("products.code", ondelete="CASCADE"), index=True)
    region: Mapped[str] = mapped_column(ForeignKey("regions.code", ondelete="CASCADE"), index=True)
    week_start: Mapped[date] = mapped_column(Date, index=True)
    units: Mapped[float] = mapped_column(Float)


class ContextEvent(Base):
    """A business event that moves demand: promotion, stockout, festival, etc.

    `product_code`, `category` and `region` are filters; NULL means "applies to all".
    """

    __tablename__ = "context_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    product_code: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    region: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    multiplier: Mapped[float] = mapped_column(Float)
    recurring_yearly: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(32), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Override(Base):
    """A planner's manual forecast for one product/region/week."""

    __tablename__ = "overrides"
    __table_args__ = (UniqueConstraint("product_code", "region", "week_start", name="uq_override_series_week"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_code: Mapped[str] = mapped_column(ForeignKey("products.code", ondelete="CASCADE"), index=True)
    region: Mapped[str] = mapped_column(ForeignKey("regions.code", ondelete="CASCADE"), index=True)
    week_start: Mapped[date] = mapped_column(Date)
    value: Mapped[float] = mapped_column(Float)
    system_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(32))
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(Text)
    details: Mapped[str] = mapped_column(Text, default="{}")


class DataVersion(Base):
    """Single-row counter bumped on every write; used to invalidate forecast caches across workers."""

    __tablename__ = "data_version"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=0)
