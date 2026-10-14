import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, ShieldCheck, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ForecastPoint, StockPlan } from "../api/types";
import { ForecastChart } from "../components/charts";
import { SeriesPicker, useSeries } from "../components/SeriesPicker";
import { Card, ErrorBox, Loading, Modal, PageHeader, Pill, Segmented } from "../components/ui";
import { inr, pct, ratioPct, shortDate, signedPct, units } from "../lib/format";

function useDebounced<T>(value: T, ms = 350): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function StockPanel({
  stock,
  serviceLevel,
  onServiceLevel,
  onHand,
  onOnHand,
}: {
  stock: StockPlan;
  serviceLevel: number;
  onServiceLevel?: (v: number) => void;
  onHand?: string;
  onOnHand?: (v: string) => void;
}) {
  const risk = stock.stockout_risk;
  return (
    <div className="space-y-5">
      <div className="rounded-xl bg-indigo-600 p-5 text-white">
        <div className="text-sm text-indigo-100">Recommended order now</div>
        <div className="mt-1 text-4xl font-semibold tabular-nums">{units(stock.recommended_order)}</div>
        <div className="mt-1 text-sm text-indigo-100">
          units · ≈ {inr(stock.recommended_order * stock.unit_cost)} at cost
        </div>
      </div>

      {onServiceLevel && (
        <div>
          <div className="flex items-center justify-between">
            <label className="label" htmlFor="sl">
              Service level (chance of not running out)
            </label>
            <span className="text-sm font-semibold tabular-nums">{pct(serviceLevel * 100, 1)}</span>
          </div>
          <input
            id="sl"
            type="range"
            min={0.8}
            max={0.995}
            step={0.005}
            value={serviceLevel}
            onChange={(e) => onServiceLevel(Number(e.target.value))}
            className="w-full accent-indigo-600"
          />
        </div>
      )}
      {onOnHand && (
        <div>
          <label className="label" htmlFor="onhand">
            Units on hand today
          </label>
          <input
            id="onhand"
            type="number"
            min={0}
            className="input"
            value={onHand}
            placeholder={`${Math.round(stock.on_hand)} (assumed: ~1 week of demand)`}
            onChange={(e) => onOnHand(e.target.value)}
          />
        </div>
      )}

      <dl className="grid grid-cols-2 gap-3 text-sm">
        {[
          ["Demand until next delivery", `${units(stock.expected_demand)} ± ${units(stock.demand_sd)}`],
          ["Safety stock", units(stock.safety_stock)],
          ["Target stock level", units(stock.order_up_to)],
          ["Days of cover now", stock.days_of_cover == null ? "–" : `${Math.round(stock.days_of_cover)} days`],
        ].map(([k, v]) => (
          <div key={k} className="rounded-lg bg-slate-50 p-3 dark:bg-slate-800/60">
            <dt className="text-xs text-slate-500 dark:text-slate-400">{k}</dt>
            <dd className="mt-0.5 font-semibold tabular-nums">{v}</dd>
          </div>
        ))}
      </dl>

      <div
        className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm ${
          risk > 0.5
            ? "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300"
            : risk > 0.1
              ? "bg-amber-50 text-amber-800 dark:bg-amber-950 dark:text-amber-300"
              : "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
        }`}
      >
        <ShieldCheck className="size-4" />
        {ratioPct(risk)} chance of a stock-out if you don't order
      </div>

      <p className="text-xs text-slate-500 dark:text-slate-400">
        Covers {stock.protection_weeks} weeks: {stock.lead_time_weeks}-week supplier lead time + 1 week until the next review.
      </p>

      <div>
        <div className="mb-2 text-xs font-medium text-slate-500">Cost of more safety</div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-slate-500">
              <th className="pb-1 text-left font-medium">Service</th>
              <th className="pb-1 text-right font-medium">Safety stock</th>
              <th className="pb-1 text-right font-medium">Stock value</th>
            </tr>
          </thead>
          <tbody>
            {stock.trade_off.map((r) => (
              <tr key={r.service_level} className="border-t border-slate-100 dark:border-slate-800">
                <td className="py-1.5">{pct(r.service_level * 100, 0)}</td>
                <td className="py-1.5 text-right tabular-nums">{units(r.safety_stock)}</td>
                <td className="py-1.5 text-right tabular-nums">{inr(r.inventory_value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function OverrideModal({
  point,
  product,
  region,
  onClose,
}: {
  point: ForecastPoint | null;
  product: string;
  region: string;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [value, setValue] = useState("");
  const [reason, setReason] = useState("");
  useEffect(() => {
    if (point) {
      setValue(String(Math.round(point.override?.value ?? point.context)));
      setReason(point.override?.reason ?? "");
    }
  }, [point]);
  const save = useMutation({
    mutationFn: () =>
      api.saveOverride({ product_code: product, region, week_start: point!.week, value: Number(value), reason: reason.trim() }),
    onSuccess: () => {
      qc.invalidateQueries();
      onClose();
    },
  });
  const remove = useMutation({
    mutationFn: () => api.deleteOverride(point!.override!.id),
    onSuccess: () => {
      qc.invalidateQueries();
      onClose();
    },
  });
  const valid = value !== "" && Number(value) >= 0 && reason.trim().length >= 3;

  return (
    <Modal
      open={point != null}
      title={point ? `Override week of ${shortDate(point.week)}` : ""}
      onClose={onClose}
      footer={
        <>
          {point?.override && (
            <button className="btn-danger mr-auto" onClick={() => remove.mutate()} disabled={remove.isPending}>
              <Trash2 className="size-4" /> Remove override
            </button>
          )}
          <button className="btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button className="btn-primary" disabled={!valid || save.isPending} onClick={() => save.mutate()}>
            Save override
          </button>
        </>
      }
    >
      {point && (
        <div className="space-y-4">
          <p className="text-sm text-slate-600 dark:text-slate-300">
            The system forecasts <strong>{units(point.context)}</strong> units (likely {units(point.p10)}–{units(point.p90)}).
            Overrides are logged and scored later, so you can see whether manual changes help.
          </p>
          <div>
            <label className="label" htmlFor="ov-value">
              Your forecast (units)
            </label>
            <input id="ov-value" type="number" min={0} className="input" value={value} onChange={(e) => setValue(e.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="ov-reason">
              Reason (required)
            </label>
            <textarea
              id="ov-reason"
              rows={3}
              className="input"
              placeholder="e.g. Key account confirmed a bulk order"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </div>
          {(save.error || remove.error) && <ErrorBox error={save.error ?? remove.error} />}
        </div>
      )}
    </Modal>
  );
}

export default function Forecast() {
  const series = useSeries();
  const { product, region, ready } = series;
  const [horizon, setHorizon] = useState<"8" | "12" | "26">("12");
  const [serviceLevel, setServiceLevel] = useState(0.95);
  const [onHand, setOnHand] = useState("");
  const [editing, setEditing] = useState<ForecastPoint | null>(null);
  const sl = useDebounced(serviceLevel);
  const oh = useDebounced(onHand);

  useEffect(() => setOnHand(""), [product, region]);

  const q = useQuery({
    queryKey: ["forecast", product, region, horizon, sl, oh],
    queryFn: () => api.forecast(product, region, { horizon: Number(horizon), serviceLevel: sl, onHand: oh === "" ? null : Number(oh) }),
    enabled: ready,
    placeholderData: keepPreviousData,
  });
  const d = q.data;

  return (
    <>
      <PageHeader
        title="Forecast & stock"
        subtitle="Demand forecast with business events built in, the likely range, and how much stock to hold."
        actions={<SeriesPicker series={series} />}
      />
      {q.error && <ErrorBox error={q.error} onRetry={() => q.refetch()} />}
      {!d && !q.error && <Loading />}
      {d && (
        <div className="grid gap-6 xl:grid-cols-3">
          <div className="space-y-6 xl:col-span-2">
            <Card
              title={`${d.product.name} · ${d.region}`}
              subtitle={`Weekly units. Shaded band = 80% likely range. Faded line = what the model forecast at the time.`}
              actions={
                <Segmented
                  value={horizon}
                  onChange={setHorizon}
                  options={[
                    { value: "8", label: "8 wks" },
                    { value: "12", label: "12 wks" },
                    { value: "26", label: "26 wks" },
                  ]}
                />
              }
            >
              <ForecastChart history={d.history.slice(-52)} forecast={d.forecast} />
            </Card>

            <Card title="Week by week" subtitle="What drives each week's number. Click the pencil to override." padded={false}>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="border-b border-slate-100 dark:border-slate-800">
                    <tr>
                      <th className="th">Week of</th>
                      <th className="th text-right">Baseline</th>
                      <th className="th">Events this week</th>
                      <th className="th text-right">Forecast</th>
                      <th className="th text-right">Likely range</th>
                      <th className="th" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                    {d.forecast.map((p) => (
                      <tr key={p.week} className="align-top">
                        <td className="td whitespace-nowrap font-medium">{shortDate(p.week)}</td>
                        <td className="td text-right tabular-nums text-slate-500">{units(p.baseline)}</td>
                        <td className="td">
                          <div className="flex flex-wrap gap-1">
                            {p.drivers.length === 0 && <span className="text-slate-400">—</span>}
                            {p.drivers.map((dr) => (
                              <Pill key={dr.name} tone={dr.effect_pct >= 0 ? "good" : "bad"}>
                                {dr.name} {signedPct(dr.effect_pct, 0)}
                                {dr.damped && <span title="Reduced: diminishing returns when many events stack">*</span>}
                              </Pill>
                            ))}
                          </div>
                        </td>
                        <td className="td text-right font-semibold tabular-nums">
                          {units(p.final)}
                          {p.override && (
                            <div className="text-xs font-normal text-amber-600" title={p.override.reason}>
                              override by {p.override.author}
                            </div>
                          )}
                        </td>
                        <td className="td whitespace-nowrap text-right tabular-nums text-slate-500">
                          {units(p.p10)}–{units(p.p90)}
                        </td>
                        <td className="td text-right">
                          <button
                            className="rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800"
                            onClick={() => setEditing(p)}
                            aria-label={`Override week of ${shortDate(p.week)}`}
                          >
                            <Pencil className="size-4" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="px-5 py-3 text-xs text-slate-500">* When 3+ events overlap, extra events count at half strength to avoid over-forecasting.</p>
            </Card>
          </div>

          <Card title="Stock recommendation" subtitle={`Lead time ${d.stock.lead_time_weeks} weeks`} className="h-fit xl:sticky xl:top-6">
            <StockPanel stock={d.stock} serviceLevel={serviceLevel} onServiceLevel={setServiceLevel} onHand={onHand} onOnHand={setOnHand} />
          </Card>
        </div>
      )}
      <OverrideModal point={editing} product={product} region={region} onClose={() => setEditing(null)} />
    </>
  );
}
