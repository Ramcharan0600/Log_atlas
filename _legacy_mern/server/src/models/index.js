import mongoose from "mongoose";
const { Schema, model } = mongoose;
const Mixed = Schema.Types.Mixed;

// Numeric ids keep URLs short and match the React client.
const Counter = model("Counter", new Schema({ _id: String, seq: Number }));
export async function nextId(name, n = 1) {
  const c = await Counter.findByIdAndUpdate(name, { $inc: { seq: n } }, { new: true, upsert: true });
  return c.seq - n + 1;
}

const opts = { versionKey: false };
export const UploadedFile = model("UploadedFile", new Schema({ id: { type: Number, index: true, unique: true }, filename: String, size_bytes: Number,
  encoding: String, detected_format: String, path: String, created_at: { type: Date, default: Date.now } }, opts));

export const Job = model("Job", new Schema({ id: { type: Number, index: true, unique: true }, file_ids: [Number], status: { type: String, default: "queued" },
  progress: { type: Number, default: 0 }, stage: { type: String, default: "" }, config: Mixed, error: String, stats: { type: Mixed, default: {} },
  created_at: { type: Date, default: Date.now }, finished_at: Date }, opts));

const logSchema = new Schema({ id: Number, job_id: Number, line_no: Number, timestamp: Date, level: String, service: String, component: String, host: String,
  ip: String, pid: String, thread: String, request_id: String, error_code: String, message: String, normalized: String, template_id: Number,
  cluster_id: Number, is_anomaly: Boolean, anomaly_score: Number, label: String }, opts);
logSchema.index({ job_id: 1, line_no: 1 }); logSchema.index({ job_id: 1, level: 1 }); logSchema.index({ job_id: 1, cluster_id: 1 });
logSchema.index({ job_id: 1, timestamp: 1 }); logSchema.index({ job_id: 1, id: 1 }); logSchema.index({ message: "text", normalized: "text" });
export const LogEntry = model("LogEntry", logSchema);

export const Template = model("Template", new Schema({ job_id: { type: Number, index: true }, template_key: Number, template: String, count: Number, params: [String] }, opts));

export const Cluster = model("Cluster", new Schema({ job_id: { type: Number, index: true }, cluster_key: Number, name: String, size: Number, severity: String,
  priority: String, priority_score: Number, first_seen: Date, last_seen: Date, keywords: [String], representatives: [String], template: String,
  services: Mixed, levels: Mixed, trend: Mixed, related: Mixed, is_anomalous: Boolean, summary: Mixed }, opts));

export const Anomaly = model("Anomaly", new Schema({ id: { type: Number, index: true }, job_id: { type: Number, index: true }, kind: String, score: Number,
  reason: String, detected_at: Date, cluster_key: Number, severity: String, log_ids: [Number], impact: String }, opts));

export const Insight = model("Insight", new Schema({ id: Number, job_id: { type: Number, index: true }, title: String, hypothesis: String, summary: String,
  evidence: Mixed, confidence: String, related_clusters: [Number], timeline: Mixed, recommendations: [String], disclaimer: String }, opts));

export const Evaluation = model("Evaluation", new Schema({ job_id: { type: Number, index: true }, results: Mixed }, opts));
