import { Link } from "react-router-dom";
import { Boxes, CheckCircle2, Flame, ScrollText, Siren } from "lucide-react";
import { useJob } from "../hooks/useJob";
import { useApi } from "../hooks/useApi";
import { Async, Badge, Empty, NeedJob, PageHeader, Stat, SyntheticBanner } from "../components/ui";
import { AnomalyTimeline, ClusterSizes, ErrorRateChart, HBar, SeverityPie, VolumeChart } from "../charts/Charts";
import { fmtTime, kindLabel } from "../utils/format";
import { Summary, Timeline } from "../types";

export default function Overview() {
  const { jobId, jobs } = useJob();
  const summary = useApi<Summary>(jobId ? `/analysis/${jobId}/summary` : null);
  const timeline = useApi<Timeline>(jobId ? `/analysis/${jobId}/timeline` : null);
  return (
    <div>
      <PageHeader title="Overview" sub="Health of the selected log analysis at a glance. Every value is computed from the uploaded logs." />
      <NeedJob>
        <Async state={summary}>{(s) => (
          <div className="space-y-6">
            {s.is_synthetic && <SyntheticBanner />}
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
              <Stat label="Logs analyzed" value={s.total_logs.toLocaleString()} icon={<ScrollText size={18} />} />
              <Stat label="Error clusters" value={s.n_clusters} icon={<Boxes size={18} />} tone="text-accent2" hint="Groups of similar log messages found by clustering (all severities)." />
              <Stat label="Critical clusters" value={s.critical} tone="text-crit" icon={<Flame size={18} />} hint="Clusters whose heuristic priority score is Critical. See the cluster page for the scoring factors." />
              <Stat label="Anomalies" value={s.anomalies} tone="text-high" icon={<Siren size={18} />} />
              <Stat label="Status" value={<span className="text-accent text-xl capitalize">{s.job.status}</span>} icon={<CheckCircle2 size={18} />} />
            </div>
            <div className="grid lg:grid-cols-3 gap-4">
              <div className="card lg:col-span-2"><div className="h-title">Log volume & errors over time {timeline.data?.freq && <span className="normal-case tracking-normal">({timeline.data.freq} buckets)</span>}</div>
                {timeline.data?.points.length ? <VolumeChart data={timeline.data.points} /> : <Empty title="No timestamps" text="Timestamps could not be parsed, so there is no time axis." />}</div>
              <div className="card"><div className="h-title">Severity distribution</div><SeverityPie levels={s.levels} /></div>
            </div>
            {!!timeline.data?.points.length && (
              <div className="grid lg:grid-cols-3 gap-4">
                <div className="card"><div className="h-title">Error rate over time</div><ErrorRateChart data={timeline.data.points} /></div>
                <div className="card"><div className="h-title">Anomaly timeline</div><AnomalyTimeline data={timeline.data.points} /></div>
                <div className="card"><div className="h-title">Top services with errors</div>
                  {Object.keys(s.error_services).length ? <HBar data={Object.entries(s.error_services).map(([label, value]) => ({ label, value }))} name="errors" /> : <p className="text-dim text-sm">No ERROR/FATAL logs.</p>}</div>
              </div>)}
            <div className="grid lg:grid-cols-2 gap-4">
              <div className="card"><div className="h-title">Top error clusters (by priority)</div>
                <table className="tbl"><tbody>{s.top_clusters.map((c) => (
                  <tr key={c.id}><td><Badge v={c.priority} /></td><td><Link className="hover:text-accent" to={`/clusters/${c.id}`}>{c.name}</Link></td><td className="text-right tabular-nums text-dim">{c.size.toLocaleString()}</td></tr>))}</tbody></table>
                <div className="h-title mt-4">Error cluster distribution</div>
                <ClusterSizes data={s.top_clusters.map((c) => ({ label: c.name.slice(0, 26), value: c.size, priority: c.priority }))} />
              </div>
              <div className="space-y-4">
                <div className="card"><div className="h-title">Recent anomalies</div>
                  {s.recent_anomalies.length === 0 && <p className="text-dim text-sm">No anomalies detected.</p>}
                  {s.recent_anomalies.map((a) => (
                    <div key={a.id} className="py-2 border-b border-line/60 last:border-0 text-sm">
                      <div className="flex gap-2 items-center flex-wrap"><Badge v={a.severity} /><span className="mono text-dim">{kindLabel(a.kind)}</span><span className="ml-auto mono text-dim">{fmtTime(a.detected_at)}</span></div>
                      <div className="mt-1">{a.reason}</div>
                    </div>))}
                  <Link to="/anomalies" className="text-accent text-sm">All anomalies →</Link></div>
                <div className="card"><div className="h-title">Recent analysis jobs</div>
                  {jobs.slice(0, 6).map((j) => (
                    <div key={j.id} className="flex justify-between gap-2 text-sm py-1"><span className="truncate">#{j.id} · {j.dataset_name || j.filename}</span><span className={j.status === "failed" ? "text-crit" : "text-dim"}>{j.status}</span></div>))}
                </div>
              </div>
            </div>
          </div>)}
        </Async>
      </NeedJob>
    </div>
  );
}
