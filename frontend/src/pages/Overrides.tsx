import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Database, FileUp, RotateCcw, Trash2 } from "lucide-react";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { ImportReport } from "../api/types";
import { Callout, Card, EmptyState, ErrorBox, Loading, PageHeader, Pill, Segmented } from "../components/ui";
import { dateTime, longDate, signedPct, units } from "../lib/format";

type Tab = "overrides" | "audit" | "data";

function OverridesTab() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["overrides"], queryFn: api.overrides });
  const meta = useQuery({ queryKey: ["meta"], queryFn: api.meta });
  const del = useMutation({ mutationFn: (id: number) => api.deleteOverride(id), onSuccess: () => qc.invalidateQueries() });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} />;
  const today = meta.data?.last_actual_week ?? "";

  return (
    <Card padded={false}>
      {q.data!.length === 0 ? (
        <EmptyState title="No overrides yet">
          Use the pencil on the <Link className="text-indigo-600 underline" to="/forecast">Forecast</Link> page to set one.
        </EmptyState>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="border-b border-slate-100 dark:border-slate-800">
              <tr>
                <th className="th">Week of</th>
                <th className="th">Series</th>
                <th className="th text-right">System</th>
                <th className="th text-right">Planner</th>
                <th className="th">Reason</th>
                <th className="th">By</th>
                <th className="th" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {q.data!.map((o) => {
                const diff = o.system_value ? (o.value / o.system_value - 1) * 100 : null;
                return (
                  <tr key={o.id}>
                    <td className="td whitespace-nowrap">
                      {longDate(o.week_start)} {o.week_start > today ? <Pill tone="warn">upcoming</Pill> : <Pill>past</Pill>}
                    </td>
                    <td className="td whitespace-nowrap font-medium">
                      <Link className="hover:underline" to={`/forecast?product=${o.product_code}&region=${o.region}`}>
                        {o.product_code} · {o.region}
                      </Link>
                    </td>
                    <td className="td text-right tabular-nums text-slate-500">{units(o.system_value)}</td>
                    <td className="td text-right font-semibold tabular-nums">
                      {units(o.value)}
                      {diff != null && <div className="text-xs font-normal text-slate-500">{signedPct(diff, 0)}</div>}
                    </td>
                    <td className="td max-w-xs text-slate-600 dark:text-slate-300">{o.reason}</td>
                    <td className="td whitespace-nowrap text-slate-500">{o.author}</td>
                    <td className="td text-right">
                      <button
                        className="rounded-md p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950"
                        onClick={() => confirm("Remove this override?") && del.mutate(o.id)}
                        aria-label="Remove override"
                      >
                        <Trash2 className="size-4" />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

const ACTION_TONE: Record<string, "good" | "bad" | "warn" | "neutral"> = {
  create: "good",
  import: "good",
  update: "warn",
  delete: "bad",
  reset: "bad",
};

function AuditTab() {
  const q = useQuery({ queryKey: ["audit"], queryFn: () => api.audit(200) });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} />;
  return (
    <Card padded={false}>
      <ol className="divide-y divide-slate-100 dark:divide-slate-800">
        {q.data!.map((a) => (
          <li key={a.id} className="flex gap-4 px-5 py-3">
            <div className="w-28 shrink-0 text-xs text-slate-500 tabular-nums">{dateTime(a.timestamp)}</div>
            <div className="min-w-0 flex-1">
              <div className="text-sm">{a.summary}</div>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                <Pill tone={ACTION_TONE[a.action] ?? "neutral"}>{a.action}</Pill>
                <span>{a.entity_type}</span>
                <span>·</span>
                <span className="font-medium text-slate-700 dark:text-slate-300">{a.actor}</span>
              </div>
            </div>
          </li>
        ))}
      </ol>
    </Card>
  );
}

function DataTab() {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [report, setReport] = useState<ImportReport | null>(null);
  const importSales = useMutation({
    mutationFn: (f: File) => api.importSales(f),
    onSuccess: (r) => {
      setReport(r);
      qc.invalidateQueries();
    },
  });
  const reset = useMutation({ mutationFn: api.resetDemo, onSuccess: () => qc.invalidateQueries() });

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card title="Load your own sales history" subtitle="Replace the demo data with real weekly sales">
        <p className="text-sm text-slate-600 dark:text-slate-300">
          Upload a CSV or Excel file with columns <code>product_code, region, week_start, units</code> (optional:{" "}
          <code>product_name, category</code>). Dates are snapped to the Monday of their week; existing weeks are updated.
          At least ~18 months of history gives good seasonality.
        </p>
        <input
          ref={fileRef}
          type="file"
          accept=".csv,.xlsx,.xls"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) importSales.mutate(f);
            e.target.value = "";
          }}
        />
        <button className="btn-primary mt-4" onClick={() => fileRef.current?.click()} disabled={importSales.isPending}>
          <FileUp className="size-4" /> {importSales.isPending ? "Uploading…" : "Upload sales file"}
        </button>
        {report && (
          <p className="mt-3 text-sm text-emerald-700 dark:text-emerald-300">
            {report.created} rows loaded{report.errors.length ? `, ${report.errors.length} rows skipped` : ""}.
          </p>
        )}
        {importSales.error && (
          <div className="mt-3">
            <ErrorBox error={importSales.error} />
          </div>
        )}
      </Card>
      <Card title="Reset demo data" subtitle="Start over with the generated dataset">
        <p className="text-sm text-slate-600 dark:text-slate-300">
          Deletes all sales, events, overrides and the audit log, then regenerates the demo dataset (3 products × 4 regions, the
          original Excel events and the Indian festival calendar).
        </p>
        <button
          className="btn-ghost mt-4 text-red-600"
          disabled={reset.isPending}
          onClick={() => confirm("Delete everything and regenerate the demo data?") && reset.mutate()}
        >
          <RotateCcw className={`size-4 ${reset.isPending ? "animate-spin" : ""}`} /> Reset demo data
        </button>
        {reset.isSuccess && <p className="mt-3 text-sm text-emerald-700">Demo data regenerated.</p>}
      </Card>
    </div>
  );
}

export default function Overrides() {
  const [tab, setTab] = useState<Tab>("overrides");
  return (
    <>
      <PageHeader
        title="Overrides & audit"
        subtitle="Every manual change is recorded with who made it and why. Overrides are scored on the Accuracy page."
        actions={
          <Segmented<Tab>
            value={tab}
            onChange={setTab}
            options={[
              { value: "overrides", label: "Overrides" },
              { value: "audit", label: "Audit log" },
              { value: "data", label: "Data" },
            ]}
          />
        }
      />
      {tab === "overrides" && (
        <div className="space-y-4">
          <Callout>
            Overrides should be the exception. Check the <Link to="/accuracy" className="font-medium underline">Accuracy</Link> page
            to see whether past overrides beat the system.
          </Callout>
          <OverridesTab />
        </div>
      )}
      {tab === "audit" && <AuditTab />}
      {tab === "data" && (
        <>
          <div className="mb-4 flex items-center gap-2 text-sm text-slate-500">
            <Database className="size-4" /> Data management
          </div>
          <DataTab />
        </>
      )}
    </>
  );
}
