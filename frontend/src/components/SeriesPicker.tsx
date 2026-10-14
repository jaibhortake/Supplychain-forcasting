import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";

/** Selected product/region, kept in the URL so it survives navigation and can be shared. */
export function useSeries() {
  const [params, setParams] = useSearchParams();
  const meta = useQuery({ queryKey: ["meta"], queryFn: api.meta });
  const product = params.get("product") ?? meta.data?.products[0]?.code ?? "";
  const region = params.get("region") ?? meta.data?.regions[0] ?? "";
  const set = (key: "product" | "region", value: string) => {
    const next = new URLSearchParams(params);
    next.set("product", key === "product" ? value : product);
    next.set("region", key === "region" ? value : region);
    setParams(next, { replace: true });
  };
  return { product, region, meta: meta.data, ready: Boolean(product && region), set };
}

export function SeriesPicker({ series }: { series: ReturnType<typeof useSeries> }) {
  const { meta, product, region, set } = series;
  return (
    <div className="flex flex-wrap gap-2">
      <select
        aria-label="Product"
        className="input w-auto!"
        value={product}
        onChange={(e) => set("product", e.target.value)}
      >
        {meta?.products.map((p) => (
          <option key={p.code} value={p.code}>
            {p.code} · {p.name}
          </option>
        ))}
      </select>
      <div className="inline-flex rounded-lg bg-slate-100 p-0.5 dark:bg-slate-800" role="radiogroup" aria-label="Region">
        {meta?.regions.map((r) => (
          <button
            key={r}
            role="radio"
            aria-checked={r === region}
            onClick={() => set("region", r)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
              r === region
                ? "bg-white text-slate-900 shadow-sm dark:bg-slate-950 dark:text-white"
                : "text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
            }`}
          >
            {r}
          </button>
        ))}
      </div>
    </div>
  );
}
