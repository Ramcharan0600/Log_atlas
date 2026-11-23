import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import { api, errMsg } from "../services/api";
import { Async, Badge, ErrorBox, Hint, PageHeader, Pager } from "../components/ui";
import { TrendChart } from "../charts/Charts";
import { fmtTime, kindLabel } from "../utils/format";
import { ClusterDetail as CD, LogRow, Page } from "../types";

export default function ClusterDetail() {
  const { id } = useParams();
  const state = useApi<CD>(`/clusters/${id}`);
  const [logs, setLogs] = useState<Page<LogRow> | null>(null);
  const [page, setPage] = useState(1); const [q, setQ] = useState(""); const [err, setErr] = useState<string | null>(null);
  useEffect(() => { api.get<Page<LogRow>>(`/clusters/${id}/logs`, { params: { page, page_size: 20, q: q || undefined } }).then((r) => setLogs(r.data)).catch((e) => setErr(errMsg(e))); }, [id, page, q]);
  return (
    <Async state={state}>{(c) => (
      <div className="space-y-4">
        <PageHeader title={c.name} sub={c.summary} right={<div className="flex gap-2"><Badge v={c.priority} /><Badge v={c.severity} />{c.is_anomalous && <Badge v="Anomalous" />}</div>} />
        <p className="text-xs text-dim -mt-4">Summary source: {c.summary_source === "rule" ? "rule-based (from verified statistics)" : c.summary_source}</p>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="card"><div className="h-title !mb-1">Events</div><div className="text-2xl font-semibold">{c.size.toLocaleString()}</div></div>
          <div className="card"><div className="h-title !mb-1">First seen</div><div className="mono">{fmtTime(c.first_seen)}</div></div>
          <div className="card"><div className="h-title !mb-1">Last seen</div><div className="mono">{fmtTime(c.last_seen)}</div></div>
          <div className="card"><div className="h-title !mb-1">Priority score<Hint text="Transparent weighted heuristic for triage; not a statistically validated risk model." /></div><div className="text-2xl font-semibold">{c.priority_score}</div></div>
        </div>
        <div className="grid lg:grid-cols-2 gap-4">
          <div className="card"><div className="h-title">Extracted template</div><pre className="mono whitespace-pre-wrap bg-bg p-3 rounded">{c.template}</pre>
            <div className="h-title mt-4">Common keywords</div><div className="flex flex-wrap gap-1">{c.keywords.map((k) => <span key={k} className="mono bg-line px-1.5 py-0.5 rounded">{k}</span>)}</div>
            <div className="h-title mt-4">Affected services</div><div className="text-sm">{Object.entries(c.services).map(([s, n]) => `${s} (${n})`).join(", ")}</div></div>
          <div className="card"><div className="h-title">Frequency trend</div>{c.trend.length ? <TrendChart data={c.trend} /> : <p className="text-dim text-sm">No time axis available.</p>}
            <p className="text-xs text-dim mt-2">Second-half vs first-half frequency ratio: {c.trend_ratio?.toFixed(2)}</p></div>
        </div>
        <div className="grid lg:grid-cols-2 gap-4">
          <div className="card"><div className="h-title">Representative messages</div>{c.representatives.map((r, i) => <pre key={i} className="mono whitespace-pre-wrap break-words bg-bg p-2 rounded mb-2">{r}</pre>)}</div>
          <div className="card"><div className="h-title">Why this priority?</div><p className="text-sm mb-3">{c.priority_explanation}</p>
            <table className="tbl"><tbody>{Object.entries(c.priority_factors).map(([k, v]) => <tr key={k}><td className="text-dim">{k}</td><td><div className="h-1.5 bg-bg rounded w-40 inline-block align-middle mr-2"><div className="h-full bg-accent rounded" style={{ width: `${v * 100}%` }} /></div>{v.toFixed(2)}</td></tr>)}</tbody></table></div>
        </div>
        <div className="grid lg:grid-cols-2 gap-4">
          <div className="card"><div className="h-title">Related clusters (centroid similarity)</div>
            {c.related.length === 0 ? <p className="text-dim text-sm">No similar clusters above the 0.3 threshold.</p> : c.related.map((r) => <div key={r.id} className="flex justify-between text-sm py-1"><Link className="hover:text-accent" to={`/clusters/${r.id}`}>{r.name}</Link><span className="text-dim tabular-nums">{r.similarity}</span></div>)}</div>
          <div className="card"><div className="h-title">Anomalies in this cluster</div>
            {c.anomalies.length === 0 ? <p className="text-dim text-sm">None flagged.</p> : c.anomalies.map((a) => <div key={a.id} className="text-sm py-1.5 border-b border-line/60 last:border-0"><span className="mono text-dim">{kindLabel(a.kind)}</span> — {a.reason}</div>)}</div>
        </div>
        <div className="card overflow-x-auto">
          <div className="flex justify-between items-center mb-2 gap-2 flex-wrap"><div className="h-title !mb-0">Logs in this cluster ({logs?.total.toLocaleString() ?? "…"})</div>
            <input className="input w-60" placeholder="Search within cluster…" aria-label="Search within cluster" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
            {logs && <Pager page={page} total={logs.total} size={20} onPage={setPage} />}</div>
          {err && <ErrorBox msg={err} />}
          <table className="tbl"><thead><tr><th>Time</th><th>Severity</th><th>Service</th><th>Message</th></tr></thead>
            <tbody>{logs?.items.map((l) => <tr key={l.id}><td className="mono text-dim whitespace-nowrap">{fmtTime(l.timestamp)}</td><td><Badge v={l.severity} /></td><td className="text-dim">{l.service}</td><td className="mono break-words">{l.original_message}</td></tr>)}</tbody></table>
        </div>
      </div>)}</Async>
  );
}
