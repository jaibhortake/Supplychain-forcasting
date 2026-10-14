"""'Chat with your forecast': answers grounded in the system's own numbers.

Small local models hallucinate numbers and are unreliable at tool-calling, so instead of letting
the model fetch data, we detect which products/regions the question is about, compute the
relevant facts deterministically, and give the model only those facts with strict instructions.
The facts are returned to the UI so users can check the answer.
"""

from __future__ import annotations

import re
from datetime import timedelta

from app.core.calendar import week_label
from app.core.evaluation import fva_table, override_scorecard
from app.services import llm
from app.services.forecast_service import ForecastService, SeriesAnalysis, upcoming_events

MAX_SERIES = 4
FORECAST_WEEKS = 8

CATEGORY_SYNONYMS = {
    "air_conditioner": ("ac", "acs", "air conditioner", "air conditioners", "aircon", "cooling"),
    "television": ("tv", "tvs", "television", "televisions"),
    "refrigerator": ("fridge", "fridges", "refrigerator", "refrigerators", "ref"),
}

SYSTEM_PROMPT = """You are a demand-planning assistant for a consumer-durables distributor in India.
Answer ONLY from the FACTS below. Rules:
- Quote numbers exactly as given in FACTS; never invent numbers, events or dates.
- If the FACTS do not contain the answer, say so and suggest which product/region to ask about.
- Explain the "why" using the listed drivers (events, festivals, promotions, stockouts).
- "P10-P90" is the likely range; "WAPE" is forecast error (lower is better).
- Be concise: a short answer, then up to 5 bullet points.

FACTS
-----
{facts}"""


def _mentions(text: str, word: str) -> bool:
    return re.search(rf"(?<![A-Za-z0-9-]){re.escape(word.lower())}(?![A-Za-z0-9-])", text) is not None


def detect_scope(message: str, svc: ForecastService) -> tuple[list[str], list[str]]:
    text = message.lower()
    products = []
    for p in svc.products():
        if _mentions(text, p.code) or any(_mentions(text, s) for s in CATEGORY_SYNONYMS.get(p.category, ())):
            products.append(p.code)
    regions = [r for r in svc.regions() if _mentions(text, r)]
    return products, regions


def _series_facts(svc: ForecastService, a: SeriesAnalysis) -> str:
    d = a.data
    lines = [f"## {d.product.code} ({d.product.name}) - {d.region}"]
    last = ", ".join(f"{week_label(w)}: {int(v)}" for w, v in zip(d.weeks[-4:], d.sales[-4:], strict=True))
    lines.append(f"Last 4 weeks actual sales: {last}")
    pts = svc.forecast_points(a, FORECAST_WEEKS)
    lines.append("Forecast (week: final units [P10-P90], statistical baseline, drivers):")
    for p in pts:
        drivers = "; ".join(f"{x['name']} {x['effect_pct']:+.0f}%" for x in p["drivers"]) or "no events"
        ov = f" PLANNER OVERRIDE by {p['override']['author']}: {p['override']['reason']}" if p["override"] else ""
        lines.append(
            f"- {p['label']} ({p['week']:%d %b}): {p['final']:.0f} [{p['p10']:.0f}-{p['p90']:.0f}], "
            f"baseline {p['baseline']:.0f}, {drivers}{ov}"
        )
    stock = svc.stock_plan(a, pts, 0.95, on_hand=round(pts[0]["final"]), on_order=0)
    lines.append(
        f"Stock plan @95% service, lead time {stock['lead_time_weeks']}w: order-up-to {stock['order_up_to']} units, "
        f"safety stock {stock['safety_stock']}, recommended order {stock['recommended_order']} "
        f"(assuming {stock['on_hand']:.0f} on hand), stock-out risk without ordering {stock['stockout_risk']:.0%}."
    )
    acc = ", ".join(f"{m['layer']} {m['wape']:.1f}%" for m in a.fva if m["wape"] is not None)
    lines.append(f"Backtest accuracy (WAPE, last 52 weeks): {acc}")
    if a.anomalies:
        lines.append(
            "Recent anomalies: "
            + "; ".join(
                f"{week_label(x.week)} actual {x.actual:.0f} vs expected {x.expected:.0f} ({x.direction}, {x.kind})"
                for x in a.anomalies[-4:]
            )
        )
    return "\n".join(lines)


def _portfolio_facts(svc: ForecastService) -> str:
    lines = ["## Portfolio summary (next 4 weeks vs last 4 weeks)"]
    rows = []
    for p, r in svc.series_keys():
        a = svc.analyze(p, r)
        pts = svc.forecast_points(a, 4)
        nxt, last = sum(x["final"] for x in pts), float(a.data.sales[-4:].sum())
        change = (nxt / last - 1) * 100 if last else 0
        lines.append(f"- {p} {r}: next 4w {nxt:.0f} units ({change:+.0f}% vs last 4w), {len(a.anomalies)} anomalies")
        rows += a.backtest
    fva = ", ".join(f"{m['layer']} {m['wape']:.1f}%" for m in fva_table(rows) if m["wape"] is not None)
    sc = override_scorecard(rows)
    lines.append(f"Portfolio WAPE by layer: {fva}")
    lines.append(f"Planner overrides: {sc['improved']} of {sc['overrides']} improved accuracy.")
    return "\n".join(lines)


def build_facts(message: str, svc: ForecastService) -> tuple[str, list[str]]:
    products, regions = detect_scope(message, svc)
    keys = svc.series_keys()
    selected = (
        [(p, r) for p, r in keys if (not products or p in products) and (not regions or r in regions)]
        if (products or regions)
        else []
    )

    sections, grounded = [], []
    if keys:
        last_week = svc.analyze(*keys[0]).data.weeks[-1]
        sections.append(f"Sales data available up to week {week_label(last_week)} ({last_week:%d %b %Y}).")
    for p, r in selected[:MAX_SERIES]:
        sections.append(_series_facts(svc, svc.analyze(p, r)))
        grounded.append(f"{p} · {r}")
    if len(selected) > MAX_SERIES:
        sections.append(f"(Only the first {MAX_SERIES} of {len(selected)} matching series are shown.)")
    if not selected:
        sections.append(_portfolio_facts(svc))
        grounded.append("Portfolio summary")
    if keys:
        events = upcoming_events(svc.session, last_week + timedelta(days=7), weeks=12)
        if events:
            lines = [
                f"- {e['name']}: {e['start_date']:%d %b} - {e['end_date']:%d %b}, x{e['multiplier']:.2f}, {e['scope']}"
                for e in events
            ]
            sections.append("## Upcoming events (next 12 weeks)\n" + "\n".join(lines))
    return "\n\n".join(sections), grounded


def answer(message: str, history: list[dict], svc: ForecastService) -> dict:
    facts, grounded = build_facts(message, svc)
    messages = [{"role": "system", "content": SYSTEM_PROMPT.format(facts=facts)}]
    messages += history[-6:]
    messages.append({"role": "user", "content": message})
    reply = llm.chat(messages)
    return {"answer": reply, "model": svc.settings.ollama_model, "grounded_on": grounded, "facts": facts}
