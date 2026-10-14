import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileSpreadsheet, Pencil, Plus, RefreshCw, Search, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { ContextEvent, EventInput, ImportReport } from "../api/types";
import { Card, EmptyState, ErrorBox, Loading, Modal, PageHeader, Pill, TypeBadge } from "../components/ui";
import { addDays, longDate, shortDate, signedPct } from "../lib/format";

const EMPTY: EventInput = {
  name: "",
  event_type: "promotion",
  description: "",
  product_code: null,
  category: null,
  region: null,
  start_date: "",
  end_date: "",
  multiplier: 1.1,
  recurring_yearly: false,
};

function EventForm({ initial, editingId, onClose }: { initial: EventInput | null; editingId: number | null; onClose: () => void }) {
  const qc = useQueryClient();
  const meta = useQuery({ queryKey: ["meta"], queryFn: api.meta });
  const [form, setForm] = useState<EventInput>(EMPTY);
  const [effect, setEffect] = useState("10");
  useEffect(() => {
    if (initial) {
      setForm(initial);
      setEffect(String(Math.round((initial.multiplier - 1) * 1000) / 10));
    }
  }, [initial]);
  const set = <K extends keyof EventInput>(k: K, v: EventInput[K]) => setForm((f) => ({ ...f, [k]: v }));

  const save = useMutation({
    mutationFn: () => {
      const body = { ...form, multiplier: 1 + Number(effect) / 100 };
      return editingId ? api.updateEvent(editingId, body) : api.createEvent(body);
    },
    onSuccess: () => {
      qc.invalidateQueries();
      onClose();
    },
  });
  const valid = form.name.trim() && form.start_date && form.end_date && effect !== "" && Number(effect) > -90;

  return (
    <Modal
      open={initial != null}
      title={editingId ? "Edit event" : "Add business event"}
      onClose={onClose}
      footer={
        <>
          <button className="btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button className="btn-primary" disabled={!valid || save.isPending} onClick={() => save.mutate()}>
            {editingId ? "Save changes" : "Add event"}
          </button>
        </>
      }
    >
      <div className="space-y-4">
        <div>
          <label className="label" htmlFor="ev-name">
            Name
          </label>
          <input id="ev-name" className="input" value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="e.g. Diwali flash sale" />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Type</label>
            <select className="input" value={form.event_type} onChange={(e) => set("event_type", e.target.value)}>
              {(meta.data?.event_types ?? []).map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Effect on demand (%)</label>
            <input type="number" step="1" className="input" value={effect} onChange={(e) => setEffect(e.target.value)} />
          </div>
          <div>
            <label className="label">Product</label>
            <select className="input" value={form.product_code ?? ""} onChange={(e) => set("product_code", e.target.value || null)}>
              <option value="">All products</option>
              {meta.data?.products.map((p) => (
                <option key={p.code} value={p.code}>
                  {p.code} · {p.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Region</label>
            <select className="input" value={form.region ?? ""} onChange={(e) => set("region", e.target.value || null)}>
              <option value="">All regions</option>
              {meta.data?.regions.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Starts</label>
            <input type="date" className="input" value={form.start_date} onChange={(e) => set("start_date", e.target.value)} />
          </div>
          <div>
            <label className="label">Ends</label>
            <input type="date" className="input" value={form.end_date} onChange={(e) => set("end_date", e.target.value)} />
          </div>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" className="size-4 accent-indigo-600" checked={form.recurring_yearly} onChange={(e) => set("recurring_yearly", e.target.checked)} />
          Repeats every year on the same dates
        </label>
        <div>
          <label className="label">Notes</label>
          <textarea rows={2} className="input" value={form.description} onChange={(e) => set("description", e.target.value)} />
        </div>
        {save.error && <ErrorBox error={save.error} />}
      </div>
    </Modal>
  );
}

export default function Events() {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const meta = useQuery({ queryKey: ["meta"], queryFn: api.meta });
  const q = useQuery({ queryKey: ["events"], queryFn: () => api.events() });
  const [type, setType] = useState("all");
  const [search, setSearch] = useState("");
  const [showPast, setShowPast] = useState(false);
  const [editing, setEditing] = useState<{ initial: EventInput; id: number | null } | null>(null);
  const [report, setReport] = useState<ImportReport | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Pre-filled "record what happened" form when arriving from an alert.
  useEffect(() => {
    if (params.get("new")) {
      const start = params.get("start") ?? "";
      setEditing({
        id: null,
        initial: {
          ...EMPTY,
          name: "",
          event_type: params.get("type") ?? "other",
          product_code: params.get("product"),
          region: params.get("region"),
          start_date: start,
          end_date: start ? addDays(start, 6) : "",
          multiplier: params.get("type") === "stockout" ? 0.7 : 1.3,
        },
      });
      setParams({}, { replace: true });
    }
  }, [params, setParams]);

  const importMut = useMutation({
    mutationFn: (f: File) => api.importEvents(f),
    onSuccess: (r) => {
      setReport(r);
      qc.invalidateQueries();
    },
  });
  const syncMut = useMutation({
    mutationFn: api.syncFestivals,
    onSuccess: (r) => {
      setReport(r);
      qc.invalidateQueries();
    },
  });
  const delMut = useMutation({ mutationFn: (id: number) => api.deleteEvent(id), onSuccess: () => qc.invalidateQueries() });

  const today = meta.data?.last_actual_week ?? "";
  const rows = useMemo(() => {
    const s = search.toLowerCase();
    return (q.data ?? [])
      .filter((e) => type === "all" || e.event_type === type)
      .filter((e) => showPast || e.recurring_yearly || e.end_date >= today)
      .filter((e) => !s || `${e.name} ${e.description} ${e.product_code ?? ""} ${e.region ?? ""}`.toLowerCase().includes(s))
      .sort((a, b) => a.start_date.localeCompare(b.start_date));
  }, [q.data, type, search, showPast, today]);

  const scope = (e: ContextEvent) =>
    `${e.product_code ?? (e.category ? e.category.replace("_", " ") : "All products")} · ${e.region ?? "All regions"}`;

  return (
    <>
      <PageHeader
        title="Business events"
        subtitle="Promotions, festivals, stockouts and distributor activity that move demand. Every forecast uses these automatically."
        actions={
          <>
            <input
              ref={fileRef}
              type="file"
              accept=".xlsx,.xls,.csv"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) importMut.mutate(f);
                e.target.value = "";
              }}
            />
            <button className="btn-ghost" onClick={() => fileRef.current?.click()} disabled={importMut.isPending}>
              <FileSpreadsheet className="size-4" /> Import Excel
            </button>
            <button className="btn-ghost" onClick={() => syncMut.mutate()} disabled={syncMut.isPending} title="Rebuild festival events from the festival calendar">
              <RefreshCw className={`size-4 ${syncMut.isPending ? "animate-spin" : ""}`} /> Refresh festivals
            </button>
            <button className="btn-primary" onClick={() => setEditing({ initial: EMPTY, id: null })}>
              <Plus className="size-4" /> Add event
            </button>
          </>
        }
      />

      {(report || importMut.error || syncMut.error) && (
        <div className="mb-4">
          {report && (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-200">
              <div className="flex justify-between">
                <strong>{report.created} events added.</strong>
                <button className="text-xs underline" onClick={() => setReport(null)}>
                  Dismiss
                </button>
              </div>
              {report.errors.length > 0 && (
                <ul className="mt-2 list-disc space-y-0.5 pl-5 text-xs">
                  {report.errors.slice(0, 10).map((e) => (
                    <li key={e}>{e}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {(importMut.error || syncMut.error) && <ErrorBox error={importMut.error ?? syncMut.error} />}
        </div>
      )}

      <Card padded={false}>
        <div className="flex flex-col gap-3 border-b border-slate-100 p-4 sm:flex-row sm:items-center dark:border-slate-800">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
            <input className="input pl-9!" placeholder="Search events…" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <select className="input sm:w-44!" value={type} onChange={(e) => setType(e.target.value)} aria-label="Filter by type">
            <option value="all">All types</option>
            {meta.data?.event_types.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <label className="flex items-center gap-2 whitespace-nowrap text-sm">
            <input type="checkbox" className="size-4 accent-indigo-600" checked={showPast} onChange={(e) => setShowPast(e.target.checked)} />
            Show past events
          </label>
        </div>

        {q.isLoading && <Loading />}
        {q.error && (
          <div className="p-4">
            <ErrorBox error={q.error} />
          </div>
        )}
        {q.data && rows.length === 0 && <EmptyState title="No events match">Try another filter or add one.</EmptyState>}
        {rows.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-b border-slate-100 dark:border-slate-800">
                <tr>
                  <th className="th">Event</th>
                  <th className="th">Type</th>
                  <th className="th">Applies to</th>
                  <th className="th">When</th>
                  <th className="th text-right">Effect</th>
                  <th className="th" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {rows.map((e) => (
                  <tr key={e.id} className="align-top">
                    <td className="td max-w-sm">
                      <div className="font-medium">{e.name}</div>
                      {e.description && <div className="mt-0.5 line-clamp-2 text-xs text-slate-500">{e.description}</div>}
                    </td>
                    <td className="td">
                      <TypeBadge type={e.event_type} />
                    </td>
                    <td className="td whitespace-nowrap text-slate-600 capitalize dark:text-slate-300">{scope(e)}</td>
                    <td className="td whitespace-nowrap">
                      {e.recurring_yearly ? (
                        <>
                          {shortDate(e.start_date)} – {shortDate(e.end_date)} <Pill>yearly</Pill>
                        </>
                      ) : (
                        <>
                          {shortDate(e.start_date)} – {longDate(e.end_date)}
                        </>
                      )}
                    </td>
                    <td className={`td text-right font-medium tabular-nums ${e.multiplier >= 1 ? "text-emerald-600" : "text-red-600"}`}>
                      {signedPct((e.multiplier - 1) * 100, 0)}
                    </td>
                    <td className="td whitespace-nowrap text-right">
                      <button
                        className="rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800"
                        onClick={() => setEditing({ id: e.id, initial: { ...e } })}
                        aria-label={`Edit ${e.name}`}
                      >
                        <Pencil className="size-4" />
                      </button>
                      <button
                        className="rounded-md p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950"
                        onClick={() => confirm(`Delete "${e.name}"?`) && delMut.mutate(e.id)}
                        aria-label={`Delete ${e.name}`}
                      >
                        <Trash2 className="size-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="border-t border-slate-100 px-5 py-3 text-xs text-slate-500 dark:border-slate-800">
          Showing {rows.length} of {q.data?.length ?? 0} events. Excel template columns match <code>backend/data/dummy_data.xlsx</code>.
        </div>
      </Card>

      <EventForm initial={editing?.initial ?? null} editingId={editing?.id ?? null} onClose={() => setEditing(null)} />
    </>
  );
}
