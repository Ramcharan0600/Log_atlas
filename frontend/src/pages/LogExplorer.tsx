import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import { useJob } from "../hooks/useJob";
import { api, errMsg } from "../services/api";
import { Badge, Empty, ErrorBox, NeedJob, PageHeader, Pager, Skeleton } from "../components/ui";
import { fmtTime } from "../utils/format";
import { LogRow, Page } from "../types";

type Facets = { services: string[]; severities: string[]; clusters: { id: number; name: string }[] };
const SIZE = 50;

export default function LogExplorer() {
  const { jobId } = useJob();
  const [sp, setSp] = useSearchParams();
  const [res, setRes] = useState<Page<LogRow> | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState<LogRow | null>(null);
  const facets = useApi<Facets>(jobId ? `/analysis/${jobId}/facets` : null).data;
  const f = Object.fromEntries(sp.entries());
  const page = Number(f.page || 1);
  const set = (k: string, v: string) => { const n = new URLSearchParams(sp); if (v) n.set(k, v); else n.delete(k); if (k !== "page") n.delete("page"); setSp(n); };
  const key = sp.toString();
  useEffect(() => {
    if (!jobId) return;
    setErr(null);
    const params: Record<string, string | number> = { page_size: SIZE };
    for (const k of ["q", "severity", "service", "cluster", "anomaly", "start", "end", "page"]) if (f[k]) params[k] = f[k];
    api.get<Page<LogRow>>(`/analysis/${jobId}/logs`, { params }).then((r) => setRes(r.data)).catch((e) => setErr(errMsg(e)));
  }, [jobId, key]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div>
      <PageHeader title="Log Explorer" sub="Search, filter and inspect individual parsed logs. Messages are rendered as plain text." />
      <NeedJob>
        <div className="card mb-4 grid grid-cols-2 lg:grid-cols-8 gap-2">
          <input className="input col-span-2" placeholder="Search message… (Enter)" aria-label="Search" defaultValue={f.q} key={f.q} onKeyDown={(e) => e.key === "Enter" && set("q", (e.target as HTMLInputElement).value)} />
          <select className="input" aria-label="Severity" value={f.severity || ""} onChange={(e) => set("severity", e.target.value)}><option value="">All severities</option>{facets?.severities.map((l) => <option key={l}>{l}</option>)}</select>
          <select className="input" aria-label="Service" value={f.service || ""} onChange={(e) => set("service", e.target.value)}><option value="">All services</option>{facets?.services.map((s) => <option key={s}>{s}</option>)}</select>
          <select className="input" aria-label="Cluster" value={f.cluster || ""} onChange={(e) => set("cluster", e.target.value)}><option value="">All clusters</option>{facets?.clusters.map((c) => <option key={c.id} value={c.id}>#{c.id} {c.name.slice(0, 40)}</option>)}</select>
          <select className="input" aria-label="Anomaly" value={f.anomaly || ""} onChange={(e) => set("anomaly", e.target.value)}><option value="">Any anomaly state</option><option value="true">Anomalous</option><option value="false">Normal</option></select>
          <input type="datetime-local" className="input" aria-label="From" title="From (UTC)" value={f.start || ""} onChange={(e) => set("start", e.target.value)} />
          <input type="datetime-local" className="input" aria-label="To" title="To (UTC)" value={f.end || ""} onChange={(e) => set("end", e.target.value)} />
        </div>
        {err && <ErrorBox msg={err} />}
        {!res && !err ? <Skeleton className="h-96" /> : res && (
          res.total === 0 ? <Empty title="No logs match these filters" action={<button className="btn-ghost" onClick={() => setSp({})}>Clear filters</button>} /> : (
            <div className="card overflow-x-auto">
              <div className="flex justify-between items-center mb-2 text-sm text-dim"><span>{res.total.toLocaleString()} logs</span><Pager page={page} total={res.total} size={SIZE} onPage={(p) => set("page", String(p))} /></div>
              <table className="tbl"><thead><tr><th>Time</th><th>Severity</th><th>Service</th><th>Message</th><th>Cluster</th><th title="Flagged by an anomaly detector">Anom.</th></tr></thead>
                <tbody>{res.items.map((l) => (
                  <tr key={l.id} className="cursor-pointer hover:bg-line/40" onClick={() => setOpen(l)}>
                    <td className="mono text-dim whitespace-nowrap">{fmtTime(l.timestamp)}</td><td><Badge v={l.severity} /></td><td className="text-dim">{l.service}</td>
                    <td className="mono max-w-xl truncate">{l.original_message}</td><td className="mono">#{l.cluster_id}</td><td>{l.anomaly_flag ? <span className="text-high" title={`score ${l.anomaly_score}`}>●</span> : ""}</td></tr>))}</tbody></table>
            </div>))}
        {open && (
          <div className="fixed inset-0 bg-black/50 flex justify-end z-50" onClick={() => setOpen(null)}>
            <aside className="w-full max-w-2xl bg-panel border-l border-line p-6 overflow-y-auto" onClick={(e) => e.stopPropagation()} aria-label="Log details">
              <div className="flex justify-between mb-4"><h2 className="font-semibold">Log line {open.line_no}</h2><button className="btn-ghost !py-1" onClick={() => setOpen(null)}>Close</button></div>
              <div className="grid md:grid-cols-2 gap-3 mb-4">
                <div><div className="h-title">Original</div><pre className="mono whitespace-pre-wrap break-words bg-bg p-3 rounded">{open.original_message}</pre></div>
                <div><div className="h-title">Normalized</div><pre className="mono whitespace-pre-wrap break-words bg-bg p-3 rounded">{open.normalized_message}</pre></div>
              </div>
              <div className="h-title">Extracted template</div><pre className="mono whitespace-pre-wrap bg-bg p-3 rounded mb-4">{open.template ?? "—"}</pre>
              <div className="h-title">Cluster</div>
              <p className="mb-4 text-sm">{open.cluster_pk ? <Link className="text-accent" to={`/clusters/${open.cluster_pk}`}>{open.cluster_name}</Link> : open.cluster_name ?? `#${open.cluster_id}`}</p>
              <div className="h-title">Parsed fields</div>
              <table className="tbl"><tbody>{(["timestamp", "severity", "service", "component", "host", "ip", "pid", "thread", "request_id", "error_code", "template_id", "anomaly_flag", "anomaly_score"] as const).map((k) => (
                <tr key={k}><td className="text-dim w-40">{k}</td><td className="mono">{open[k] == null || open[k] === "" ? "—" : String(open[k])}</td></tr>))}</tbody></table>
            </aside>
          </div>)}
      </NeedJob>
    </div>
  );
}
