// Mirrors backend/app/schemas.py

export interface Product {
  code: string;
  name: string;
  category: string;
  unit_cost: number;
  lead_time_weeks: number;
}

export interface Meta {
  products: Product[];
  regions: string[];
  event_types: string[];
  last_actual_week: string | null;
  data_version: number;
}

export interface Driver {
  event_id: number | null;
  name: string;
  event_type: string;
  effect_pct: number;
  raw_effect_pct: number;
  damped: boolean;
}

export interface ForecastPoint {
  week: string;
  label: string;
  horizon: number;
  naive: number | null;
  baseline: number;
  context_multiplier: number;
  context: number;
  final: number;
  p10: number;
  p90: number;
  override: { id: number; value: number; reason: string; author: string } | null;
  drivers: Driver[];
}

export interface HistoryPoint {
  week: string;
  label: string;
  actual: number;
  forecast: number | null;
  baseline: number | null;
  context_multiplier: number;
  drivers: Driver[];
}

export interface TradeOffRow {
  service_level: number;
  safety_stock: number;
  order_up_to: number;
  recommended_order: number;
  inventory_value: number;
}

export interface StockPlan {
  service_level: number;
  lead_time_weeks: number;
  protection_weeks: number;
  expected_demand: number;
  demand_sd: number;
  safety_stock: number;
  order_up_to: number;
  on_hand: number;
  on_order: number;
  recommended_order: number;
  stockout_risk: number;
  days_of_cover: number | null;
  unit_cost: number;
  trade_off: TradeOffRow[];
}

export interface LayerMetrics {
  layer: "naive" | "baseline" | "context" | "final";
  wape: number | null;
  mape: number | null;
  rmse: number | null;
  mae: number | null;
  bias: number | null;
  n: number;
  fva: number | null;
}

export interface ForecastResponse {
  product: Product;
  region: string;
  last_actual_week: string;
  sigma: number;
  history: HistoryPoint[];
  forecast: ForecastPoint[];
  stock: StockPlan;
  accuracy: LayerMetrics[];
}

export interface SeriesSummary {
  product_code: string;
  product_name: string;
  region: string;
  next_4w_demand: number;
  last_4w_actual: number;
  change_pct: number | null;
  context_uplift_pct: number;
  wape: number | null;
  fva_vs_naive: number | null;
  anomalies: number;
  stockout_risk: number;
  sparkline: number[];
}

export interface UpcomingEvent {
  id: number;
  name: string;
  event_type: string;
  start_date: string;
  end_date: string;
  multiplier: number;
  scope: string;
}

export interface Overview {
  last_actual_week: string;
  total_next_4w: number;
  total_last_4w: number;
  portfolio_accuracy: LayerMetrics[];
  open_anomalies: number;
  upcoming_events: UpcomingEvent[];
  series: SeriesSummary[];
}

export interface FvaResponse {
  portfolio: LayerMetrics[];
  overrides: {
    overrides: number;
    improved: number;
    worsened: number;
    wape_system: number | null;
    wape_override: number | null;
  };
  series: { product_code: string; region: string; layers: LayerMetrics[] }[];
  backtest_weeks: number;
  horizon_weeks: number;
}

export interface Anomaly {
  product_code: string;
  region: string;
  week: string;
  label: string;
  actual: number;
  expected: number;
  deviation_pct: number;
  z_score: number;
  direction: "spike" | "drop";
  kind: "unexplained" | "mis-sized";
  events: string[];
}

export interface ContextEvent {
  id: number;
  name: string;
  event_type: string;
  description: string;
  product_code: string | null;
  category: string | null;
  region: string | null;
  start_date: string;
  end_date: string;
  multiplier: number;
  recurring_yearly: boolean;
  source: string;
  created_at: string;
  updated_at: string;
}

export type EventInput = Omit<ContextEvent, "id" | "source" | "created_at" | "updated_at">;

export interface Override {
  id: number;
  product_code: string;
  region: string;
  week_start: string;
  value: number;
  system_value: number | null;
  reason: string;
  author: string;
  created_at: string;
}

export interface AuditEntry {
  id: number;
  timestamp: string;
  actor: string;
  action: string;
  entity_type: string;
  entity_id: string;
  summary: string;
  details: string;
}

export interface ImportReport {
  created: number;
  errors: string[];
}

export interface ScenarioEvent {
  name: string;
  event_type: string;
  start_date: string;
  end_date: string;
  multiplier: number;
}

export interface ScenarioResponse {
  weeks: string[];
  current: ForecastPoint[];
  scenario: ForecastPoint[];
  current_stock: StockPlan;
  scenario_stock: StockPlan;
  total_current: number;
  total_scenario: number;
  change_pct: number | null;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatResponse {
  answer: string;
  model: string;
  grounded_on: string[];
  facts: string;
}

export interface Health {
  status: string;
  llm: { available: boolean; model: string; url: string };
}
