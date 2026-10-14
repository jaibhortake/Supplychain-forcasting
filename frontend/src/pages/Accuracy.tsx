import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { LayerMetrics } from "../api/types";
import { Callout, Card, ErrorBox, Loading, PageHeader, StatTile } from "../components/ui";
import { LAYER_LABELS, pct, signedPct } from "../lib/format";
import { LayerBars } from "./Dashboard";

function FvaCell({ m }: { m: LayerMetrics | undefined }) {
  if (!m) return <td className="td">–</td>;
  const tone = m.fva == null ? "" : m.fva >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400";
  return (
    <td className="td text-right tabular-nums">
      <div className="font-medium">{pct(m.wape)}</div>
      {m.fva != null && <div className={`text-xs ${tone}`}>{m.fva >= 0 ? "▼" : "▲"} {Math.abs(m.fva).toFixed(1)}</div>}
    </td>
  );
}

export default function Accuracy() {
  const q = useQuery({ queryKey: ["fva"], queryFn: api.fva });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} onRetry={() => q.refetch()} />;
  const d = q.data!;
  const by = (layer: string) => d.portfolio.find((l) => l.layer === layer);
  const naive = by("naive")?.wape;
  const context = by("context")?.wape;
  const final = by("final");
  const o = d.overrides;

  return (
    <>
      <PageHeader
        title="Accuracy & Forecast Value Added"
        subtitle={`Every forecast layer is replayed over the last ${d.backtest_weeks} weeks (forecasting 1–${d.horizon_weeks} weeks ahead, using only data available at the time) and compared with what actually sold.`}
      />

      <Callout>
        <strong>How to read this:</strong> WAPE is the forecast error as a % of units sold, so lower is better. FVA (Forecast Value
        Added) is how many points of error each layer removes compared with the layer before it. A red ▲ means that step made
        the forecast <em>worse</em>, so that effort is not adding value.
      </Callout>

      <div className="mt-6 grid gap-4 sm:grid-cols-3">
        <StatTile
          label="Error: same week last year"
          value={pct(naive)}
          hint="The simple benchmark to beat"
        />
        <StatTile
          label="Error: with business context"
          value={pct(context)}
          hint={naive != null && context != null ? `${(naive - context).toFixed(1)} pts better than the benchmark` : undefined}
          tone="good"
        />
        <StatTile
          label="Planner overrides"
          value={`${o.improved} / ${o.overrides}`}
          hint={
            o.wape_system != null && o.wape_override != null
              ? `improved accuracy · error on those weeks ${pct(o.wape_system)} → ${pct(o.wape_override)}`
              : "No overrides in the backtest window yet"
          }
          tone={o.overrides && o.improved / o.overrides >= 0.5 ? "good" : "warn"}
        />
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <Card title="Portfolio: error by layer" subtitle="All products and regions combined">
          <LayerBars layers={d.portfolio} />
          <dl className="mt-5 grid grid-cols-2 gap-3 text-sm">
            <div className="rounded-lg bg-slate-50 p-3 dark:bg-slate-800/60">
              <dt className="text-xs text-slate-500">Bias of final forecast</dt>
              <dd className="font-semibold">{signedPct(final?.bias)}</dd>
              <dd className="text-xs text-slate-500">{(final?.bias ?? 0) >= 0 ? "over-forecasting" : "under-forecasting"}</dd>
            </div>
            <div className="rounded-lg bg-slate-50 p-3 dark:bg-slate-800/60">
              <dt className="text-xs text-slate-500">Forecasts scored</dt>
              <dd className="font-semibold">{final?.n ?? 0}</dd>
              <dd className="text-xs text-slate-500">series × weeks</dd>
            </div>
          </dl>
        </Card>

        <Card title="By product and region" subtitle="WAPE, with FVA vs. the previous layer underneath" className="xl:col-span-2" padded={false}>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-b border-slate-100 dark:border-slate-800">
                <tr>
                  <th className="th">Series</th>
                  {["naive", "baseline", "context", "final"].map((l) => (
                    <th key={l} className="th text-right">
                      {LAYER_LABELS[l]}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {d.series.map((s) => (
                  <tr key={s.product_code + s.region}>
                    <td className="td font-medium">
                      {s.product_code} · {s.region}
                    </td>
                    {["naive", "baseline", "context", "final"].map((l) => (
                      <FvaCell key={l} m={s.layers.find((x) => x.layer === l)} />
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </>
  );
}
