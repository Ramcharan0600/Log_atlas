import { ReactNode } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, Info, Inbox } from "lucide-react";
import { useJob } from "../hooks/useJob";
import { cx } from "../utils/format";

const TONE: Record<string, string> = {
  Critical: "bg-crit/15 text-crit border-crit/40", High: "bg-high/15 text-high border-high/40", Medium: "bg-med/15 text-med border-med/40", Low: "bg-low/15 text-low border-low/40",
  FATAL: "bg-crit/15 text-crit border-crit/40", ERROR: "bg-high/15 text-high border-high/40", WARN: "bg-med/15 text-med border-med/40", INFO: "bg-low/15 text-low border-low/40",
  DEBUG: "bg-line text-dim border-line", UNKNOWN: "bg-line text-dim border-line",
  "Strong evidence": "bg-accent/15 text-accent border-accent/40", "Moderate evidence": "bg-med/15 text-med border-med/40", "Limited evidence": "bg-line text-dim border-line",
};
export const Badge = ({ v, title }: { v: string; title?: string }) => (
  <span title={title} className={cx("inline-block border rounded px-1.5 py-0.5 text-[11px] font-medium whitespace-nowrap", TONE[v] || "bg-line text-dim border-line")}>{v}</span>
);

/** Native-tooltip wrapper with a visible help marker. */
export const Hint = ({ text }: { text: string }) => <span title={text} className="inline-flex align-middle ml-1 text-dim cursor-help" aria-label={text}><Info size={12} /></span>;

export const Stat = ({ label, value, tone, hint, icon }: { label: string; value: ReactNode; tone?: string; hint?: string; icon?: ReactNode }) => (
  <div className="card card-hover relative overflow-hidden">
    <div className="flex items-start justify-between gap-2">
      <div><div className="h-title !mb-2">{label}{hint && <Hint text={hint} />}</div><div className={cx("text-3xl font-bold tabular-nums tracking-tight", tone)}>{value}</div></div>
      {icon && <div className={cx("p-2 rounded-lg bg-line/60", tone || "text-accent")}>{icon}</div>}
    </div>
    <div className={cx("absolute left-0 top-0 h-full w-1 opacity-70", tone ? "bg-current " + tone : "bg-accent")} />
  </div>
);
export const PageHeader = ({ title, sub, right }: { title: string; sub?: string; right?: ReactNode }) => (
  <div className="flex items-end justify-between mb-7 gap-4 flex-wrap">
    <div><h1 className="text-3xl font-bold tracking-tight"><span className="gradient-text">{title}</span></h1>{sub && <p className="text-dim text-sm mt-1.5 max-w-3xl leading-relaxed">{sub}</p>}</div>{right}
  </div>
);
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
export const Empty = ({ title, text, action }: { title: string; text?: string; action?: ReactNode }) => (
  <div className="card text-center py-14 border-dashed"><div className="mx-auto mb-3 w-12 h-12 rounded-2xl bg-accent/15 text-accent grid place-items-center"><Inbox size={22} /></div><div className="font-medium">{title}</div>{text && <p className="text-dim text-sm mt-1">{text}</p>}{action && <div className="mt-4">{action}</div>}</div>
);
export const SyntheticBanner = () => (
  <div className="card !py-2 border-med/50 text-med text-sm mb-4 flex items-center gap-2"><AlertTriangle size={14} /> This analysis uses <b>synthetic demo data</b>. Metrics demonstrate the pipeline, not real-world performance.</div>
);
export const EvidenceTag = ({ t }: { t: string }) => {
  const m: Record<string, string> = { observed: "Observed fact", statistical: "Statistical finding", model: "Model prediction" };
  return <span className="mono text-[10px] uppercase px-1.5 py-0.5 rounded bg-line text-dim mr-2 whitespace-nowrap">{m[t] || t}</span>;
};

/** Renders children only when a completed analysis is selected; otherwise a helpful empty/progress state. */
export function NeedJob({ children }: { children: ReactNode }) {
  const { jobId, job, loaded } = useJob();
  if (!loaded) return <PageSkeleton />;
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
