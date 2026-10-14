import { useQuery } from "@tanstack/react-query";
import { ArrowRight, BellRing, CalendarDays, Package, Target } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { LayerMetrics } from "../api/types";
import { Sparkline } from "../components/charts";
import { Card, ErrorBox, Loading, PageHeader, Pill, StatTile, TypeBadge } from "../components/ui";
import { LAYER_LABELS, longDate, pct, shortDate, signedPct, units } from "../lib/format";

export function LayerBars({ layers }: { layers: LayerMetrics[] }) {
  const max = Math.max(...layers.map((l) => l.wape ?? 0), 1);
  return (
    <div className="space-y-3">
      {layers.map((l) => (
        <div key={l.layer}>
          <div className="mb-1 flex justify-between text-xs">
            <span className="text-slate-600 dark:text-slate-300">{LAYER_LABELS[l.layer]}</span>
            <span className="flex items-center gap-2 tabular-nums">
              {l.fva != null && (
                <span className={l.fva >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}>
                  {l.fva >= 0 ? "▼" : "▲"} {Math.abs(l.fva).toFixed(1)} pts
                </span>
              )}
              <span className="font-semibold">{pct(l.wape)}</span>
            </span>
          </div>
          <div className="h-2 rounded-full bg-slate-100 dark:bg-slate-800">
            <div
              className={`h-2 rounded-full ${l.layer === "naive" ? "bg-slate-400" : "bg-indigo-500"}`}
              style={{ width: `${((l.wape ?? 0) / max) * 100}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

export default function Dashboard() {
  const navigate = useNavigate();
  const q = useQuery({ queryKey: ["overview"], queryFn: api.overview });

  if (q.isLoading) return <Loading label="Crunching forecasts…" />;
  if (q.error) return <ErrorBox error={q.error} onRetry={() => q.refetch()} />;
  const d = q.data!;
  const naive = d.portfolio_accuracy.find((l) => l.layer === "naive");
  const final = d.portfolio_accuracy.find((l) => l.layer === "final");
  const change = d.total_last_4w ? (d.total_next_4w / d.total_last_4w - 1) * 100 : null;
  const improvement = naive?.wape != null && final?.wape != null ? naive.wape - final.wape : null;
  const unexplained = d.series.reduce((s, x) => s + x.anomalies, 0);

  return (
    <>
      <PageHeader
        title="Dashboard"
        subtitle={<>Sales data up to the week of {longDate(d.last_actual_week)}. Figures below cover the next 4 weeks across every product and region.</>}
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Expected demand · next 4 weeks"
          value={units(d.total_next_4w)}
          hint={`${signedPct(change)} vs last 4 weeks`}
          tone={change != null && change >= 0 ? "good" : "warn"}
          icon={<Package className="size-4" />}
        />
        <StatTile
          label="Forecast error (WAPE)"
          value={pct(final?.wape)}
          hint={improvement != null ? `${improvement.toFixed(1)} pts better than "same week last year"` : undefined}
          tone={improvement != null && improvement > 0 ? "good" : "bad"}
          icon={<Target className="size-4" />}
        />
        <StatTile
          label="Alerts to review"
          value={unexplained}
          hint="Weeks where sales broke from the forecast"
          tone={unexplained ? "warn" : "good"}
          icon={<BellRing className="size-4" />}
        />
        <StatTile
          label="Events in the next 12 weeks"
          value={d.upcoming_events.length}
          hint="Festivals, promotions, supply issues"
          icon={<CalendarDays className="size-4" />}
        />
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <Card title="Products & regions" subtitle="Click a row to open its forecast" className="xl:col-span-2" padded={false}>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-b border-slate-100 dark:border-slate-800">
                <tr>
                  <th className="th">Series</th>
                  <th className="th">Last 26 wks → next 4</th>
                  <th className="th text-right">Next 4 wks</th>
                  <th className="th text-right">vs last 4</th>
                  <th className="th text-right">Event effect</th>
                  <th className="th text-right">Error</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {d.series.map((s) => (
                  <tr
                    key={s.product_code + s.region}
                    className="cursor-pointer transition hover:bg-slate-50 dark:hover:bg-slate-800/50"
                    onClick={() => navigate(`/forecast?product=${s.product_code}&region=${s.region}`)}
                  >
                    <td className="td">
                      <div className="font-medium">
                        {s.product_code} · {s.region}
                      </div>
                      <div className="text-xs text-slate-500">{s.product_name}</div>
                    </td>
                    <td className="td">
                      <Sparkline values={s.sparkline} />
                    </td>
                    <td className="td text-right font-medium tabular-nums">{units(s.next_4w_demand)}</td>
                    <td className="td text-right tabular-nums">
                      <span className={s.change_pct != null && s.change_pct < 0 ? "text-red-600 dark:text-red-400" : "text-emerald-600 dark:text-emerald-400"}>
                        {signedPct(s.change_pct, 0)}
                      </span>
                    </td>
                    <td className="td text-right tabular-nums">
                      {Math.abs(s.context_uplift_pct) < 0.5 ? (
                        <span className="text-slate-400">—</span>
                      ) : (
                        <Pill tone={s.context_uplift_pct > 0 ? "good" : "bad"}>{signedPct(s.context_uplift_pct, 0)}</Pill>
                      )}
                    </td>
                    <td className="td text-right tabular-nums">
                      {pct(s.wape)}
                      {s.anomalies > 0 && (
                        <span className="ml-1.5 inline-block size-1.5 rounded-full bg-amber-500 align-middle" title={`${s.anomalies} alerts`} />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <div className="space-y-6">
          <Card
            title="Does the extra work pay off?"
            subtitle="Forecast error over the last 52 weeks, by layer (lower is better)"
            actions={
              <Link to="/accuracy" className="text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400">
                Details
              </Link>
            }
          >
            <LayerBars layers={d.portfolio_accuracy} />
          </Card>

          <Card
            title="Coming up"
            actions={
              <Link to="/events" className="text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400">
                All events
              </Link>
            }
            padded={false}
          >
            <ul className="divide-y divide-slate-100 dark:divide-slate-800">
              {d.upcoming_events.slice(0, 7).map((e) => (
                <li key={e.name + e.start_date} className="flex items-start justify-between gap-3 px-5 py-3">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">{e.name}</div>
                    <div className="mt-0.5 truncate text-xs text-slate-500">
                      {shortDate(e.start_date)} – {shortDate(e.end_date)} · {e.scope}
                    </div>
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1">
                    <TypeBadge type={e.event_type} />
                    <span className={`text-xs font-medium tabular-nums ${e.multiplier >= 1 ? "text-emerald-600" : "text-red-600"}`}>
                      {signedPct((e.multiplier - 1) * 100, 0)}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
            <Link
              to="/scenarios"
              className="flex items-center justify-center gap-1 border-t border-slate-100 py-3 text-sm font-medium text-indigo-600 hover:bg-slate-50 dark:border-slate-800 dark:text-indigo-400 dark:hover:bg-slate-800/50"
            >
              Plan a promotion in the what-if simulator <ArrowRight className="size-4" />
            </Link>
          </Card>
        </div>
      </div>
    </>
  );
}
