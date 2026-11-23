"""Report generation (JSON / CSV / PDF) from persisted analysis results."""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime

from sqlalchemy import select

from app.models import AnalysisJob, Anomaly, Cluster, Insight

TRUTH_NOTE = "Observed facts and statistics come from the uploaded logs; hypotheses are potential, unconfirmed root causes."


def collect(db, job: AnalysisJob) -> dict:
    cl = db.scalars(select(Cluster).where(Cluster.job_id == job.job_id).order_by(Cluster.priority_score.desc())).all()
    an = db.scalars(select(Anomaly).where(Anomaly.job_id == job.job_id).order_by(Anomaly.anomaly_score.desc()).limit(200)).all()
    ins = db.scalars(select(Insight).where(Insight.job_id == job.job_id)).all()
    s = job.stats or {}
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z", "note": TRUTH_NOTE,
        "dataset": {"job_id": job.job_id, "filename": job.filename, "dataset_name": job.dataset_name, "synthetic_demo_data": job.is_synthetic, "total_logs": job.total_logs,
                    "time_range": s.get("time_range"), "levels": s.get("levels"), "n_templates": s.get("n_templates"), "configuration": job.configuration},
        "clusters": [{"id": c.cluster_id, "name": c.cluster_name, "size": c.cluster_size, "severity": c.severity, "priority": c.priority, "priority_score": c.priority_score,
                      "first_seen": c.first_seen.isoformat() if c.first_seen else None, "last_seen": c.last_seen.isoformat() if c.last_seen else None, "anomalous": c.is_anomalous,
                      "summary": c.summary, "template": c.details.get("template"), "services": list((c.details.get("services") or {}).keys()),
                      "priority_explanation": c.details.get("priority_explanation")} for c in cl],
        "anomalies": [{"id": a.anomaly_id, "kind": a.kind, "score": a.anomaly_score, "reason": a.detection_reason, "time": a.timestamp.isoformat() if a.timestamp else None,
                       "severity": a.severity, "impact": a.impact} for a in an],
        "insights": [{"title": i.title, "hypothesis": i.hypothesis, "evidence_level": i.confidence_level, "evidence": i.evidence, "recommended_actions": i.recommended_actions,
                      "disclaimer": i.disclaimer} for i in ins],
        "evaluation": {k: v for k, v in (s.get("evaluation") or {}).items() if k in ("final", "final_after_noise_attachment", "comparison", "anomaly", "template_methods", "timings_s")},
    }


def to_json(data: dict) -> bytes:
    return json.dumps(data, indent=2, default=str).encode()


def to_csv(data: dict) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["cluster_id", "name", "size", "severity", "priority", "priority_score", "first_seen", "last_seen", "anomalous", "services", "template", "summary"])
    for c in data["clusters"]:
        w.writerow([c["id"], c["name"], c["size"], c["severity"], c["priority"], c["priority_score"], c["first_seen"], c["last_seen"], c["anomalous"],
                    ";".join(c["services"]), c["template"], c["summary"]])
    return buf.getvalue().encode("utf-8-sig")


def to_pdf(data: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape as esc

    ss = getSampleStyleSheet()
    small = ss["BodyText"].clone("small", fontSize=8, leading=10)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=15 * mm, title="Atlas report")
    d = data["dataset"]
    el = [Paragraph("Atlas - Log Analysis Report", ss["Title"]), Paragraph(esc(f"Generated {data['generated_at']} | job #{d['job_id']} | {d['filename']}"), small)]
    if d["synthetic_demo_data"]:
        el.append(Paragraph("<b>Note:</b> this analysis used synthetic demo data.", small))
    el += [Spacer(1, 6), Paragraph(esc(data["note"]), small), Paragraph("Dataset summary", ss["Heading2"]),
           Paragraph(esc(f"Total logs: {d['total_logs']:,}; templates: {d['n_templates']}; clusters: {len(data['clusters'])}; anomalies: {len(data['anomalies'])}. "
                         f"Time range: {' to '.join(d['time_range'] or []) or 'n/a'}."), ss["BodyText"]),
           Paragraph(esc("Severity distribution: " + ", ".join(f"{k}={v}" for k, v in (d["levels"] or {}).items())), ss["BodyText"]), Paragraph("Error clusters", ss["Heading2"])]
    rows = [["Priority", "Cluster", "Size", "Severity", "First seen"]] + [[c["priority"], Paragraph(esc(c["name"]), small), c["size"], c["severity"], (c["first_seen"] or "")[:16]]
                                                                          for c in data["clusters"][:25]]
    t = Table(rows, colWidths=[22 * mm, 80 * mm, 18 * mm, 22 * mm, 36 * mm], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 8),
                           ("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    el += [t, Paragraph("Anomalies (top 15 by score)", ss["Heading2"])]
    for a in data["anomalies"][:15]:
        el.append(Paragraph(esc(f"[{a['kind']}] score {a['score']:.2f} {a['time'] or ''}: {a['reason']}"), small))
    el.append(Paragraph("Root-cause hypotheses (potential, unconfirmed)", ss["Heading2"]))
    for i in data["insights"]:
        el += [Paragraph(f"<b>{esc(i['title'])}</b> - {esc(i['evidence_level'])}", ss["BodyText"]), Paragraph(esc(i["hypothesis"]), small)]
        el += [Paragraph("- " + esc(f"[{e['type']}] {e['text']}"), small) for e in i["evidence"][:8]]
        el += [Paragraph("Suggested investigation: " + esc("; ".join(i["recommended_actions"][:5])), small), Spacer(1, 4)]
    doc.build(el)
    return buf.getvalue()
