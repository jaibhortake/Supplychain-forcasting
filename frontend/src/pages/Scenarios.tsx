import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Plus, Trash2, Zap } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { ScenarioEvent } from "../api/types";
import { ForecastChart } from "../components/charts";
import { SeriesPicker, useSeries } from "../components/SeriesPicker";
import { Callout, Card, ErrorBox, Loading, PageHeader, StatTile } from "../components/ui";
import { addDays, inr, shortDate, signedPct, units } from "../lib/format";

interface Draft {
  id: number;
  name: string;
  event_type: string;
  start: string;
  weeks: number;
  effectPct: number;
}

let nextId = 1;

function toEvent(d: Draft): ScenarioEvent {
  return {
    name: d.name || "What-if event",
    event_type: d.event_type,
    start_date: d.start,
    end_date: addDays(d.start, d.weeks * 7 - 1),
    multiplier: 1 + d.effectPct / 100,
  };
}

const PRESETS = [
  { label: "20% off promo for 2 weeks", name: "Price promotion", event_type: "promotion", weeks: 2, effectPct: 20, offsetWeeks: 2 },
  { label: "Supply disruption", name: "Supplier delay", event_type: "stockout", weeks: 2, effectPct: -35, offsetWeeks: 1 },
  { label: "Distributor push", name: "Distributor incentive", event_type: "distributor", weeks: 4, effectPct: 12, offsetWeeks: 3 },
];

export default function Scenarios() {
  const series = useSeries();
  const { product, region, ready, meta } = series;
  const firstWeek = meta?.last_actual_week ? addDays(meta.last_actual_week, 7) : null;
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [debounced, setDebounced] = useState<ScenarioEvent[]>([]);

  useEffect(() => {
    if (firstWeek && drafts.length === 0) {
      const p = PRESETS[0];
      setDrafts([{ id: nextId++, name: p.name, event_type: p.event_type, start: addDays(firstWeek, p.offsetWeeks * 7), weeks: p.weeks, effectPct: p.effectPct }]);
    }
  }, [firstWeek]);

  const events = useMemo(() => drafts.map(toEvent), [drafts]);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(events), 300);
    return () => clearTimeout(t);
  }, [events]);

  const q = useQuery({
    queryKey: ["scenario", product, region, debounced],
    queryFn: () => api.simulate({ product_code: product, region, horizon: 12, service_level: 0.95, on_hand: null, events: debounced }),
    enabled: ready,
    placeholderData: keepPreviousData,
  });

  const update = (id: number, patch: Partial<Draft>) => setDrafts((ds) => ds.map((d) => (d.id === id ? { ...d, ...patch } : d)));
  const addPreset = (p: (typeof PRESETS)[number]) =>
    firstWeek &&
    setDrafts((ds) => [
      ...ds,
      { id: nextId++, name: p.name, event_type: p.event_type, start: addDays(firstWeek, p.offsetWeeks * 7), weeks: p.weeks, effectPct: p.effectPct },
    ]);

  const d = q.data;
  const orderDelta = d ? d.scenario_stock.recommended_order - d.current_stock.recommended_order : 0;
  const unitCost = d?.current_stock.unit_cost ?? 0;

  return (
    <>
      <PageHeader
        title="What-if simulator"
        subtitle="Try a promotion, supply problem or distributor push before committing to it, and see the effect on demand and stock. Nothing is saved."
        actions={<SeriesPicker series={series} />}
      />

      <div className="grid gap-6 xl:grid-cols-5">
        <Card title="Your scenario" subtitle="Changes update the results instantly" className="h-fit xl:col-span-2">
          <div className="space-y-4">
            {drafts.length === 0 && <p className="text-sm text-slate-500">No hypothetical events. Add one below.</p>}
            {drafts.map((dr) => (
              <div key={dr.id} className="space-y-3 rounded-xl border border-slate-200 p-4 dark:border-slate-700">
                <div className="flex gap-2">
                  <input className="input" value={dr.name} onChange={(e) => update(dr.id, { name: e.target.value })} aria-label="Event name" />
                  <button className="btn-danger px-2!" onClick={() => setDrafts((ds) => ds.filter((x) => x.id !== dr.id))} aria-label="Remove event">
                    <Trash2 className="size-4" />
                  </button>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <div>
                    <label className="label">Type</label>
                    <select className="input" value={dr.event_type} onChange={(e) => update(dr.id, { event_type: e.target.value })}>
                      {["promotion", "stockout", "distributor", "other"].map((t) => (
                        <option key={t} value={t}>
                          {t}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="label">Starts</label>
                    <input type="date" className="input" value={dr.start} min={firstWeek ?? undefined} onChange={(e) => update(dr.id, { start: e.target.value })} />
                  </div>
                  <div>
                    <label className="label">Weeks</label>
                    <input type="number" min={1} max={12} className="input" value={dr.weeks} onChange={(e) => update(dr.id, { weeks: Math.max(1, Math.min(12, Number(e.target.value) || 1)) })} />
                  </div>
                </div>
                <div>
                  <div className="flex justify-between">
                    <label className="label">Expected effect on demand</label>
                    <span className={`text-sm font-semibold tabular-nums ${dr.effectPct >= 0 ? "text-emerald-600" : "text-red-600"}`}>
                      {signedPct(dr.effectPct, 0)}
                    </span>
                  </div>
                  <input
                    type="range"
                    min={-60}
                    max={80}
                    step={1}
                    value={dr.effectPct}
                    onChange={(e) => update(dr.id, { effectPct: Number(e.target.value) })}
                    className="w-full accent-indigo-600"
                    aria-label="Effect on demand"
                  />
                </div>
              </div>
            ))}
            <div>
              <div className="label">Quick add</div>
              <div className="flex flex-wrap gap-2">
                {PRESETS.map((p) => (
                  <button key={p.label} className="btn-ghost py-1.5! text-xs" onClick={() => addPreset(p)} disabled={drafts.length >= 10}>
                    <Plus className="size-3.5" /> {p.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </Card>

        <div className="space-y-6 xl:col-span-3">
          {q.error && <ErrorBox error={q.error} />}
          {!d && !q.error && <Loading />}
          {d && (
            <>
              <div className="grid gap-4 sm:grid-cols-3">
                <StatTile
                  label="Demand · next 12 weeks"
                  value={units(d.total_scenario)}
                  hint={`${signedPct(d.change_pct)} vs current plan (${units(d.total_current)})`}
                  tone={(d.change_pct ?? 0) >= 0 ? "good" : "bad"}
                  icon={<Zap className="size-4" />}
                />
                <StatTile
                  label="Order now"
                  value={units(d.scenario_stock.recommended_order)}
                  hint={`${orderDelta >= 0 ? "+" : ""}${units(orderDelta)} units vs current plan`}
                  tone={orderDelta > 0 ? "warn" : "neutral"}
                />
                <StatTile
                  label="Extra stock investment"
                  value={inr(orderDelta * unitCost)}
                  hint={`Safety stock ${units(d.current_stock.safety_stock)} → ${units(d.scenario_stock.safety_stock)}`}
                />
              </div>
              <Card title="Current plan vs what-if" subtitle="Weekly units over the next 12 weeks">
                <ForecastChart history={[]} forecast={d.current} scenario={d.scenario} showBaseline={false} height={300} />
              </Card>
              <Callout>
                Weeks with a planner override stay locked at the planner's number. Remove the override on the Forecast page to
                see the what-if there. Scenario window: {d.weeks[0]} to {d.weeks[d.weeks.length - 1]}
                {debounced[0] && <> · first event starts {shortDate(debounced[0].start_date)}</>}.
              </Callout>
            </>
          )}
        </div>
      </div>
    </>
  );
}
