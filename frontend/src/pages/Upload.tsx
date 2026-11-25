import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Database, Play, UploadCloud, X } from "lucide-react";
import { api, errMsg } from "../services/api";
import { useJob } from "../hooks/useJob";
import { useApi } from "../hooks/useApi";
import { useToast } from "../hooks/useToast";
import ColumnMapper from "../components/ColumnMapper";
import { Badge, ErrorBox, Hint, PageHeader, Skeleton } from "../components/ui";
import { DatasetInfo, Job, UploadedItem } from "../types";

const DEFAULTS = { features: "tfidf", algorithm: "dbscan", eps: 0, min_samples: 3, min_cluster_size: 5, sim_threshold: 0.5, contamination: 0.02, z_threshold: 3, lowercase: false, keep_stack_trace: false, run_evaluation: true, mask_rules: "email,phone,token,password,apikey" };
type Cfg = typeof DEFAULTS;

export default function UploadPage() {
  const { jobs, refresh, setJobId } = useJob();
  const { notify } = useToast();
  const datasets = useApi<DatasetInfo[]>("/datasets");
  const [files, setFiles] = useState<UploadedItem[]>([]);
  const [pct, setPct] = useState(0); const [err, setErr] = useState(""); const [drag, setDrag] = useState(false);
  const [loading, setLoading] = useState<string | null>(null);
  const [cfg, setCfg] = useState<Cfg>(DEFAULTS);
  const [jobId, setLocalJob] = useState<number | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const job: Job | undefined = jobs.find((j) => j.id === jobId);
  const running = job && (job.status === "queued" || job.status === "running");

  const upload = async (list: FileList | null) => {
    if (!list?.length) return;
    setErr(""); const fd = new FormData(); [...list].forEach((f) => fd.append("files", f));
    try {
      const r = await api.post<UploadedItem[]>("/logs/upload", fd, { onUploadProgress: (e) => setPct(Math.round((e.loaded / (e.total || 1)) * 100)) });
      const bad = r.data.filter((x) => x.error); bad.forEach((b) => notify(`${b.filename}: ${b.error}`, "err"));
      setFiles((cur) => [...cur, ...r.data.filter((x) => x.file_id)]);
    } catch (e) { setErr(errMsg(e)); } finally { setPct(0); if (input.current) input.current.value = ""; }
  };
  const loadDataset = async (name: string) => {
    setLoading(name); setErr("");
    try { const r = await api.post<UploadedItem>("/datasets/load", { name }); setFiles((cur) => cur.some((f) => f.file_id === r.data.file_id) ? cur : [...cur, r.data]); datasets.reload(); }
    catch (e) { setErr(errMsg(e)); } finally { setLoading(null); }
  };
  const start = async () => {
    setErr("");
    try {
      const body = { file_ids: files.map((f) => f.file_id), config: { ...cfg, mask_rules: cfg.mask_rules || "none" } };
      const r = await api.post<Job>("/analysis/start", body);
      setLocalJob(r.data.id); await refresh(); notify(`Analysis #${r.data.id} started`);
    } catch (e) { setErr(errMsg(e)); }
  };
  const num = (k: keyof Cfg, step = 1, hint?: string) => <label className="text-sm"><div className="text-dim mb-1">{k}{hint && <Hint text={hint} />}</div><input type="number" step={step} className="input w-full" value={cfg[k] as number} onChange={(e) => setCfg({ ...cfg, [k]: Number(e.target.value) })} /></label>;
  const chk = (k: keyof Cfg, hint: string) => <label className="text-sm flex items-center gap-2"><input type="checkbox" checked={cfg[k] as boolean} onChange={(e) => setCfg({ ...cfg, [k]: e.target.checked })} />{k}<Hint text={hint} /></label>;

  return (
    <div>
      <PageHeader title="Upload & Analysis" sub="TXT, LOG, CSV, JSON, JSONL · Apache, Nginx, Python, Java, syslog, HDFS, BGL and custom timestamped logs. Sensitive values are masked before storage." />
      <div className="grid lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-4">
          <div role="button" tabIndex={0} aria-label="Upload log files" onKeyDown={(e) => e.key === "Enter" && input.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={(e) => { e.preventDefault(); setDrag(false); upload(e.dataTransfer.files); }}
            onClick={() => input.current?.click()} className={`card border-dashed border-2 text-center py-10 cursor-pointer ${drag ? "border-accent bg-accent/5" : ""}`}>
            <UploadCloud className="mx-auto text-accent mb-3" size={34} /><div className="font-medium">Drop log files here or click to browse</div><div className="text-dim text-sm">Multiple files · max 50 MB each</div>
            <input ref={input} type="file" multiple hidden accept=".txt,.log,.csv,.json,.jsonl" onChange={(e) => upload(e.target.files)} />
            {pct > 0 && <div className="mt-4 h-1.5 bg-bg rounded max-w-sm mx-auto" role="progressbar" aria-valuenow={pct}><div className="h-full bg-accent rounded" style={{ width: `${pct}%` }} /></div>}
          </div>
          {err && <ErrorBox msg={err} />}

          <div className="card"><div className="h-title">Datasets</div>
            {!datasets.data ? <Skeleton className="h-24" /> : (
              <div className="grid md:grid-cols-2 gap-2">{datasets.data.map((d) => (
                <div key={d.name} className="border border-line rounded-md p-3 flex flex-col gap-1.5">
                  <div className="flex items-center gap-2 flex-wrap"><b className="text-sm">{d.name}</b>{d.is_synthetic ? <Badge v="Synthetic demo" /> : <Badge v="Real data" />}</div>
                  <p className="text-xs text-dim">{d.description}</p>
                  <p className="text-xs text-dim">Format: {d.format} · Labels: {d.labels} · License: {d.license}</p>
                  <button className="btn-ghost !py-1 self-start" disabled={loading !== null} onClick={() => loadDataset(d.name)}><Database size={14} />{loading === d.name ? "Loading…" : d.loaded_file_id ? "Add again" : d.is_synthetic ? "Load" : "Download & load"}</button>
                </div>))}</div>)}</div>

          {files.map((f) => (
            <div key={f.file_id} className="card overflow-x-auto">
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm mb-3 items-center"><b>{f.filename}</b>{f.is_synthetic && <Badge v="Synthetic demo" />}
                <span className="text-dim">format <span className="text-ink">{f.preview?.detected_format}</span></span><span className="text-dim">encoding {f.preview?.encoding}</span>
                <span className="text-dim">{f.preview?.n_records.toLocaleString()} records</span><span className="text-dim">{f.preview?.invalid_lines} invalid lines</span>
                <span className="text-dim">timestamps parsed {Math.round((f.preview?.timestamp_parse_rate ?? 0) * 100)}%</span>{f.preview?.has_ground_truth && <span className="text-accent">ground-truth labels ✓</span>}
                <button className="ml-auto text-dim hover:text-ink" aria-label={`Remove ${f.filename}`} onClick={() => setFiles(files.filter((x) => x !== f))}><X size={14} /></button></div>
              {f.file_id && f.filename.toLowerCase().endsWith(".csv") && (
                <ColumnMapper fileId={f.file_id} onApplied={(preview) => setFiles((cur) => cur.map((x) => (x.file_id === f.file_id ? { ...x, preview } : x)))} />)}
              <table className="tbl"><thead><tr><th>Time</th><th>Level</th><th>Service</th><th>Message</th></tr></thead>
                <tbody>{f.preview?.rows.slice(0, 8).map((p) => <tr key={p.line_no}><td className="mono text-dim whitespace-nowrap">{p.timestamp ?? "—"}</td><td className="mono">{p.level}</td><td className="text-dim">{p.service ?? "—"}</td><td className="mono truncate max-w-md">{p.message}</td></tr>)}</tbody></table>
            </div>))}
        </div>

        <div className="space-y-4">
          <div className="card space-y-3"><div className="h-title">Analysis configuration</div>
            <label className="text-sm block"><div className="text-dim mb-1">Feature representation<Hint text="TF-IDF is lexical; embeddings are semantic (Sentence-Transformers, downloaded on first use). Neither is always better: see Model Evaluation." /></div>
              <select className="input w-full" value={cfg.features} onChange={(e) => setCfg({ ...cfg, features: e.target.value })}><option value="tfidf">TF-IDF (word + char n-grams)</option><option value="embeddings">Sentence embeddings</option></select></label>
            <label className="text-sm block"><div className="text-dim mb-1">Clustering algorithm</div>
              <select className="input w-full" value={cfg.algorithm} onChange={(e) => setCfg({ ...cfg, algorithm: e.target.value })}><option value="dbscan">DBSCAN</option><option value="hdbscan">HDBSCAN</option><option value="kmeans">K-Means (baseline)</option></select></label>
            <div className="grid grid-cols-2 gap-2">{num("eps", 0.05, "DBSCAN radius; 0 = estimate from the k-distance knee")}{num("min_samples")}{num("min_cluster_size", 1, "HDBSCAN minimum cluster size")}{num("sim_threshold", 0.05, "Drain3 template similarity threshold")}{num("contamination", 0.01, "Expected anomaly share for Isolation Forest")}{num("z_threshold", 0.5, "Z-score threshold for spike detection")}</div>
            <div className="h-title !mt-4">Parsing & privacy</div>
            {chk("lowercase", "Lower-case message text before normalization")}{chk("keep_stack_trace", "Keep multi-line stack traces in normalized text")}{chk("run_evaluation", "Run the TF-IDF/embeddings × DBSCAN/HDBSCAN/K-Means comparison (slower)")}
            <label className="text-sm block"><div className="text-dim mb-1">Mask rules<Hint text="Comma list: email, phone, token, password, apikey, ip, identifier, or 'none'. Applied before anything is stored." /></div><input className="input w-full" value={cfg.mask_rules} onChange={(e) => setCfg({ ...cfg, mask_rules: e.target.value })} /></label>
            <button className="btn-primary w-full justify-center mt-2" disabled={!files.length || !!running} onClick={start}><Play size={16} /> Start analysis ({files.length} file{files.length !== 1 && "s"})</button></div>

          {job && (
            <div className="card"><div className="h-title">Progress · analysis #{job.id}</div><div className="text-sm mb-2">{job.stage}</div>
              <div className="h-2 bg-bg rounded" role="progressbar" aria-valuenow={Math.round(job.progress * 100)}><div className={`h-full rounded transition-all ${job.status === "failed" ? "bg-crit" : "bg-accent"}`} style={{ width: `${job.progress * 100}%` }} /></div>
              {job.error && <div className="text-crit text-sm mt-2">{job.error}</div>}
              {job.status === "completed" && (
                <div className="mt-3 text-sm space-y-2"><div className="text-dim">Results preview</div>
                  <div>{job.stats.total_logs?.toLocaleString()} logs · {job.stats.n_templates} templates · {job.stats.n_clusters} clusters · {job.stats.critical} critical · {job.stats.anomalies} anomalies</div>
                  {job.stats.invalid_lines > 0 && <div className="text-med">{job.stats.invalid_lines} invalid line(s) skipped</div>}
                  <Link to="/" onClick={() => setJobId(job.id)} className="btn-primary">Open dashboard</Link></div>)}
            </div>)}
        </div>
      </div>
    </div>
  );
}
