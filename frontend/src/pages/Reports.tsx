import { useState } from "react";
import { Download } from "lucide-react";
import { useJob } from "../hooks/useJob";
import { useToast } from "../hooks/useToast";
import { api, errMsg } from "../services/api";
import { NeedJob, PageHeader } from "../components/ui";

const FORMATS = [
  ["pdf", "PDF report", "Dataset summary, severity distribution, clusters, anomalies, root-cause hypotheses with evidence and recommendations."],
  ["csv", "CSV (clusters)", "One row per cluster: size, severity, priority, time range, services, template, summary."],
  ["json", "JSON (full)", "Machine-readable export: dataset, configuration, clusters, anomalies, insights, evaluation."],
] as const;

export default function Reports() {
  const { jobId, job } = useJob();
  const { notify } = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const download = async (fmt: string) => {
    setBusy(fmt);
    try {
      const r = await api.get(`/analysis/${jobId}/export`, { params: { format: fmt }, responseType: "blob" });
      const url = URL.createObjectURL(r.data);
      const a = Object.assign(document.createElement("a"), { href: url, download: `atlas_job${jobId}.${fmt}` });
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
      notify(`${fmt.toUpperCase()} report downloaded`);
    } catch (e) { notify(errMsg(e), "err"); } finally { setBusy(null); }
  };
  return (
    <div>
      <PageHeader title="Reports" sub={job ? `Export results for analysis #${job.id} (${job.dataset_name || job.filename}). Hypotheses are labelled as potential, unconfirmed causes.` : "Export analysis results."} />
      <NeedJob>
        <div className="grid md:grid-cols-3 gap-4">{FORMATS.map(([f, t, d]) => (
          <div key={f} className="card flex flex-col gap-3"><h2 className="font-semibold">{t}</h2><p className="text-sm text-dim flex-1">{d}</p>
            <button className="btn-primary justify-center" disabled={busy !== null} onClick={() => download(f)}><Download size={16} />{busy === f ? "Preparing…" : `Download ${f.toUpperCase()}`}</button></div>))}</div>
      </NeedJob>
    </div>
  );
}
