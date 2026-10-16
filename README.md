# Supply Chain Demand Forecasting

**A context-aware demand forecasting and stock planning app.** It predicts weekly sales per product and region, adjusts
the forecast for real business events (promotions, Indian festivals, stockouts, distributor activity), tells you how
much stock to hold, and checks whether each of those adjustments actually makes the forecast more accurate.

Built with **FastAPI** (backend) and **React + TypeScript** (frontend). It has an optional local AI assistant
powered by **Ollama**.

---

## Why this exists

Distributors decide every week how much stock to send to each region. Statistical forecasts only look at past sales,
so they miss what planners already know ("Diwali is in three weeks", "there's a supply delay"). Planners then patch the
numbers by hand in Excel, and nobody measures whether those patches help.

This project fixes that loop:

1. **Forecast** normal demand from sales history.
2. **Add business context** automatically, with the reason shown for every change.
3. **Turn it into a decision**: a likely range and a recommended stock level.
4. **Measure** whether each step (and each manual override) made the forecast better or worse.

## Features

| | Feature | What it gives you |
|---|---|---|
| 📈 | **Statistical baseline** | Holt-Winters style model with yearly seasonality. Past promotions are removed from history before fitting, so they don't distort "normal" demand. |
| 🎉 | **Business events** | Promotions, stockouts, distributor activity, weather and seasonal events. Imported from Excel or added in the UI, applied week by week. |
| 🪔 | **Indian festival calendar** | Diwali, Holi, Eid, Pongal, Onam, Durga Puja, Ganesh Chaturthi and more, with the right dates each year, region and product effects. |
| 🎯 | **Forecast Value Added (FVA)** | Replays the last 52 weeks to show the error of each layer: *same week last year → baseline → + events → + planner overrides*. |
| 📦 | **Stock recommendations** | P10–P90 range, safety stock and order quantity for a chosen service level, plus the cost of more safety. |
| 🔔 | **Alerts** | Flags weeks where sales broke from the forecast and no event explains it ("missing context?"). |
| 🧪 | **What-if simulator** | "What if we run a 20% promo in week 44?" Instant impact on demand and stock. Nothing is saved. |
| ✍️ | **Overrides + audit log** | Planners can override any week, but a reason is required. Every change records who, when and why. |
| 💬 | **Ask the forecast** | Plain-English questions answered by a local LLM, **grounded in the system's own numbers** (no made-up data). |

## How it works

```
 Sales history ──► Remove known event effects ──► Baseline model (trend + seasonality)
                                                         │
 Business events + festival calendar ───────────────────►× event multipliers (diminishing returns)
                                                         │
 Planner overrides (with reason) ───────────────────────►  final forecast
                                                         │
                         ┌───────────────────────────────┼──────────────────────────┐
                         ▼                               ▼                          ▼
                 P10–P90 range                Safety stock & order qty       Backtest → FVA & alerts
```

* An event affects a week in proportion to the days it covers. When 3+ uplifts overlap, the extra ones count at
  half strength, so stacked events can't inflate the forecast.
* Error ranges come from the model's own past mistakes (backtest residuals), so the range is wider where forecasts have
  been less reliable.
* Stock policy: *order-up-to level = expected demand over (lead time + 1 week) + z × std-dev*.

## Quick start

### Option A: Docker (one command)

```bash
docker compose up --build
```

Open **http://localhost:8080**. Demo data is generated on first start.

### Option B: Run locally

**Requirements:** Python 3.11+, Node.js 20+

```bash
# 1. Backend (API on http://localhost:8000, docs at /docs)
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows   (macOS/Linux: source .venv/bin/activate)
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

```bash
# 2. Frontend (in a second terminal, opens http://localhost:5173)
cd frontend
npm install
npm run dev
```

### Optional: the AI assistant

The "Ask the forecast" page needs [Ollama](https://ollama.com) running locally. Everything else works without it.

```bash
ollama pull llama3.2
ollama serve
```

## Using your own data

* **Sales history:** go to *Overrides & audit → Data* and upload a CSV/Excel file with columns
  `product_code, region, week_start, units`. Around 18+ months of weekly history gives good seasonality.
* **Business events:** go to *Business events → Import Excel*. The template matches
  [`backend/data/dummy_data.xlsx`](backend/data/dummy_data.xlsx), the original planner sheet.
* **Festival dates:** edit [`backend/data/festivals.json`](backend/data/festivals.json), then click *Refresh festivals*.

All settings (database, Ollama URL, backtest length, etc.) can be changed with environment variables. See
[`.env.example`](.env.example).

## Project structure

```
├── backend/                  FastAPI service
│   ├── app/
│   │   ├── api/              HTTP routes (forecast, events, overrides, FVA, chat…)
│   │   ├── core/             Pure forecasting logic: baseline, events, metrics, inventory, backtest
│   │   ├── services/         Database orchestration, Excel import, festivals, demo data, LLM
│   │   ├── models.py         Database tables (SQLAlchemy)
│   │   └── schemas.py        API request/response types (Pydantic)
│   ├── data/                 Original Excel sheet + festival calendar
│   └── tests/                Pytest suite
├── frontend/                 React + TypeScript + Vite + Tailwind
│   └── src/
│       ├── pages/            Dashboard, Forecast, What-if, Accuracy, Alerts, Events, Overrides, Assistant
│       ├── components/       Layout, charts, shared UI
│       └── api/              Typed API client
├── research/                 Original internship proof-of-concept (notebooks + write-up)
└── docker-compose.yml
```

## API at a glance

Interactive docs are at `http://localhost:8000/docs` once the backend is running.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/overview` | Portfolio summary for the dashboard |
| GET | `/api/forecast/{product}/{region}` | Forecast, range, drivers and stock plan |
| POST | `/api/scenarios/simulate` | What-if analysis with hypothetical events |
| GET | `/api/fva` | Forecast Value Added per layer and series |
| GET | `/api/anomalies` | Alerts: unexplained or mis-sized deviations |
| GET/POST/PUT/DELETE | `/api/events` | Manage business events (`/import` for Excel) |
| GET/POST/DELETE | `/api/overrides` | Planner overrides |
| GET | `/api/audit` | Audit log of every change |
| POST | `/api/sales/import` | Load your own sales history |
| POST | `/api/chat` | Ask a question (needs Ollama) |

## Key terms

* **WAPE:** forecast error as a % of units sold. Lower is better. Unlike MAPE, it doesn't blow up on low-volume weeks.
* **FVA (Forecast Value Added):** how much each step reduces the error versus the step before it. A negative FVA
  means that step makes the forecast worse.
* **P10–P90:** the range actual sales should fall inside about 80% of the time.
* **Service level:** the chance of not running out before the next delivery. Higher means more safety stock.

## Running tests

```bash
cd backend
pytest          # unit + API tests
ruff check .    # lint
```

## Background

This started as a proof of concept during my internship at **ElasticRun**: a notebook that adjusted a hand-entered
forecast with multipliers from an Excel sheet and explained the result with a CrewAI + Ollama agent pipeline. The
original work is kept in [`research/`](research/).

What changed compared with the PoC:

* The forecast is now generated from history. You no longer type in a base number.
* The Excel multipliers are actually used. In the PoC, the adjustment code read mock fields and ignored the sheet.
* Date logic works for any year (the PoC was hard-coded to 2025).
* Accuracy is measured with a proper rolling backtest on 600+ forecasts, not 2 hand-picked examples.
* The LLM explains the numbers; it doesn't calculate them. Its answers are grounded in computed facts.

## Limitations & next steps

* No login yet. The user name in the sidebar is used for the audit log. Next step: SSO or JWT auth with roles.
* SQLite by default. Set `DATABASE_URL` to PostgreSQL for multi-user production use, and add Alembic migrations.
* Possible additions: learning event effects from history automatically, live weather data for AC demand, and
  GitHub Actions CI.

## License

[MIT](LICENSE)
