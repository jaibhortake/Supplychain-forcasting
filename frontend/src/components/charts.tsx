import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipProps,
} from "recharts";
import type { ForecastPoint, HistoryPoint } from "../api/types";
import { shortDate, units } from "../lib/format";

const C = {
  actual: "var(--chart-actual)",
  forecast: "var(--chart-forecast)",
  band: "var(--chart-band)",
  baseline: "var(--chart-baseline)",
  scenario: "var(--chart-scenario)",
  override: "var(--chart-override)",
  grid: "var(--chart-grid)",
};

interface Row {
  week: string;
  actual?: number;
  backtest?: number | null;
  final?: number;
  baseline?: number | null;
  band?: [number, number];
  scenario?: number;
  overridden?: boolean;
}

function ChartTooltip({ active, payload }: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload as Row;
  const items: [string, string, number | null | undefined][] = [
    ["Actual sales", C.actual, row.actual],
    ["Forecast", C.forecast, row.final],
    ["What-if", C.scenario, row.scenario],
    ["Forecast made at the time", C.forecast, row.backtest],
    ["Statistical baseline", C.baseline, row.baseline],
  ];
  return (
    <div className="card min-w-48 p-3 text-xs shadow-lg">
      <div className="mb-1.5 font-semibold">Week of {shortDate(row.week)}</div>
      {items
        .filter(([, , v]) => v != null)
        .map(([label, color, v]) => (
          <div key={label} className="flex items-center justify-between gap-4 py-0.5">
            <span className="flex items-center gap-1.5 text-slate-500 dark:text-slate-400">
              <span className="size-2 rounded-full" style={{ background: color }} />
              {label}
            </span>
            <span className="font-medium tabular-nums">{units(v)}</span>
          </div>
        ))}
      {row.band && (
        <div className="mt-1 border-t border-slate-100 pt-1 text-slate-500 dark:border-slate-800">
          Likely range: {units(row.band[0])} – {units(row.band[1])}
        </div>
      )}
      {row.overridden && <div className="mt-1 font-medium text-amber-600">Planner override</div>}
    </div>
  );
}

export function ForecastChart({
  history,
  forecast,
  scenario,
  showBaseline = true,
  height = 340,
}: {
  history: HistoryPoint[];
  forecast: ForecastPoint[];
  scenario?: ForecastPoint[];
  showBaseline?: boolean;
  height?: number;
}) {
  const rows: Row[] = [
    ...history.map((h) => ({ week: h.week, actual: h.actual, backtest: h.forecast })),
    ...forecast.map((f, i) => ({
      week: f.week,
      final: f.final,
      baseline: showBaseline ? f.baseline : null,
      band: [f.p10, f.p90] as [number, number],
      scenario: scenario?.[i]?.final,
      overridden: Boolean(f.override),
    })),
  ];
  // Join the forecast line to the last actual so there is no visual gap.
  const lastHist = history[history.length - 1];
  if (lastHist && forecast.length) {
    const idx = history.length - 1;
    rows[idx] = { ...rows[idx], final: lastHist.actual, ...(scenario ? { scenario: lastHist.actual } : {}) };
  }
  const splitWeek = lastHist?.week;

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
        <CartesianGrid stroke={C.grid} vertical={false} />
        <XAxis
          dataKey="week"
          tickFormatter={shortDate}
          minTickGap={36}
          tickLine={false}
          axisLine={{ stroke: C.grid }}
        />
        <YAxis tickFormatter={(v) => units(v)} tickLine={false} axisLine={false} width={56} />
        <Tooltip content={<ChartTooltip />} />
        <Legend iconType="plainline" wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
        <Area
          dataKey="band"
          name="Likely range (P10–P90)"
          stroke="none"
          fill={C.band}
          fillOpacity={0.15}
          isAnimationActive={false}
          legendType="square"
        />
        <Line dataKey="actual" name="Actual sales" stroke={C.actual} strokeWidth={1.75} dot={false} isAnimationActive={false} />
        <Line
          dataKey="backtest"
          name="Past forecasts"
          stroke={C.forecast}
          strokeWidth={1.25}
          strokeOpacity={0.55}
          dot={false}
          isAnimationActive={false}
          connectNulls
        />
        {showBaseline && (
          <Line
            dataKey="baseline"
            name="Baseline (no events)"
            stroke={C.baseline}
            strokeDasharray="4 4"
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        )}
        <Line
          dataKey="final"
          name="Forecast"
          stroke={C.forecast}
          strokeWidth={2.5}
          isAnimationActive={false}
          dot={(props: { cx?: number; cy?: number; payload?: Row; index?: number }) =>
            props.payload?.overridden ? (
              <circle key={props.index} cx={props.cx} cy={props.cy} r={4.5} fill={C.override} stroke="white" strokeWidth={1.5} />
            ) : (
              <g key={props.index} />
            )
          }
        />
        {scenario && (
          <Line dataKey="scenario" name="What-if" stroke={C.scenario} strokeWidth={2.5} dot={false} isAnimationActive={false} />
        )}
        {splitWeek && <ReferenceLine x={splitWeek} stroke={C.baseline} strokeDasharray="2 4" label={{ value: "today", position: "insideTopRight", fontSize: 11, fill: "var(--chart-axis)" }} />}
      </ComposedChart>
    </ResponsiveContainer>
  );
}

/** Tiny inline trend line: history in slate, forecast tail in indigo. */
export function Sparkline({ values, forecastCount = 4, width = 120, height = 32 }: { values: number[]; forecastCount?: number; width?: number; height?: number }) {
  if (values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const x = (i: number) => (i / (values.length - 1)) * (width - 4) + 2;
  const y = (v: number) => height - 3 - ((v - min) / span) * (height - 6);
  const split = values.length - forecastCount - 1;
  const path = (from: number, to: number) =>
    values
      .slice(from, to + 1)
      .map((v, k) => `${k === 0 ? "M" : "L"}${x(from + k).toFixed(1)},${y(v).toFixed(1)}`)
      .join(" ");
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
      <path d={path(0, split)} fill="none" stroke="var(--chart-baseline)" strokeWidth={1.5} />
      <path d={path(split, values.length - 1)} fill="none" stroke="var(--chart-forecast)" strokeWidth={2} />
      <circle cx={x(values.length - 1)} cy={y(values[values.length - 1])} r={2.5} fill="var(--chart-forecast)" />
    </svg>
  );
}
