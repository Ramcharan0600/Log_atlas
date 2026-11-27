import { ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { NAV } from "../layouts/nav";
import { AlertTriangle, Info, Inbox } from "lucide-react";
import { useJob } from "../hooks/useJob";
import { cx } from "../utils/format";

const TONE: Record<string, string> = {
  Critical: "bg-crit/10 text-crit border-crit/35", High: "bg-high/10 text-high border-high/35", Medium: "bg-med/10 text-med border-med/35", Low: "bg-low/10 text-low border-low/35",
  FATAL: "bg-crit/10 text-crit border-crit/35", ERROR: "bg-high/10 text-high border-high/35", WARN: "bg-med/10 text-med border-med/35", INFO: "bg-low/10 text-low border-low/35",
  DEBUG: "bg-line text-dim border-line", UNKNOWN: "bg-line text-dim border-line",
  "Strong evidence": "bg-accent/10 text-accent border-accent/35", "Moderate evidence": "bg-med/10 text-med border-med/35", "Limited evidence": "bg-line text-dim border-line",
};
export const Badge = ({ v, title }: { v: string; title?: string }) => (
  <span title={title} className={cx("inline-flex items-center gap-1.5 border rounded-sm px-1.5 py-px font-mono text-[10.5px] uppercase tracking-wide whitespace-nowrap", TONE[v] || "bg-line text-dim border-line")}>
    <span className="w-1.5 h-1.5 bg-current" aria-hidden />{v}
  </span>
);

/** Native-tooltip wrapper with a visible help marker. */
export const Hint = ({ text }: { text: string }) => <span title={text} className="inline-flex align-middle ml-1 text-dim cursor-help" aria-label={text}><Info size={12} /></span>;

export const Stat = ({ label, value, tone, hint, icon }: { label: string; value: ReactNode; tone?: string; hint?: string; icon?: ReactNode }) => (
  <div className="card card-hover !p-0 flex flex-col">
    <div className="flex items-center justify-between gap-2 px-4 pt-3.5"><div className="h-title !mb-0">{label}{hint && <Hint text={hint} />}</div>{icon && <span className="text-dim">{icon}</span>}</div>
    <div className={cx("px-4 pt-3 pb-4 font-display text-[40px] leading-none font-bold tabular-nums tracking-tight", tone)}>{value}</div>
  </div>
);
export const PageHeader = ({ title, sub, right }: { title: string; sub?: string; right?: ReactNode }) => {
  const { pathname } = useLocation();
  const i = NAV.findIndex(([to]) => (to === "/" ? pathname === "/" : pathname.startsWith(to)));
  return (
    <div className="flex items-end justify-between mb-7 gap-4 flex-wrap border-b border-ink/30 pb-5">
      <div>
        {i >= 0 && <div className="font-mono text-[11px] tracking-[0.14em] text-accent mb-2">{String(i + 1).padStart(2, "0")} / {String(NAV.length).padStart(2, "0")}</div>}
        <h1 className="text-[34px] leading-none font-bold tracking-[-0.02em]">{title}</h1>{sub && <p className="text-dim text-sm mt-3 max-w-2xl leading-relaxed">{sub}</p>}
      </div>{right}
    </div>
  );
};
export const Skeleton = ({ className = "h-24" }: { className?: string }) => <div className={cx("skeleton", className)} aria-hidden />;
export const PageSkeleton = () => (
  <div className="space-y-4" aria-busy="true" aria-label="Loading">
    <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-20" />)}</div>
    <Skeleton className="h-64" /><Skeleton className="h-48" />
  </div>
);
export const ErrorBox = ({ msg, retry }: { msg: string; retry?: () => void }) => (
  <div className="card border-crit/50 text-crit text-sm flex items-center gap-3" role="alert"><AlertTriangle size={16} /><span className="flex-1">{msg}</span>{retry && <button className="btn-ghost !py-1" onClick={retry}>Retry</button>}</div>
);
/** Something worth knowing that is not a failure. */
export const Notice = ({ msg }: { msg: string }) => (
  <div className="card !py-2 border-med/50 text-med text-sm flex items-center gap-3" role="status"><Info size={16} className="shrink-0" /><span className="flex-1">{msg}</span></div>
);
export const Empty =({ title, text, action }: { title: string; text?: string; action?: ReactNode }) => (
  <div className="card text-center py-14 border-dashed"><div className="mx-auto mb-3 w-12 h-12 rounded-2xl bg-accent/10 text-accent grid place-items-center"><Inbox size={22} /></div><div className="font-display font-bold text-lg">{title}</div>{text && <p className="text-dim text-sm mt-1">{text}</p>}{action && <div className="mt-4">{action}</div>}</div>
);
export const SyntheticBanner = () => (
  <div className="card !py-2 border-med/50 text-med text-sm mb-4 flex items-center gap-2 font-mono text-xs"><AlertTriangle size={14} /> This analysis uses <b>synthetic demo data</b>. Metrics demonstrate the pipeline, not real-world performance.</div>
);
export const EvidenceTag = ({ t }: { t: string }) => {
  const m: Record<string, string> = { observed: "Observed fact", statistical: "Statistical finding", model: "Model prediction" };
  return <span className="mono text-[10px] uppercase px-1.5 py-0.5 rounded bg-line text-dim mr-2 whitespace-nowrap">{m[t] || t}</span>;
};

/** Renders children only when a completed analysis is selected; otherwise a helpful empty/progress state. */
export function NeedJob({ children }: { children: ReactNode }) {
  const { jobId, job, loaded, connError } = useJob();
  if (!loaded) return <PageSkeleton />;
  // the list never arrived: do not claim there are no analyses (the layout shows why)
  if (connError && !job) return <PageSkeleton />;
  if (!jobId || !job) return <Empty title="No completed analysis yet" text="Upload a log file or load a dataset to get started." action={<Link to="/upload" className="btn-primary">Upload & analyze</Link>} />;
  if (job.status === "failed") return <ErrorBox msg={`Analysis #${job.id} failed: ${job.error || "unknown error"}`} />;
  if (job.status !== "completed")
    return <Empty title={`Analysis #${job.id} is ${job.status}`} text={`${job.stage} — ${Math.round(job.progress * 100)}%`} />;
  return <>{children}</>;
}

/** Generic data-state wrapper: skeleton while loading, error with retry, children when data present. */
export function Async<T>({ state, children }: { state: { data: T | null; error: string | null; loading: boolean; reload: () => void }; children: (d: T) => ReactNode }) {
  if (state.error) return <ErrorBox msg={state.error} retry={state.reload} />;
  if (!state.data) return <PageSkeleton />;
  return <>{children(state.data)}</>;
}

export const Pager = ({ page, total, size, onPage }: { page: number; total: number; size: number; onPage: (p: number) => void }) => {
  const pages = Math.max(1, Math.ceil(total / size));
  return (
    <div className="flex items-center gap-2 text-sm text-dim">
      <button className="btn-ghost !py-1" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="Previous page">‹</button>
      <span>Page {page} / {pages}</span>
      <button className="btn-ghost !py-1" disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label="Next page">›</button>
    </div>
  );
};
