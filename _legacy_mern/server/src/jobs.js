// Background job runner: parses files, runs the pipeline, persists everything to MongoDB.
import fs from "fs/promises";
import { Job, UploadedFile, LogEntry, Template, Cluster, Anomaly, Insight, Evaluation, nextId } from "./models/index.js";
import { parseFiles, analyze } from "./pipeline/runner.js";

export async function runJob(jobId) {
  const job = await Job.findOne({ id: jobId });
  try {
    Object.assign(job, { status: "running", stage: "Parsing logs", progress: 0.05 }); await job.save();
    const files = await UploadedFile.find({ id: { $in: job.file_ids } });
    const payload = await Promise.all(files.map(async (f) => ({ name: f.filename, data: await fs.readFile(f.path) })));
    const { rows, meta } = parseFiles(payload);
    for (const f of files) { const m = meta.files.find((x) => x.name === f.filename); if (m) { f.encoding = m.encoding; f.detected_format = m.format; await f.save(); } }
    const progress = async (p, stage) => { job.progress = p; job.stage = stage; await job.save(); };
    await progress(0.15, "Normalizing");
    const res = await analyze(rows, job.config, progress, process.env);
    const base = await nextId("log", rows.length);
    for (let i = 0; i < rows.length; i += 5000)
      await LogEntry.insertMany(rows.slice(i, i + 5000).map((r, k) => ({ id: base + i + k, job_id: jobId, line_no: r.line_no, timestamp: r.timestamp, level: r.level,
        service: r.service, component: r.component, host: r.host, ip: r.ip, pid: r.pid, thread: r.thread, request_id: r.request_id, error_code: r.error_code,
        message: r.message.slice(0, 5000), normalized: r.normalized, template_id: r.template_id, cluster_id: r.cluster_id, is_anomaly: r.is_anomaly,
        anomaly_score: r.anomaly_score, label: r.label })), { ordered: false });
    await Template.insertMany(Object.entries(res.templates).map(([k, t]) => ({ job_id: jobId, template_key: +k, ...t })));
    await Cluster.insertMany(res.clusters.map(({ priority_factors, trend_ratio, ...c }) => ({ job_id: jobId, ...c, summary: { ...c.summary, priority_factors, trend_ratio } })));
    const aBase = await nextId("anomaly", res.anomalies.length || 1);
    await Anomaly.insertMany(res.anomalies.map((a, k) => ({ id: aBase + k, job_id: jobId, kind: a.kind, score: a.score, reason: a.reason, detected_at: a.detected_at,
      cluster_key: a.cluster_key, severity: a.severity, impact: a.impact, log_ids: a.log_idx.map((i) => base + i) })));
    const iBase = await nextId("insight", res.insights.length || 1);
    await Insight.insertMany(res.insights.map((x, k) => ({ id: iBase + k, job_id: jobId, ...x })));
    await Evaluation.create({ job_id: jobId, results: res.evaluation });
    Object.assign(job, { stats: { ...res.stats, invalid_lines: meta.invalid_lines, files: meta.files }, status: "completed", progress: 1, stage: "Done", finished_at: new Date() });
    await job.save();
  } catch (e) {
    console.error(e);
    Object.assign(job, { status: "failed", error: `${e.name}: ${e.message}`, stage: "Failed" }); await job.save();
  }
}
