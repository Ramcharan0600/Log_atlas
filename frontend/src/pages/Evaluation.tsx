import { useState } from "react";
import { useApi } from "../hooks/useApi";
import { useJob } from "../hooks/useJob";
import { useToast } from "../hooks/useToast";
import { api, errMsg } from "../services/api";
import { Async, Empty, ErrorBox, Hint, NeedJob, PageHeader, SyntheticBanner } from "../components/ui";
import { MetricBars } from "../charts/Charts";
import { fmtNum } from "../utils/format";
import { Evaluation, GridRow } from "../types";

const rowLabel = (g: GridRow) => `${g.features}+${g.algorithm}`;

export default function EvaluationPage() {
  const { jobId } = useJob();
  const { notify } = useToast();
  const state = useApi<Evaluation>(jobId ? `/analysis/${jobId}/evaluation` : null);
  const [p, setP] = useState({ eps: 0, min_samples: 3, min_cluster_size: 5, n_clusters: 0, max_unique: 4000 });
  const [busy, setBusy] = useState(false); const [err, setErr] = useState<string | null>(null);
  const run = async () => {
    setBusy(true); setErr(null);
    try { await api.post(`/analysis/${jobId}/evaluation/run`, p); notify("Experiment grid executed and saved"); state.reload(); }
    catch (e) { setErr(errMsg(e)); notify("Experiment failed", "err"); } finally { setBusy(false); }
  };
  const num = (k: keyof typeof p, step = 1) => <label className="text-sm"><div className="text-dim mb-1">{k}</div><input type="number" step={step} className="input w-full" value={p[k]} onChange={(e) => setP({ ...p, [k]: Number(e.target.value) })} /></label>;
  return (
    <div>
      <PageHeader title="Model Evaluation" sub="Every number is measured on this dataset in an executed run. Supervised metrics appear only when ground-truth labels exist." />
      <NeedJob>
        <Async state={state}>{(d) => {
          const ev = d.evaluation, grid = (ev.comparison?.grid ?? []).filter((g) => !g.error);
          const sup = ev.comparison?.supervised;
          return (
            <div className="space-y-6">
              {d.is_synthetic && <SyntheticBanner />}
              {ev.comparison?.warning && <ErrorBox msg={ev.comparison.warning} />}
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="card"><div className="h-title !mb-1">Features used</div><div className="mono">{ev.feature_backend}</div></div>
                <div className="card"><div className="h-title !mb-1">Pipeline throughput</div><div className="text-xl font-semibold">{fmtNum(ev.logs_per_second)} logs/s</div><div className="text-xs text-dim">{ev.total_seconds}s total incl. evaluation</div></div>
                <div className="card"><div className="h-title !mb-1">Final clustering</div><div className="text-sm">{ev.final?.n_clusters} clusters · raw noise {fmtNum((ev.raw_noise_ratio ?? 0) * 100, 1)}%</div><div className="text-xs text-dim">noise re-attached to template groups</div></div>
                <div className="card"><div className="h-title !mb-1">Ground truth</div><div className="text-sm">{ev.has_cluster_labels ? "cluster labels ✓" : "no cluster labels"} · {ev.has_anomaly_labels ? "anomaly labels ✓" : "no anomaly labels"}</div></div>
              </div>

              {grid.length > 0 && (
                <div className="card overflow-x-auto"><div className="h-title">Clustering comparison — TF-IDF vs embeddings × DBSCAN / HDBSCAN / K-Means</div>
                  {ev.comparison?.note && <p className="text-xs text-dim mb-2">{ev.comparison.note}</p>}
                  <table className="tbl"><thead><tr><th>Features</th><th>Algorithm</th><th>Clusters</th><th>Noise</th>{sup && <><th>ARI</th><th>NMI</th><th>Homog.</th><th>Compl.</th><th>V-meas.</th></>}
                    <th>Silhouette<Hint text="Cosine silhouette on non-noise points. Density-based clusters are non-convex, so low silhouette does not imply bad clusters." /></th><th>Davies-Bouldin ↓</th><th>Calinski-H. ↑</th><th>Cluster s</th><th>Feature s</th><th>Peak MB</th></tr></thead>
                    <tbody>{grid.map((g, i) => { const m = g.metrics!; return (
                      <tr key={i}><td><div>{g.features}</div><div className="mono text-dim">{g.feature_backend}</div></td><td>{g.algorithm}<div className="mono text-dim">{JSON.stringify(g.parameters)}</div></td><td>{m.n_clusters}</td><td>{fmtNum(m.noise_ratio * 100, 1)}%</td>
                        {sup && <><td>{fmtNum(m.ari)}</td><td>{fmtNum(m.nmi)}</td><td>{fmtNum(m.homogeneity)}</td><td>{fmtNum(m.completeness)}</td><td>{fmtNum(m.v_measure)}</td></>}
                        <td>{fmtNum(m.silhouette)}</td><td>{fmtNum(m.davies_bouldin)}</td><td>{fmtNum(m.calinski_harabasz)}</td><td>{g.cluster_seconds}</td><td>{g.feature_seconds}</td><td>{g.peak_memory_mb}</td></tr>); })}</tbody></table>
                  <div className="grid lg:grid-cols-2 gap-4 mt-4">
                    {sup && <div><div className="h-title">Agreement with ground truth</div><MetricBars data={grid.map((g) => ({ label: rowLabel(g), ARI: g.metrics!.ari, NMI: g.metrics!.nmi }))} keys={[{ key: "ARI", name: "ARI", color: "hsl(var(--accent))" }, { key: "NMI", name: "NMI", color: "hsl(var(--low))" }]} /></div>}
                    <div><div className="h-title">Runtime (s)</div><MetricBars data={grid.map((g) => ({ label: rowLabel(g), cluster: g.cluster_seconds, features: g.feature_seconds }))} keys={[{ key: "features", name: "Feature generation", color: "hsl(var(--med))" }, { key: "cluster", name: "Clustering", color: "hsl(var(--high))" }]} /></div>
                  </div>
                  <p className="text-xs text-dim mt-3">Memory is peak Python/NumPy allocation (tracemalloc) during clustering. Silhouette / Davies-Bouldin / Calinski-Harabasz assume compact convex clusters and ignore noise points, so they are weak guides for DBSCAN/HDBSCAN; prefer supervised metrics when labels exist. K-Means uses k = number of Drain templates (capped at 50).</p>
                </div>)}

              {ev.template_methods && (
                <div className="card overflow-x-auto"><div className="h-title">Template extraction: Drain3 vs regex-only baseline</div>
                  <table className="tbl"><thead><tr><th>Method</th><th>Templates</th><th>Runtime s</th><th>Logs/s</th>{ev.has_cluster_labels && <th>Grouping accuracy</th>}</tr></thead>
                    <tbody>{Object.entries(ev.template_methods).map(([k, v]) => <tr key={k}><td>{k}</td><td>{v.n_templates}</td><td>{v.runtime_s}</td><td>{fmtNum(v.logs_per_s)}</td>{ev.has_cluster_labels && <td>{fmtNum(v.grouping_accuracy)}</td>}</tr>)}</tbody></table></div>)}

              {ev.anomaly ? (
                <div className="card overflow-x-auto"><div className="h-title">Anomaly detection vs labels</div>
                  <table className="tbl"><thead><tr><th>Detector</th><th>Precision</th><th>Recall</th><th>F1</th><th>ROC-AUC</th><th>PR-AUC</th><th>Flagged / positives</th></tr></thead>
                    <tbody>{Object.entries(ev.anomaly).map(([k, v]) => <tr key={k}><td>{k}</td><td>{fmtNum(v.precision)}</td><td>{fmtNum(v.recall)}</td><td>{fmtNum(v.f1)}</td><td>{fmtNum(v.roc_auc)}</td><td>{fmtNum(v.pr_auc)}</td><td>{v.flagged} / {v.positives}</td></tr>)}</tbody></table>
                  <p className="text-xs text-dim mt-2">{ev.anomaly_note}</p></div>
              ) : <Empty title="No anomaly labels in this dataset" text="Upload data with a normal/anomaly label column (or a labelled dataset such as BGL) to see precision/recall/F1/ROC-AUC." />}

              <div className="card"><div className="h-title">Run a parameter comparison</div>
                <div className="grid grid-cols-2 lg:grid-cols-6 gap-3 items-end">{num("eps", 0.05)}{num("min_samples")}{num("min_cluster_size")}{num("n_clusters")}{num("max_unique", 500)}
                  <button className="btn-primary justify-center" disabled={busy} onClick={run}>{busy ? "Running…" : "Run experiments"}</button></div>
                <p className="text-xs text-dim mt-2">eps = 0 estimates it from the k-distance knee; n_clusters = 0 uses the Drain template count. Results are stored in the experiment history below.</p>{err && <ErrorBox msg={err} />}</div>

              {d.experiments.length > 0 && (
                <div className="card overflow-x-auto"><div className="h-title">Experiment history ({d.experiments.length})</div>
                  <table className="tbl"><thead><tr><th>#</th><th>Type</th><th>Features</th><th>Algorithm</th><th>Parameters</th><th>Key metrics</th><th>Time s</th></tr></thead>
                    <tbody>{d.experiments.slice(0, 40).map((e) => <tr key={e.id}><td>{e.id}</td><td>{e.kind}</td><td>{e.features}</td><td>{e.algorithm}</td><td className="mono max-w-xs truncate" title={JSON.stringify(e.parameters)}>{JSON.stringify(e.parameters)}</td>
                      <td className="mono">{["ari", "nmi", "f1", "roc_auc", "silhouette"].filter((k) => e.metrics[k] != null).map((k) => `${k}=${fmtNum(e.metrics[k])}`).join(" ")}</td><td>{fmtNum(e.execution_time)}</td></tr>)}</tbody></table></div>)}
            </div>);
        }}</Async>
      </NeedJob>
    </div>
  );
}
