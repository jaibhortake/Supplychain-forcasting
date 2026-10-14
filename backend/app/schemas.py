"""Request/response models for the public API."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator


def _as_utc(v: datetime) -> datetime:
    """SQLite drops tzinfo; stored timestamps are UTC, so make that explicit in the API."""
    return v.replace(tzinfo=UTC) if v.tzinfo is None else v


UTCDateTime = Annotated[datetime, AfterValidator(_as_utc)]

EventType = Literal["promotion", "stockout", "distributor", "seasonal", "temperature", "festival", "other"]


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    name: str
    category: str
    unit_cost: float
    lead_time_weeks: int


class MetaOut(BaseModel):
    products: list[ProductOut]
    regions: list[str]
    event_types: list[str]
    last_actual_week: date | None
    data_version: int


# ---- context events ----------------------------------------------------------
class EventBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    event_type: EventType
    description: str = ""
    product_code: str | None = None
    category: str | None = None
    region: str | None = None
    start_date: date
    end_date: date
    multiplier: float = Field(gt=0.1, le=5.0, description="1.15 = +15% demand, 0.8 = -20%")
    recurring_yearly: bool = False

    @model_validator(mode="after")
    def _check_window(self):
        if self.end_date < self.start_date and not self.recurring_yearly:
            raise ValueError("end_date must be on or after start_date")
        if (self.end_date - self.start_date).days > 366:
            raise ValueError("event window cannot exceed one year")
        return self


class EventIn(EventBase):
    pass


class EventOut(EventBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    source: str
    created_at: UTCDateTime
    updated_at: UTCDateTime


class ImportReport(BaseModel):
    created: int
    errors: list[str]


# ---- overrides ---------------------------------------------------------------
class OverrideIn(BaseModel):
    product_code: str
    region: str
    week_start: date
    value: float = Field(ge=0)
    reason: str = Field(min_length=3, max_length=500)


class OverrideOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_code: str
    region: str
    week_start: date
    value: float
    system_value: float | None
    reason: str
    author: str
    created_at: UTCDateTime


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    timestamp: UTCDateTime
    actor: str
    action: str
    entity_type: str
    entity_id: str
    summary: str
    details: str


# ---- forecasting -------------------------------------------------------------
class DriverOut(BaseModel):
    event_id: int | None
    name: str
    event_type: str
    effect_pct: float
    raw_effect_pct: float
    damped: bool


class OverrideRef(BaseModel):
    id: int
    value: float
    reason: str
    author: str


class ForecastPoint(BaseModel):
    week: date
    label: str
    horizon: int
    naive: float | None
    baseline: float
    context_multiplier: float
    context: float
    final: float
    p10: float
    p90: float
    override: OverrideRef | None
    drivers: list[DriverOut]


class HistoryPoint(BaseModel):
    week: date
    label: str
    actual: float
    forecast: float | None
    baseline: float | None
    context_multiplier: float
    drivers: list[DriverOut]


class TradeOffRow(BaseModel):
    service_level: float
    safety_stock: int
    order_up_to: int
    recommended_order: int
    inventory_value: float


class StockPlanOut(BaseModel):
    service_level: float
    lead_time_weeks: int
    protection_weeks: int
    expected_demand: float
    demand_sd: float
    safety_stock: int
    order_up_to: int
    on_hand: float
    on_order: float
    recommended_order: int
    stockout_risk: float
    days_of_cover: float | None
    unit_cost: float
    trade_off: list[TradeOffRow]


class LayerMetrics(BaseModel):
    layer: str
    wape: float | None
    mape: float | None
    rmse: float | None
    mae: float | None
    bias: float | None
    n: int
    fva: float | None


class ForecastOut(BaseModel):
    product: ProductOut
    region: str
    last_actual_week: date
    sigma: float
    history: list[HistoryPoint]
    forecast: list[ForecastPoint]
    stock: StockPlanOut
    accuracy: list[LayerMetrics]


class SeriesSummary(BaseModel):
    product_code: str
    product_name: str
    region: str
    next_4w_demand: float
    last_4w_actual: float
    change_pct: float | None
    context_uplift_pct: float
    wape: float | None
    fva_vs_naive: float | None
    anomalies: int
    stockout_risk: float
    sparkline: list[float]


class UpcomingEvent(BaseModel):
    id: int
    name: str
    event_type: str
    start_date: date
    end_date: date
    multiplier: float
    scope: str


class OverviewOut(BaseModel):
    last_actual_week: date
    total_next_4w: float
    total_last_4w: float
    portfolio_accuracy: list[LayerMetrics]
    open_anomalies: int
    upcoming_events: list[UpcomingEvent]
    series: list[SeriesSummary]


class OverrideScorecard(BaseModel):
    overrides: int
    improved: int
    worsened: int
    wape_system: float | None
    wape_override: float | None


class SeriesFva(BaseModel):
    product_code: str
    region: str
    layers: list[LayerMetrics]


class FvaOut(BaseModel):
    portfolio: list[LayerMetrics]
    overrides: OverrideScorecard
    series: list[SeriesFva]
    backtest_weeks: int
    horizon_weeks: int


class AnomalyOut(BaseModel):
    product_code: str
    region: str
    week: date
    label: str
    actual: float
    expected: float
    deviation_pct: float
    z_score: float
    direction: str
    kind: str
    events: list[str]


# ---- scenarios ---------------------------------------------------------------
class ScenarioEvent(BaseModel):
    name: str = "What-if event"
    event_type: EventType = "promotion"
    start_date: date
    end_date: date
    multiplier: float = Field(gt=0.1, le=5.0)


class ScenarioIn(BaseModel):
    product_code: str
    region: str
    horizon: int = Field(default=12, ge=1, le=52)
    service_level: float = Field(default=0.95, ge=0.5, lt=1.0)
    on_hand: float | None = Field(default=None, ge=0)
    events: list[ScenarioEvent] = Field(default_factory=list, max_length=10)


class ScenarioOut(BaseModel):
    weeks: list[str]
    current: list[ForecastPoint]
    scenario: list[ForecastPoint]
    current_stock: StockPlanOut
    scenario_stock: StockPlanOut
    total_current: float
    total_scenario: float
    change_pct: float | None


# ---- chat --------------------------------------------------------------------
class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)


class ChatOut(BaseModel):
    answer: str
    model: str
    grounded_on: list[str]
    facts: str
