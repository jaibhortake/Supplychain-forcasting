import { useQuery } from "@tanstack/react-query";
import {
  BellRing,
  CalendarDays,
  FlaskConical,
  History,
  LayoutDashboard,
  Menu,
  MessageSquare,
  Moon,
  Sun,
  Target,
  TrendingUp,
  UserRound,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { api, getUserName, setUserName } from "../api/client";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/forecast", label: "Forecast & stock", icon: TrendingUp },
  { to: "/scenarios", label: "What-if simulator", icon: FlaskConical },
  { to: "/accuracy", label: "Accuracy (FVA)", icon: Target },
  { to: "/alerts", label: "Alerts", icon: BellRing },
  { to: "/events", label: "Business events", icon: CalendarDays },
  { to: "/overrides", label: "Overrides & audit", icon: History },
  { to: "/assistant", label: "Ask the forecast", icon: MessageSquare },
];

function useTheme() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    try {
      localStorage.setItem("theme", dark ? "dark" : "light");
    } catch {
      /* ignore */
    }
  }, [dark]);
  return [dark, setDark] as const;
}

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const [dark, setDark] = useTheme();
  const [name, setName] = useState(getUserName);
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 60_000 });
  const alerts = useQuery({ queryKey: ["anomalies", "unexplained"], queryFn: () => api.anomalies("unexplained") });

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2.5 px-5 py-5">
        <div className="grid size-9 place-items-center rounded-xl bg-indigo-600 text-white shadow-sm">
          <TrendingUp className="size-5" />
        </div>
        <div>
          <div className="text-sm font-semibold leading-tight">Demand Planner</div>
          <div className="text-xs text-slate-500 dark:text-slate-400">Context-aware forecasting</div>
        </div>
      </div>

      <nav className="flex-1 space-y-0.5 px-3" aria-label="Main">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            onClick={onNavigate}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition ${
                isActive
                  ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
              }`
            }
          >
            <Icon className="size-4" />
            <span className="flex-1">{label}</span>
            {to === "/alerts" && alerts.data && alerts.data.length > 0 && (
              <span className="rounded-full bg-red-100 px-1.5 text-xs font-semibold text-red-700 dark:bg-red-950 dark:text-red-300">
                {alerts.data.length}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="space-y-3 border-t border-slate-200 p-4 dark:border-slate-800">
        <label className="block">
          <span className="label flex items-center gap-1">
            <UserRound className="size-3" /> Signed in as (for the audit log)
          </span>
          <input
            className="input py-1.5!"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onBlur={() => setUserName(name.trim() || "planner")}
          />
        </label>
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400" title={health.data?.llm.url}>
            <span
              className={`size-2 rounded-full ${
                health.data?.llm.available ? "bg-emerald-500" : health.isLoading ? "bg-slate-400" : "bg-amber-500"
              }`}
            />
            AI assistant {health.data?.llm.available ? "online" : health.isLoading ? "…" : "offline"}
          </span>
          <button className="btn-ghost p-2!" onClick={() => setDark(!dark)} aria-label="Toggle dark mode">
            {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Layout() {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setOpen(false), [location.pathname]);

  return (
    <div className="min-h-screen lg:pl-64">
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-slate-200 bg-white lg:block dark:border-slate-800 dark:bg-slate-900">
        <Sidebar />
      </aside>

      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-slate-900/40" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-72 bg-white shadow-xl dark:bg-slate-900">
            <button className="absolute right-3 top-5 rounded-md p-1 text-slate-400" onClick={() => setOpen(false)} aria-label="Close menu">
              <X className="size-5" />
            </button>
            <Sidebar onNavigate={() => setOpen(false)} />
          </aside>
        </div>
      )}

      <div className="sticky top-0 z-30 flex items-center gap-3 border-b border-slate-200 bg-white/80 px-4 py-3 backdrop-blur lg:hidden dark:border-slate-800 dark:bg-slate-900/80">
        <button className="btn-ghost p-2!" onClick={() => setOpen(true)} aria-label="Open menu">
          <Menu className="size-5" />
        </button>
        <span className="font-semibold">Demand Planner</span>
      </div>

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
        <Outlet />
      </main>
    </div>
  );
}
