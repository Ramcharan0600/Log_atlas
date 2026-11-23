// Express app (exported separately from index.js so tests can mount it).
import express from "express";
import cors from "cors";
import multer from "multer";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { UploadedFile, Job, LogEntry, Template, Cluster, Anomaly, Insight, Evaluation, nextId } from "./models/index.js";
import { validateFile, readRecords } from "./pipeline/ingestion.js";
import { parseLine, detectFormat } from "./pipeline/parser.js";
import { DEFAULT_CONFIG } from "./pipeline/runner.js";
import { runJob } from "./jobs.js";
import { collect, toCsv, toPdf } from "./reports.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SAMPLE_DIR = path.join(__dirname, "..", "sample_data");
const UPLOAD_DIR = process.env.UPLOAD_DIR || path.join(__dirname, "..", "uploads");
const MAX_MB = +(process.env.MAX_UPLOAD_MB || 50);
fs.mkdirSync(UPLOAD_DIR, { recursive: true });

export const app = express();
app.use(cors({ origin: (process.env.CORS_ORIGINS || "http://localhost:5173").split(",") }));
app.use(express.json({ limit: "2mb" }));
const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: MAX_MB * 1024 * 1024 } });
const wrap = (fn) => (req, res, next) => Promise.resolve(fn(req, res, next)).catch(next);
const r = express.Router();

r.get("/health", (_, res) => res.json({ status: "ok", time: new Date() }));

async function saveFile(name, data) {
  validateFile(name, data.length, MAX_MB);
  const id = await nextId("file"), p = path.join(UPLOAD_DIR, `${id}_${path.basename(name)}`);
  fs.writeFileSync(p, data);
  return UploadedFile.create({ id, filename: name, size_bytes: data.length, path: p });
}
function preview(f, data, n = 15) {
  const { recs, encoding, invalid } = readRecords(data, f.filename);
  const format = recs[0]?.fields ? "structured" : detectFormat(recs.slice(0, 200).map((x) => x.text));
  return { file_id: f.id, filename: f.filename, size_bytes: f.size_bytes, encoding, format, records: recs.length, invalid_lines: invalid,
    preview: recs.slice(0, n).map((x) => { const p = parseLine(x.lineNo, x.text, x.fields, format); return { ...p, timestamp: p.timestamp?.toISOString() ?? null }; }) };
}

r.post("/upload", upload.array("files"), wrap(async (req, res) => {
  const out = [];
  for (const f of req.files || []) {
    try { const doc = await saveFile(f.originalname, f.buffer); out.push(preview(doc, f.buffer)); }
    catch (e) { return res.status(400).json({ detail: `${f.originalname}: ${e.message}` }); }
  }
  res.json(out);
}));
r.get("/samples", (_, res) => res.json(fs.readdirSync(SAMPLE_DIR).filter((n) => !n.startsWith(".") && !n.endsWith(".js")).sort().map((name) => ({ name, size_bytes: fs.statSync(path.join(SAMPLE_DIR, name)).size }))));
r.post("/samples/:name", wrap(async (req, res) => {
  const p = path.join(SAMPLE_DIR, path.basename(req.params.name));
  if (!fs.existsSync(p)) return res.status(404).json({ detail: "Sample not found" });
  const data = fs.readFileSync(p); res.json(preview(await saveFile(req.params.name, data), data));
}));

r.get("/config/defaults", (_, res) => res.json(DEFAULT_CONFIG));
const jobDict = (j) => ({ id: j.id, status: j.status, progress: j.progress, stage: j.stage, error: j.error, config: j.config, stats: j.stats, file_ids: j.file_ids, created_at: j.created_at, finished_at: j.finished_at });
const getJob = async (req, res) => { const j = await Job.findOne({ id: +req.params.id }); if (!j) res.status(404).json({ detail: "Job not found" }); return j; };

r.post("/jobs", wrap(async (req, res) => {
  const { file_ids = [], config = {} } = req.body;
  if (!file_ids.length || (await UploadedFile.countDocuments({ id: { $in: file_ids } })) !== file_ids.length) return res.status(400).json({ detail: "Unknown file id" });
  const job = await Job.create({ id: await nextId("job"), file_ids, config: { ...DEFAULT_CONFIG, ...config } });
  setImmediate(() => runJob(job.id));
  res.json(jobDict(job));
}));
r.get("/jobs", wrap(async (_, res) => res.json((await Job.find().sort({ id: -1 }).limit(50)).map(jobDict))));
r.get("/jobs/:id", wrap(async (req, res) => { const j = await getJob(req, res); if (j) res.json(jobDict(j)); }));
r.delete("/jobs/:id", wrap(async (req, res) => {
  const id = +req.params.id;
  await Promise.all([LogEntry, Template, Cluster, Anomaly, Insight, Evaluation].map((M) => M.deleteMany({ job_id: id })));
  await Job.deleteOne({ id }); res.json({ deleted: id });
}));

const brief = (c) => ({ id: c.cluster_key, name: c.name, size: c.size, severity: c.severity, priority: c.priority, priority_score: c.priority_score, first_seen: c.first_seen, last_seen: c.last_seen, is_anomalous: c.is_anomalous, keywords: c.keywords, services: c.services });
const anomDict = (a) => ({ id: a.id, kind: a.kind, score: a.score, reason: a.reason, detected_at: a.detected_at, cluster: a.cluster_key, severity: a.severity, impact: a.impact, n_logs: a.log_ids.length });

r.get("/jobs/:id/overview", wrap(async (req, res) => {
  const job = await getJob(req, res); if (!job) return;
  const id = job.id, total = await LogEntry.countDocuments({ job_id: id });
  const [range] = await LogEntry.aggregate([{ $match: { job_id: id, timestamp: { $ne: null } } }, { $group: { _id: null, min: { $min: "$timestamp" }, max: { $max: "$timestamp" } } }]);
  let timeline = [];
  if (range) {
    const h = (range.max - range.min) / 3600e3, unit = h <= 12 ? "minute" : "hour", binSize = h <= 12 ? 5 : 1;
    timeline = (await LogEntry.aggregate([{ $match: { job_id: id, timestamp: { $ne: null } } },
      { $group: { _id: { $dateTrunc: { date: "$timestamp", unit, binSize } }, total: { $sum: 1 }, errors: { $sum: { $cond: [{ $in: ["$level", ["ERROR", "FATAL"]] }, 1, 0] } }, anomalies: { $sum: { $cond: ["$is_anomaly", 1, 0] } } } },
      { $sort: { _id: 1 } }])).map((b) => ({ t: b._id.toISOString().slice(0, 16).replace("T", " "), total: b.total, errors: b.errors, anomalies: b.anomalies, error_rate: Math.round((b.errors / b.total) * 1e4) / 100 }));
  }
  const top_services = (await LogEntry.aggregate([{ $match: { job_id: id, level: { $in: ["ERROR", "FATAL"] } } }, { $group: { _id: "$service", errors: { $sum: 1 } } }, { $sort: { errors: -1 } }, { $limit: 8 }])).map((x) => ({ service: x._id || "unknown", errors: x.errors }));
  res.json({ job: jobDict(job), stats: job.stats, timeline, total_logs: total, top_services,
    top_clusters: (await Cluster.find({ job_id: id }).sort({ priority_score: -1 }).limit(10)).map(brief),
    recent_anomalies: (await Anomaly.find({ job_id: id }).sort({ score: -1 }).limit(8)).map(anomDict) });
}));

const escRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const logDict = (l, tpl) => ({ ...l, template: tpl[l.template_id] || "" });
const tplMap = async (id) => Object.fromEntries((await Template.find({ job_id: id }).lean()).map((t) => [t.template_key, t.template]));

r.get("/jobs/:id/logs", wrap(async (req, res) => {
  const id = +req.params.id, q = req.query, f = { job_id: id };
  if (q.q) f.$or = [{ message: { $regex: escRe(q.q), $options: "i" } }, { normalized: { $regex: escRe(q.q), $options: "i" } }];
  if (q.level) f.level = { $in: q.level.split(",") };
  if (q.service) f.service = q.service;
  if (q.cluster !== undefined && q.cluster !== "") f.cluster_id = +q.cluster;
  if (q.anomaly === "true" || q.anomaly === "false") f.is_anomaly = q.anomaly === "true";
  if (q.start || q.end) f.timestamp = { ...(q.start && { $gte: new Date(q.start) }), ...(q.end && { $lte: new Date(q.end) }) };
  const page = Math.max(1, +q.page || 1), size = Math.min(500, +q.page_size || 50);
  const [total, items, tpl] = await Promise.all([LogEntry.countDocuments(f), LogEntry.find(f, { _id: 0 }).sort({ line_no: 1 }).skip((page - 1) * size).limit(size).lean(), tplMap(id)]);
  res.json({ total, page, page_size: size, items: items.map((l) => logDict(l, tpl)) });
}));
r.get("/jobs/:id/facets", wrap(async (req, res) => {
  const id = +req.params.id;
  res.json({ services: (await LogEntry.distinct("service", { job_id: id })).filter(Boolean).sort(), levels: await LogEntry.distinct("level", { job_id: id }),
    clusters: (await Cluster.find({ job_id: id }).sort({ size: -1 }).limit(300)).map((c) => ({ id: c.cluster_key, name: c.name })) });
}));
r.get("/jobs/:id/templates", wrap(async (req, res) => res.json((await Template.find({ job_id: +req.params.id }).sort({ count: -1 }).limit(500).lean()).map((t) => ({ id: t.template_key, template: t.template, count: t.count, params: t.params })))));

r.get("/jobs/:id/clusters", wrap(async (req, res) => {
  const f = { job_id: +req.params.id };
  if (req.query.priority) f.priority = req.query.priority;
  if (req.query.q) f.$or = [{ name: { $regex: escRe(req.query.q), $options: "i" } }, { template: { $regex: escRe(req.query.q), $options: "i" } }];
  res.json((await Cluster.find(f).sort({ priority_score: -1 }).limit(500)).map(brief));
}));
r.get("/jobs/:id/clusters/:key", wrap(async (req, res) => {
  const id = +req.params.id, c = await Cluster.findOne({ job_id: id, cluster_key: +req.params.key });
  if (!c) return res.status(404).json({ detail: "Cluster not found" });
  const names = Object.fromEntries((await Cluster.find({ job_id: id, cluster_key: { $in: c.related.map((x) => x.cluster_key) } })).map((x) => [x.cluster_key, x.name]));
  res.json({ ...brief(c), representatives: c.representatives, template: c.template, levels: c.levels, trend: c.trend, summary: c.summary,
    related: c.related.map((x) => ({ ...x, name: names[x.cluster_key] || "" })), anomalies: (await Anomaly.find({ job_id: id, cluster_key: c.cluster_key })).map(anomDict) });
}));

r.get("/jobs/:id/anomalies", wrap(async (req, res) => res.json((await Anomaly.find({ job_id: +req.params.id }).sort({ score: -1 })).map(anomDict))));
r.get("/jobs/:id/anomalies/:aid/logs", wrap(async (req, res) => {
  const id = +req.params.id, a = await Anomaly.findOne({ id: +req.params.aid, job_id: id });
  if (!a) return res.status(404).json({ detail: "Not found" });
  const tpl = await tplMap(id);
  res.json((await LogEntry.find({ job_id: id, id: { $in: a.log_ids.slice(0, 100) } }, { _id: 0 }).lean()).map((l) => logDict(l, tpl)));
}));
r.get("/jobs/:id/insights", wrap(async (req, res) => res.json(await Insight.find({ job_id: +req.params.id }, { _id: 0 }).lean())));
r.get("/jobs/:id/evaluation", wrap(async (req, res) => res.json((await Evaluation.findOne({ job_id: +req.params.id }).lean())?.results || {})));

r.get("/jobs/:id/report.:fmt", wrap(async (req, res) => {
  const job = await getJob(req, res); if (!job) return;
  if (job.status !== "completed") return res.status(409).json({ detail: "Job not completed" });
  const d = await collect(job.id), fmt = req.params.fmt, name = `logmind_${job.id}`;
  if (fmt === "json") return res.attachment(`${name}.json`).type("application/json").send(JSON.stringify(d, null, 2));
  if (fmt === "csv") return res.attachment(`${name}_clusters.csv`).type("text/csv").send(toCsv(d));
  if (fmt === "pdf") return res.attachment(`${name}.pdf`).type("application/pdf").send(await toPdf(d));
  res.status(400).json({ detail: "fmt must be json, csv or pdf" });
}));

app.use("/api", r);
app.use((err, _req, res, _next) => { console.error(err); res.status(err.code === "LIMIT_FILE_SIZE" ? 400 : 500).json({ detail: err.message }); });
