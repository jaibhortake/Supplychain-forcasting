import type {
  Anomaly,
  AuditEntry,
  ChatMessage,
  ChatResponse,
  ContextEvent,
  EventInput,
  ForecastResponse,
  FvaResponse,
  Health,
  ImportReport,
  Meta,
  Overview,
  Override,
  ScenarioEvent,
  ScenarioResponse,
} from "./types";

const BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "") + "/api";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export function getUserName(): string {
  try {
    return localStorage.getItem("userName") || "planner";
  } catch {
    return "planner";
  }
}

export function setUserName(name: string) {
  try {
    localStorage.setItem("userName", name);
  } catch {
    /* storage unavailable: name only lasts for this session */
  }
}

function detailMessage(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => (d && typeof d === "object" && "msg" in d ? String(d.msg) : String(d))).join("; ");
  }
  return "Request failed";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("X-User", getUserName());
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const res = await fetch(BASE + path, { ...init, headers });
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      message = detailMessage((await res.json()).detail);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, message);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

function qs(params: Record<string, string | number | undefined | null>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}

export const api = {
  health: () => request<Health>("/health"),
  meta: () => request<Meta>("/meta"),
  overview: () => request<Overview>("/overview"),
  forecast: (product: string, region: string, opts: { horizon?: number; serviceLevel?: number; onHand?: number | null }) =>
    request<ForecastResponse>(
      `/forecast/${encodeURIComponent(product)}/${encodeURIComponent(region)}` +
        qs({ horizon: opts.horizon, service_level: opts.serviceLevel, on_hand: opts.onHand }),
    ),
  fva: () => request<FvaResponse>("/fva"),
  anomalies: (kind?: string) => request<Anomaly[]>("/anomalies" + qs({ kind })),
  simulate: (body: {
    product_code: string;
    region: string;
    horizon: number;
    service_level: number;
    on_hand: number | null;
    events: ScenarioEvent[];
  }) => request<ScenarioResponse>("/scenarios/simulate", { method: "POST", body: JSON.stringify(body) }),

  events: (params: { event_type?: string; source?: string } = {}) => request<ContextEvent[]>("/events" + qs(params)),
  createEvent: (body: EventInput) => request<ContextEvent>("/events", { method: "POST", body: JSON.stringify(body) }),
  updateEvent: (id: number, body: EventInput) =>
    request<ContextEvent>(`/events/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteEvent: (id: number) => request<void>(`/events/${id}`, { method: "DELETE" }),
  importEvents: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ImportReport>("/events/import", { method: "POST", body: form });
  },
  syncFestivals: () => request<ImportReport>("/festivals/sync", { method: "POST" }),

  overrides: () => request<Override[]>("/overrides"),
  saveOverride: (body: { product_code: string; region: string; week_start: string; value: number; reason: string }) =>
    request<Override>("/overrides", { method: "POST", body: JSON.stringify(body) }),
  deleteOverride: (id: number) => request<void>(`/overrides/${id}`, { method: "DELETE" }),
  audit: (limit = 200) => request<AuditEntry[]>("/audit" + qs({ limit })),

  importSales: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ImportReport>("/sales/import", { method: "POST", body: form });
  },
  resetDemo: () => request<{ status: string }>("/admin/reset-demo", { method: "POST" }),

  chat: (message: string, history: ChatMessage[]) =>
    request<ChatResponse>("/chat", { method: "POST", body: JSON.stringify({ message, history }) }),
};
