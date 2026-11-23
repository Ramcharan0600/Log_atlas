import { useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import { useJob } from "../hooks/useJob";
import { Async, Badge, Empty, NeedJob, PageHeader } from "../components/ui";
import { fmtTime } from "../utils/format";
import { ClusterBrief } from "../types";

export default function Clusters() {
  const { jobId } = useJob();
  const [priority, setPriority] = useState(""); const [q, setQ] = useState(""); const [anom, setAnom] = useState(false);
  const qs = new URLSearchParams({ ...(priority && { priority }), ...(q && { q }), ...(anom && { anomalous: "true" }) }).toString();
  const state = useApi<ClusterBrief[]>(jobId ? `/analysis/${jobId}/clusters?${qs}` : null);
  return (
    <div>
      <PageHeader title="Cluster Explorer" sub="Cluster names are generated from each cluster's dominant log template, never hardcoded." />
      <NeedJob>
        <div className="card mb-4 flex flex-wrap gap-2 items-center">
          <input className="input w-64" placeholder="Filter by name…" aria-label="Filter by name" value={q} onChange={(e) => setQ(e.target.value)} />
          <select className="input" aria-label="Priority" value={priority} onChange={(e) => setPriority(e.target.value)}><option value="">All priorities</option>{["Critical", "High", "Medium", "Low"].map((p) => <option key={p}>{p}</option>)}</select>
          <label className="text-sm flex items-center gap-2"><input type="checkbox" checked={anom} onChange={(e) => setAnom(e.target.checked)} /> Anomalous only</label>
        </div>
        <Async state={state}>{(cl) => cl.length === 0 ? <Empty title="No clusters match" /> : (
          <div className="card overflow-x-auto">
            <table className="tbl"><thead><tr><th>Priority</th><th>Cluster</th><th className="text-right">Events</th><th>Severity</th><th>First seen</th><th>Last seen</th><th>Services</th><th>Anomaly</th></tr></thead>
              <tbody>{cl.map((c) => (
                <tr key={c.id}><td><Badge v={c.priority} /></td>
                  <td className="max-w-sm"><Link className="hover:text-accent font-medium" to={`/clusters/${c.id}`}>{c.name}</Link><div className="text-dim text-xs mt-0.5">{c.keywords.slice(0, 5).join(" · ")}</div></td>
                  <td className="text-right tabular-nums">{c.size.toLocaleString()}</td><td><Badge v={c.severity} /></td>
                  <td className="mono text-dim whitespace-nowrap">{fmtTime(c.first_seen)}</td><td className="mono text-dim whitespace-nowrap">{fmtTime(c.last_seen)}</td>
                  <td className="text-dim text-xs">{Object.keys(c.services).slice(0, 3).join(", ")}</td><td>{c.is_anomalous ? <span className="text-high">● flagged</span> : <span className="text-dim">—</span>}</td></tr>))}</tbody></table>
          </div>)}</Async>
      </NeedJob>
    </div>
  );
}
