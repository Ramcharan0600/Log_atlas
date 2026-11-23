import { Link } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import { useJob } from "../hooks/useJob";
import { Async, Badge, Empty, EvidenceTag, NeedJob, PageHeader } from "../components/ui";
import { fmtTime } from "../utils/format";
import { Insight } from "../types";

export default function Insights() {
  const { jobId } = useJob();
  const state = useApi<Insight[]>(jobId ? `/analysis/${jobId}/insights` : null);
  return (
    <div>
      <PageHeader title="Root-Cause Insights" sub="Hypotheses derived from log evidence. They are potential causes to investigate, never confirmed root causes. The evidence label reflects how much supporting evidence exists, not a probability." />
      <NeedJob>
        <Async state={state}>{(ins) => ins.length === 0 ? <Empty title="No error-dominated clusters" text="No cluster had enough ERROR/FATAL events to form a hypothesis." /> : (
          <div className="space-y-4">{ins.map((i) => (
            <article key={i.id} className="card space-y-4">
              <div className="flex flex-wrap justify-between gap-2"><h2 className="font-semibold text-lg">{i.title}</h2><Badge v={i.confidence} title="Evidence strength: number of independent supporting signals" /></div>
              <p className="text-sm">{i.hypothesis}</p><p className="text-sm text-dim">{i.summary}</p>
              <div className="grid lg:grid-cols-2 gap-4">
                <div><div className="h-title">Evidence</div><ul className="space-y-1.5 text-sm">{i.evidence.map((e, k) => <li key={k}><EvidenceTag t={e.type} />{e.text}</li>)}</ul></div>
                <div className="space-y-4">
                  <div><div className="h-title">Potential causes</div><ul className="list-disc pl-5 text-sm">{i.suspected_causes.map((c) => <li key={c}>{c}</li>)}</ul></div>
                  <div><div className="h-title">Suggested investigation</div><ol className="list-decimal pl-5 text-sm space-y-0.5">{i.recommendations.map((r) => <li key={r}>{r}</li>)}</ol></div>
                </div>
              </div>
              {i.timeline.length > 0 && <div><div className="h-title">Timeline</div><ol className="border-l border-line pl-4 space-y-1 text-sm">{i.timeline.map((t, k) => <li key={k}><span className="mono text-dim mr-2">{fmtTime(t.time)}</span>{t.event}</li>)}</ol></div>}
              <div><div className="h-title">Related clusters</div><div className="flex flex-wrap gap-2">{i.related_clusters.map((c) => <Link key={c.id} to={`/clusters/${c.id}`} className="btn-ghost !py-1 text-xs">{c.name}</Link>)}</div></div>
              <p className="text-xs text-dim border-t border-line pt-3">{i.disclaimer}</p>
            </article>))}</div>)}</Async>
      </NeedJob>
    </div>
  );
}
