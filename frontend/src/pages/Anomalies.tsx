import { useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import { useJob } from "../hooks/useJob";
import { Async, Badge, Empty, NeedJob, PageHeader, Skeleton } from "../components/ui";
import { TrendChart } from "../charts/Charts";
import { fmtTime, kindLabel } from "../utils/format";
import { Anomaly, AnomalyDetail } from "../types";

type List = { total: number; items: Anomaly[]; kinds: string[] };

export default function Anomalies() {
  const { jobId } = useJob();
  const [kind, setKind] = useState(""); const [min, setMin] = useState(0); const [sel, setSel] = useState<number | null>(null);
  const state = useApi<List>(jobId ? `/analysis/${jobId}/anomalies?page_size=100&min_score=${min}${kind ? `&kind=${encodeURIComponent(kind)}` : ""}` : null);
  const detail = useApi<AnomalyDetail>(jobId && sel ? `/analysis/${jobId}/anomalies/${sel}` : null);
  return (
    <div>
      <PageHeader title="Anomaly Center" sub="Each anomaly states which detector flagged it and why. Scores are detector-specific and not comparable across kinds." />
      <NeedJob>
        <Async state={state}>{(d) => (
          <>
            <div className="card mb-4 flex flex-wrap gap-3 items-center">
              <select className="input" aria-label="Detector" value={kind} onChange={(e) => setKind(e.target.value)}><option value="">All detectors</option>{d.kinds.map((k) => <option key={k} value={k}>{kindLabel(k)}</option>)}</select>
              <label className="text-sm flex items-center gap-2">Min score <input type="range" min={0} max={1} step={0.05} value={min} onChange={(e) => setMin(Number(e.target.value))} /> {min.toFixed(2)}</label>
              <span className="text-dim text-sm ml-auto">{d.total} anomalies</span>
            </div>
            {d.items.length === 0 ? <Empty title="No anomalies detected" text="Detectors found nothing unusual at the configured thresholds (or filters exclude everything)." /> : (
              <div className="grid lg:grid-cols-5 gap-4">
                <div className="card lg:col-span-3 overflow-x-auto">
                  <table className="tbl"><thead><tr><th>Score</th><th>Detector</th><th>Detected</th><th>Severity</th><th>Cluster</th></tr></thead>
                    <tbody>{d.items.map((a) => (
                      <tr key={a.id} onClick={() => setSel(a.id)} className={`cursor-pointer hover:bg-line/40 ${sel === a.id ? "bg-accent/10" : ""}`}>
                        <td className="tabular-nums">{a.score.toFixed(2)}</td><td><div className="mono">{kindLabel(a.kind)}</div><div className="text-xs text-dim max-w-sm">{a.reason}</div></td>
                        <td className="mono text-dim whitespace-nowrap">{fmtTime(a.detected_at)}</td><td><Badge v={a.severity} /></td><td className="text-xs">{a.cluster ? <Link className="hover:text-accent" onClick={(e) => e.stopPropagation()} to={`/clusters/${a.cluster}`}>{a.cluster_name}</Link> : "—"}</td></tr>))}</tbody></table>
                </div>
                <div className="lg:col-span-2 space-y-4">
                  {!sel ? <div className="card text-dim text-sm">Select an anomaly to see the detection reason, potential impact, trend and related logs.</div> : !detail.data ? <Skeleton className="h-64" /> : (
                    <div className="card space-y-3">
                      <div className="flex gap-2 items-center"><Badge v={detail.data.severity} /><span className="mono">{kindLabel(detail.data.kind)}</span></div>
                      <div><div className="h-title">Detection reason</div><p className="text-sm">{detail.data.reason}</p></div>
                      <div><div className="h-title">Potential impact</div><p className="text-sm">{detail.data.impact}</p></div>
                      {detail.data.trend.length > 0 && <div><div className="h-title">Cluster trend</div><TrendChart data={detail.data.trend} /></div>}
                      <div><div className="h-title">Related logs ({detail.data.n_logs})</div>
                        {detail.data.logs.slice(0, 8).map((l) => <pre key={l.id} className="mono whitespace-pre-wrap break-words bg-bg p-2 rounded mb-1">{l.timestamp ? fmtTime(l.timestamp) + " " : ""}{l.original_message}</pre>)}</div>
                    </div>)}
                </div>
              </div>)}
          </>)}</Async>
      </NeedJob>
    </div>
  );
}
