import { useQuery } from "@tanstack/react-query";
import { ArrowDownRight, ArrowUpRight, CalendarPlus } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { Callout, Card, EmptyState, ErrorBox, Loading, PageHeader, Pill, Segmented } from "../components/ui";
import { longDate, signedPct, units } from "../lib/format";

type Filter = "all" | "unexplained" | "mis-sized";

export default function Alerts() {
  const [filter, setFilter] = useState<Filter>("unexplained");
  const q = useQuery({ queryKey: ["anomalies", filter], queryFn: () => api.anomalies(filter === "all" ? undefined : filter) });

  return (
    <>
      <PageHeader
        title="Alerts"
        subtitle="Weeks in the last year where actual sales were far from the forecast: the things a planner should look into."
        actions={
          <Segmented<Filter>
            value={filter}
            onChange={setFilter}
            options={[
              { value: "unexplained", label: "Missing context" },
              { value: "mis-sized", label: "Mis-sized events" },
              { value: "all", label: "All" },
            ]}
          />
        }
      />
      <Callout>
        <strong>Missing context</strong>: nothing on the event calendar explains the jump, so something happened that the system
        didn't know about (a strike, a heatwave, a competitor's price cut). Add it as an event so future forecasts learn from it.{" "}
        <strong>Mis-sized</strong>: an event was known, but its effect was much bigger or smaller than assumed.
      </Callout>

      <div className="mt-6">
        {q.isLoading && <Loading />}
        {q.error && <ErrorBox error={q.error} onRetry={() => q.refetch()} />}
        {q.data && q.data.length === 0 && (
          <Card>
            <EmptyState title="No alerts">Sales have stayed within the expected range.</EmptyState>
          </Card>
        )}
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {q.data?.map((a) => {
            const up = a.direction === "spike";
            return (
              <Card key={a.product_code + a.region + a.week}>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-semibold">
                      {a.product_code} · {a.region}
                    </div>
                    <div className="text-sm text-slate-500">Week of {longDate(a.week)}</div>
                  </div>
                  <div className={`grid size-9 place-items-center rounded-full ${up ? "bg-emerald-50 text-emerald-600 dark:bg-emerald-950" : "bg-red-50 text-red-600 dark:bg-red-950"}`}>
                    {up ? <ArrowUpRight className="size-5" /> : <ArrowDownRight className="size-5" />}
                  </div>
                </div>
                <div className="mt-4 flex items-baseline gap-2">
                  <span className="text-2xl font-semibold tabular-nums">{units(a.actual)}</span>
                  <span className="text-sm text-slate-500">sold vs {units(a.expected)} expected</span>
                </div>
                <div className="mt-1 text-sm">
                  <span className={up ? "text-emerald-600" : "text-red-600"}>{signedPct(a.deviation_pct, 0)}</span>
                  <span className="text-slate-500"> · {Math.abs(a.z_score).toFixed(1)}× the usual error</span>
                </div>
                <div className="mt-4 flex flex-wrap items-center gap-2">
                  {a.kind === "unexplained" ? <Pill tone="warn">Missing context?</Pill> : <Pill>Event effect mis-sized</Pill>}
                  {a.events.map((e) => (
                    <Pill key={e}>{e}</Pill>
                  ))}
                </div>
                {a.kind === "unexplained" && (
                  <Link
                    to={`/events?new=1&product=${a.product_code}&region=${a.region}&start=${a.week}&type=${up ? "other" : "stockout"}`}
                    className="btn-ghost mt-4 w-full"
                  >
                    <CalendarPlus className="size-4" /> Record what happened
                  </Link>
                )}
              </Card>
            );
          })}
        </div>
      </div>
    </>
  );
}
