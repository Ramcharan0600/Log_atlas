import PDFDocument from "pdfkit";
import { Job, Cluster, Anomaly, Insight } from "./models/index.js";

export async function collect(jobId) {
  const job = await Job.findOne({ id: jobId }).lean();
  const clusters = await Cluster.find({ job_id: jobId }).sort({ priority_score: -1 }).lean();
  const anomalies = await Anomaly.find({ job_id: jobId }).sort({ score: -1 }).lean();
  const insights = await Insight.find({ job_id: jobId }).lean();
  return {
    job: { id: job.id, status: job.status, created_at: job.created_at, config: job.config }, dataset_summary: job.stats, severity_distribution: job.stats.levels || {},
    clusters: clusters.map((c) => ({ id: c.cluster_key, name: c.name, size: c.size, priority: c.priority, severity: c.severity, first_seen: c.first_seen, last_seen: c.last_seen, template: c.template, summary: c.summary?.text, services: c.services })),
    anomalies: anomalies.map((a) => ({ kind: a.kind, score: a.score, reason: a.reason, detected_at: a.detected_at, cluster: a.cluster_key, severity: a.severity })),
    root_cause_hypotheses: insights.map((i) => ({ title: i.title, hypothesis: i.hypothesis, confidence: i.confidence, evidence: i.evidence, recommendations: i.recommendations, disclaimer: i.disclaimer })),
  };
}

const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
export function toCsv(d) {
  const head = ["cluster_id", "name", "size", "priority", "severity", "first_seen", "last_seen", "template", "summary"];
  return [head.join(","), ...d.clusters.map((c) => [c.id, c.name, c.size, c.priority, c.severity, c.first_seen?.toISOString?.() ?? "", c.last_seen?.toISOString?.() ?? "", c.template, c.summary].map(esc).join(","))].join("\n");
}

export function toPdf(d) {
  return new Promise((resolve) => {
    const doc = new PDFDocument({ margin: 48, size: "A4" }), chunks = [];
    doc.on("data", (c) => chunks.push(c)); doc.on("end", () => resolve(Buffer.concat(chunks)));
    const s = d.dataset_summary, h = (t) => doc.moveDown(0.8).font("Helvetica-Bold").fontSize(14).text(t).moveDown(0.3).font("Helvetica").fontSize(10);
    doc.font("Helvetica-Bold").fontSize(20).text(`LogMind AI — Analysis Report #${d.job.id}`);
    doc.font("Helvetica").fontSize(10).fillColor("#555").text(`Logs analyzed: ${s.total_logs} · Clusters: ${s.n_clusters} · Anomalies: ${s.anomalies} · Range: ${(s.time_range || []).join(" → ")}`).fillColor("#000");
    h("Severity distribution");
    Object.entries(d.severity_distribution).forEach(([k, v]) => doc.text(`${k.padEnd(10)} ${v}`));
    h("Top error clusters");
    d.clusters.slice(0, 20).forEach((c) => doc.text(`#${c.id}  [${c.priority}]  ${c.name}  — ${c.size} events`));
    h("Anomalies");
    d.anomalies.slice(0, 15).forEach((a) => doc.text(`• ${a.kind} (score ${a.score.toFixed(2)}): ${a.reason}`));
    h("Potential root causes (not confirmed)");
    d.root_cause_hypotheses.forEach((i) => {
      doc.moveDown(0.4).font("Helvetica-Bold").text(`${i.title} — ${i.confidence}`).font("Helvetica").text(i.hypothesis);
      i.evidence.forEach((e) => doc.text(`   • [${e.type}] ${e.text}`));
      doc.font("Helvetica-Oblique").text("Suggested investigation: " + i.recommendations.join("; ")).font("Helvetica");
      doc.fontSize(8).fillColor("#777").text(i.disclaimer).fillColor("#000").fontSize(10);
    });
    doc.end();
  });
}
