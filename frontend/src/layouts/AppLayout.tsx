import { FormEvent, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { ChevronRight, Moon, Search, Sun } from "lucide-react";
import { useJob } from "../hooks/useJob";
import { useTheme } from "../hooks/useTheme";
import { NAV } from "./nav";
import { Notice } from "../components/ui";

function Breadcrumbs() {
  const { pathname } = useLocation();
  const parts = pathname.split("/").filter(Boolean);
  const label = (p: string) => NAV.find(([to]) => to === "/" + p)?.[1] ?? (/^\d+$/.test(p) ? `#${p}` : p);
  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-1 font-mono text-[11px] uppercase tracking-wider text-dim">
      <Link to="/" className="hover:text-ink">Atlas</Link>
      {parts.map((p, i) => <span key={i} className="flex items-center gap-1"><ChevronRight size={11} />{i < parts.length - 1 ? <Link className="hover:text-ink" to={"/" + parts.slice(0, i + 1).join("/")}>{label(p)}</Link> : <span className="text-ink">{label(p)}</span>}</span>)}
    </nav>
  );
}

/** Square mark with a notched corner: a map tile, nothing more. */
const Mark = () => (
  <svg width="26" height="26" viewBox="0 0 26 26" aria-hidden className="shrink-0">
    <path d="M0 0h18l8 8v18H0z" fill="hsl(var(--accent))" /><path d="M6 19V9l7 6 7-6v10" fill="none" stroke="hsl(var(--on-accent))" strokeWidth="2.2" strokeLinejoin="miter" />
  </svg>
);

export default function AppLayout() {
  const { jobs, jobId, setJobId, connError } = useJob();
  const { theme, toggle } = useTheme();
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const search = (e: FormEvent) => { e.preventDefault(); nav(`/logs?q=${encodeURIComponent(q)}`); };
  return (
    <div className="min-h-screen flex flex-col md:flex-row">
      <aside className="md:w-60 md:min-h-screen border-b md:border-b-0 md:border-r border-line bg-panel px-4 py-5 flex md:flex-col gap-6 overflow-x-auto md:sticky md:top-0 md:h-screen">
        <Link to="/" className="flex items-center gap-2.5 whitespace-nowrap">
          <Mark /><span className="font-display font-bold text-[22px] leading-none tracking-tight">Atlas</span>
        </Link>
        <nav className="flex md:flex-col md:gap-px" aria-label="Primary">
          {NAV.map(([to, label], i) => (
            <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => `relative flex items-baseline gap-3 px-2 py-2 text-sm whitespace-nowrap border-l-2 transition-colors ${isActive ? "border-accent text-ink font-semibold bg-ink/[0.05]" : "border-transparent text-dim hover:text-ink hover:border-line"}`}>
              {({ isActive }) => (<><span className={`font-mono text-[10px] ${isActive ? "text-accent" : "text-dim"}`}>{String(i + 1).padStart(2, "0")}</span>{label}</>)}
            </NavLink>
          ))}
        </nav>
        <div className="md:mt-auto min-w-[180px] border-t border-line pt-4">
          <label className="h-title !mb-1.5 block" htmlFor="job-select">Active analysis</label>
          <select id="job-select" className="input w-full !py-1.5" value={jobId ?? ""} onChange={(e) => setJobId(Number(e.target.value))}>
            {jobs.length === 0 && <option value="">None</option>}
            {jobs.map((j) => <option key={j.id} value={j.id}>#{j.id} · {j.status} · {(j.total_logs || 0).toLocaleString()} logs{j.is_synthetic ? " · demo" : ""}</option>)}
          </select>
        </div>
      </aside>
      <div className="flex-1 min-w-0 flex flex-col">
        <header className="flex items-center gap-3 px-4 md:px-8 h-12 border-b border-line bg-bg sticky top-0 z-30 flex-wrap">
          <div className="flex-1 min-w-[200px]"><Breadcrumbs /></div>
          <form onSubmit={search} role="search" className="relative">
            <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-dim" />
            <input className="input !pl-8 !py-1.5 w-60" placeholder="Search logs" aria-label="Search logs" value={q} onChange={(e) => setQ(e.target.value)} />
          </form>
          <button className="btn-ghost !p-1.5" onClick={toggle} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`} title="Toggle theme">{theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}</button>
        </header>
        <main className="flex-1 p-4 md:p-8 min-w-0 max-w-[1500px] w-full mx-auto">{connError && <div className="mb-4"><Notice msg={`${connError} Retrying…`} /></div>}<Outlet /></main>
      </div>
    </div>
  );
}
