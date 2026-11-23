import { FormEvent, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Boxes, ChevronRight, Compass, FileDown, FlaskConical, LayoutDashboard, Lightbulb, Moon, ScrollText, Search, Siren, Sun, Upload } from "lucide-react";
import { useJob } from "../hooks/useJob";
import { useTheme } from "../hooks/useTheme";

const NAV = [
  ["/", "Overview", LayoutDashboard], ["/logs", "Log Explorer", ScrollText], ["/clusters", "Cluster Explorer", Boxes], ["/anomalies", "Anomaly Center", Siren],
  ["/insights", "Root-Cause Insights", Lightbulb], ["/evaluation", "Model Evaluation", FlaskConical], ["/upload", "Upload & Analysis", Upload], ["/reports", "Reports", FileDown],
] as const;

function Breadcrumbs() {
  const { pathname } = useLocation();
  const parts = pathname.split("/").filter(Boolean);
  const label = (p: string) => NAV.find(([to]) => to === "/" + p)?.[1] ?? (/^\d+$/.test(p) ? `#${p}` : p);
  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-1 text-xs text-dim">
      <Link to="/" className="hover:text-ink">Home</Link>
      {parts.map((p, i) => <span key={i} className="flex items-center gap-1"><ChevronRight size={12} />{i < parts.length - 1 ? <Link className="hover:text-ink" to={"/" + parts.slice(0, i + 1).join("/")}>{label(p)}</Link> : <span className="text-ink font-medium">{label(p)}</span>}</span>)}
    </nav>
  );
}

export default function AppLayout() {
  const { jobs, jobId, setJobId } = useJob();
  const { theme, toggle } = useTheme();
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const search = (e: FormEvent) => { e.preventDefault(); nav(`/logs?q=${encodeURIComponent(q)}`); };
  return (
    <div className="min-h-screen flex flex-col md:flex-row">
      <aside className="md:w-64 md:min-h-screen border-b md:border-b-0 md:border-r border-line bg-panel/70 backdrop-blur p-4 flex md:flex-col gap-5 overflow-x-auto md:sticky md:top-0 md:h-screen">
        <Link to="/" className="flex items-center gap-3 whitespace-nowrap">
          <span className="w-9 h-9 rounded-xl grid place-items-center text-white shadow-lg shadow-accent/30" style={{ backgroundImage: "linear-gradient(135deg, hsl(var(--accent)), hsl(var(--accent2)))" }}><Compass size={20} /></span>
          <span><span className="block font-bold text-lg leading-none tracking-tight">Atlas</span><span className="block text-[10px] uppercase tracking-[0.16em] text-dim mt-1">Log intelligence</span></span>
        </Link>
        <nav className="flex md:flex-col gap-1" aria-label="Primary">
          {NAV.map(([to, label, Icon]) => (
            <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => `relative flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm whitespace-nowrap transition-colors ${isActive ? "bg-accent/15 text-ink font-medium" : "text-dim hover:text-ink hover:bg-line/50"}`}>
              {({ isActive }) => (<>{isActive && <span className="absolute left-0 top-2 bottom-2 w-1 rounded-r bg-accent" />}<Icon size={17} className={isActive ? "text-accent" : ""} /> {label}</>)}
            </NavLink>
          ))}
        </nav>
        <div className="md:mt-auto min-w-[180px] card !p-3">
          <label className="h-title !mb-1.5 block" htmlFor="job-select">Active analysis</label>
          <select id="job-select" className="input w-full !py-1.5" value={jobId ?? ""} onChange={(e) => setJobId(Number(e.target.value))}>
            {jobs.length === 0 && <option value="">None</option>}
            {jobs.map((j) => <option key={j.id} value={j.id}>#{j.id} · {j.status} · {(j.total_logs || 0).toLocaleString()} logs{j.is_synthetic ? " · demo" : ""}</option>)}
          </select>
        </div>
      </aside>
      <div className="flex-1 min-w-0 flex flex-col">
        <header className="flex items-center gap-3 px-4 md:px-8 py-3 border-b border-line/70 bg-bg/60 backdrop-blur sticky top-0 z-30 flex-wrap">
          <div className="flex-1 min-w-[200px]"><Breadcrumbs /></div>
          <form onSubmit={search} role="search" className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-dim" />
            <input className="input !pl-8 w-60" placeholder="Search logs…" aria-label="Search logs" value={q} onChange={(e) => setQ(e.target.value)} />
          </form>
          <button className="btn-ghost !p-2" onClick={toggle} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`} title="Toggle theme">{theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}</button>
        </header>
        <main className="flex-1 p-4 md:p-8 min-w-0 max-w-[1500px] w-full mx-auto"><Outlet /></main>
      </div>
    </div>
  );
}
