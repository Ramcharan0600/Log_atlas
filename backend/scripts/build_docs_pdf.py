"""Build docs/Atlas_Documentation.pdf from the project's own facts (ReportLab only, no network).

Usage:  python backend/scripts/build_docs_pdf.py
Screenshots are read from docs/images/ when present; missing images are skipped.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (BaseDocTemplate, Frame, Image, KeepTogether, PageBreak, PageTemplate, Paragraph, Preformatted, Spacer, Table,
                                TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
IMG = DOCS / "images"
OUT = DOCS / "Atlas_Documentation.pdf"

INK = colors.HexColor("#171612")
DIM = colors.HexColor("#6b675c")
LINE = colors.HexColor("#cfcabb")
PAPER = colors.HexColor("#f4f1e8")
ACCENT = colors.HexColor("#4f6b0f")      # olive, matches the light theme accent
ACCENT_BG = colors.HexColor("#c8f03a")   # signal lime, matches the dark theme accent

# Built-in PDF fonts have no arrows or comparison glyphs: translate them instead of printing black boxes.
_ASCII = {"→": "->", "←": "<-", "≥": ">=", "≤": "<=", "≈": "~", "Σ": "sum", "−": "-", "–": "-", "’": "'", "‘": "'", "“": '"', "”": '"', "…": "...", "✓": "yes"}


def clean(t: str) -> str:
    for k, v in _ASCII.items():
        t = t.replace(k, v)
    return t


S = {
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9.6, leading=14, textColor=INK, spaceAfter=6, alignment=TA_LEFT),
    "small": ParagraphStyle("small", fontName="Helvetica", fontSize=8.2, leading=11, textColor=DIM),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8.4, leading=11, textColor=INK),
    "cellb": ParagraphStyle("cellb", fontName="Helvetica-Bold", fontSize=8.4, leading=11, textColor=INK),
    "head": ParagraphStyle("head", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=colors.white),
    "h1": ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=INK, spaceBefore=4, spaceAfter=10, keepWithNext=1),
    "h1x": ParagraphStyle("h1x", fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=INK, spaceBefore=4, spaceAfter=10),
    "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=13, leading=17, textColor=ACCENT, spaceBefore=12, spaceAfter=5, keepWithNext=1),
    "h3": ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=10.5, leading=14, textColor=INK, spaceBefore=8, spaceAfter=3),
    "bullet": ParagraphStyle("bullet", fontName="Helvetica", fontSize=9.6, leading=14, textColor=INK, leftIndent=14, bulletIndent=2, spaceAfter=2),
    "caption": ParagraphStyle("caption", fontName="Helvetica-Oblique", fontSize=8, leading=10, textColor=DIM, spaceBefore=3, spaceAfter=10),
    "code": ParagraphStyle("code", fontName="Courier", fontSize=8, leading=10.2, textColor=INK, backColor=PAPER, borderColor=LINE, borderWidth=0.5,
                           borderPadding=6, spaceBefore=4, spaceAfter=10, leftIndent=6, rightIndent=6),
    "cover_t": ParagraphStyle("cover_t", fontName="Helvetica-Bold", fontSize=44, leading=48, textColor=INK),
    "cover_s": ParagraphStyle("cover_s", fontName="Helvetica", fontSize=15, leading=21, textColor=DIM),
    "toc1": ParagraphStyle("toc1", fontName="Helvetica-Bold", fontSize=10, leading=17, leftIndent=0),
    "toc2": ParagraphStyle("toc2", fontName="Helvetica", fontSize=9, leading=14, leftIndent=16, textColor=DIM),
}


def P(t, st="body"):
    return Paragraph(clean(t), S[st])


def H1(t):
    return Paragraph(clean(t), S["h1"])


def H2(t):
    return Paragraph(clean(t), S["h2"])


def H3(t):
    return Paragraph(clean(t), S["h3"])


def bullets(items):
    return [Paragraph(clean(i), S["bullet"], bulletText="-") for i in items]


def code(t):
    return Preformatted(clean(t.strip("\n")), S["code"])


def table(rows, widths, header=True, first_bold=False):
    data = []
    for r, row in enumerate(rows):
        cells = []
        for c, v in enumerate(row):
            if header and r == 0:
                cells.append(Paragraph(clean(str(v)).upper(), S["head"]))
            else:
                cells.append(Paragraph(clean(str(v)), S["cellb"] if first_bold and c == 0 else S["cell"]))
        data.append(cells)
    t = Table(data, colWidths=[w * cm for w in widths], repeatRows=1 if header else 0)
    st = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("TOPPADDING", (0, 0), (-1, -1), 4),
          ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5)]
    if header:
        st += [("BACKGROUND", (0, 0), (-1, 0), INK)]
    t.setStyle(TableStyle(st))
    return [t, Spacer(1, 8)]


def shot(name, caption, width_cm=17.0):
    path = IMG / name
    if not path.exists():
        return []
    w, h = ImageReader(str(path)).getSize()
    img = Image(str(path), width=width_cm * cm, height=width_cm * cm * h / w)
    box = Table([[img]], colWidths=[width_cm * cm])
    box.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, LINE), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                             ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return [KeepTogether([box, Paragraph(clean(caption), S["caption"])])]


def flow_diagram(stages):
    """Vertical pipeline: numbered boxes with a one-line description each."""
    rows = [[Paragraph(f"<b>{i:02d}</b>", ParagraphStyle("n", fontName="Helvetica-Bold", fontSize=10, textColor=ACCENT)),
             Paragraph(f"<b>{clean(name)}</b>", S["cell"]), Paragraph(clean(desc), S["cell"]), Paragraph(clean(where), S["small"])]
            for i, (name, desc, where) in enumerate(stages, 1)]
    t = Table(rows, colWidths=[1.0 * cm, 2.8 * cm, 7.6 * cm, 5.6 * cm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (-1, -1), 0.6, INK), ("LINEBELOW", (0, 0), (-1, -2), 0.4, LINE),
                           ("BACKGROUND", (0, 0), (0, -1), PAPER), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    return [t, Spacer(1, 8)]


class Doc(BaseDocTemplate):
    def __init__(self, path, **kw):
        super().__init__(path, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2.1 * cm, bottomMargin=2 * cm,
                         title="Atlas Documentation", author="Atlas project", subject="Log clustering, anomaly detection and root-cause triage", **kw)
        fr = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="f")
        self.addPageTemplates([PageTemplate(id="cover", frames=[fr], onPage=self._cover), PageTemplate(id="body", frames=[fr], onPage=self._page)])

    def _cover(self, c, d):
        c.saveState()
        c.setFillColor(ACCENT_BG)
        c.rect(0, A4[1] - 1.1 * cm, A4[0], 1.1 * cm, stroke=0, fill=1)
        c.restoreState()

    def _page(self, c, d):
        c.saveState()
        c.setStrokeColor(LINE)
        c.line(2 * cm, A4[1] - 1.5 * cm, A4[0] - 2 * cm, A4[1] - 1.5 * cm)
        c.setFont("Helvetica", 8)
        c.setFillColor(DIM)
        c.drawString(2 * cm, A4[1] - 1.2 * cm, "ATLAS  |  Log clustering, anomaly detection and root-cause triage")
        c.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Page {d.page}")
        c.drawString(2 * cm, 1.2 * cm, "Atlas documentation")
        c.restoreState()

    def afterFlowable(self, fl):
        if isinstance(fl, Paragraph):
            n = fl.style.name
            if n in ("h1", "h2"):
                key = f"h{self.seq.nextf('toc')}"
                self.canv.bookmarkPage(key)
                self.notify("TOCEntry", (0 if n == "h1" else 1, fl.getPlainText(), self.page, key))


def experiments_table():
    """Drain3 vs regex-only grouping accuracy per dataset, read straight from docs/experiments_results.json."""
    p = DOCS / "experiments_results.json"
    if not p.exists():
        return []
    try:
        datasets = json.loads(p.read_text(encoding="utf-8"))["datasets"]
    except Exception:  # noqa: BLE001 - the table is optional
        return []
    rows = [["Dataset", "Drain3 grouping accuracy", "Regex-only grouping accuracy"]]
    for name, d in datasets.items():
        m = (d.get("evaluation") or {}).get("template_methods") or {}
        a, b = (m.get("drain3") or {}).get("grouping_accuracy"), (m.get("regex_only") or {}).get("grouping_accuracy")
        if a is not None and b is not None:
            rows.append([name, f"{a:.3f}", f"{b:.3f}"])
    return table(rows, [6.5, 5.2, 5.3]) if len(rows) > 1 else []


def build():
    story = []
    # ------------------------------------------------------------------ cover
    story += [Spacer(1, 5.2 * cm), P("LOG INTELLIGENCE, DOCUMENTED", "small"), Spacer(1, 6), Paragraph("Atlas", S["cover_t"]), Spacer(1, 10),
              Paragraph("Log clustering, anomaly detection and root-cause triage", S["cover_s"]), Spacer(1, 1.2 * cm)]
    story += table([["Document", "Project documentation"], ["Generated", date.today().isoformat()], ["Backend", "Python, FastAPI, scikit-learn, Drain3, PostgreSQL"],
                    ["Frontend", "React, TypeScript, Vite, Tailwind CSS, Recharts"]], [3.2, 13.8], header=False, first_bold=True)
    story += [Spacer(1, 1.0 * cm), P("Atlas reads application and server logs, groups thousands of similar error lines into a few clusters, flags unusual behaviour, "
                                      "ranks everything by priority and proposes evidence-backed root-cause hypotheses that are always labelled as unconfirmed.")]
    from reportlab.platypus.doctemplate import NextPageTemplate
    story += [NextPageTemplate("body"), PageBreak()]

    toc = TableOfContents()
    toc.levelStyles = [S["toc1"], S["toc2"]]
    story += [Paragraph("Contents", S["h1x"]), toc, PageBreak()]

    # ------------------------------------------------------------------ 1 introduction
    story += [H1("1. Introduction"),
              P("A production system can write millions of log lines a day. When something breaks, the useful signal is buried in repetition: the same "
                "error with a different order number, user id or timestamp, thousands of times. Atlas turns that pile into something a person can act on."),
              H2("1.1 What Atlas does"),
              *bullets(["Groups similar log messages into clusters, so thousands of lines become a short list of distinct problems.",
                        "Detects anomalies: sudden error spikes, brand-new error patterns, rare messages and unusual components.",
                        "Ranks clusters as Critical, High, Medium or Low with a scoring formula whose factors are visible.",
                        "Proposes potential root causes with the evidence behind them, and suggests what to investigate next.",
                        "Shows everything in an interactive dashboard and exports PDF, CSV and JSON reports.",
                        "Stores all results in PostgreSQL (or SQLite), so they can be queried directly, for example from pgAdmin."]),
              H2("1.2 Who it is for"),
              P("Engineers on call who need a fast first read of an incident, students and researchers comparing clustering and anomaly-detection methods "
                "on real log data, and teams who want a transparent, offline-capable log triage tool instead of a black box."),
              H2("1.3 Design principles"),
              *bullets(["Honesty first. Observed facts, statistical findings and model predictions are labelled separately in the interface.",
                        "Root causes are always potential and unconfirmed. The evidence label (Strong, Moderate, Limited) counts independent signals and is not a probability.",
                        "Priority is a heuristic, and its factor breakdown is shown for every cluster.",
                        "Synthetic demo data is always flagged in the UI, in job records and in reports.",
                        "Every metric comes from an executed run on the selected data. Nothing is hard-coded.",
                        "Privacy by default: sensitive values are masked before they are written to the database.",
                        "Works without any API key or internet connection. An optional LLM can rewrite summaries but cannot introduce numbers that are not in the facts."])]
    story += shot("overview.jpg", "Figure 1. The Overview page: counts, volume timeline, severity split, top clusters and recent anomalies.")
    story += [PageBreak()]

    # ------------------------------------------------------------------ 2 architecture
    story += [H1("2. System overview"),
              P("Atlas is a single-page React application talking to a FastAPI backend. Analyses run as background jobs. Progress and results are written to the "
                "database, and the interface polls for status."),
              H2("2.1 Technology stack"),
              *table([["Layer", "Technology"],
                      ["Frontend", "React 18, TypeScript, Vite, Tailwind CSS, Recharts, React Router"],
                      ["Backend", "Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic"],
                      ["ML and NLP", "scikit-learn (DBSCAN, HDBSCAN, K-Means, Isolation Forest), Drain3, sentence-transformers, pandas, NumPy, SciPy"],
                      ["Database", "PostgreSQL (recommended) or SQLite for quick local runs"],
                      ["Reports", "ReportLab (PDF), CSV and JSON exports"],
                      ["Packaging", "Docker Compose (PostgreSQL, backend, nginx-served frontend)"]], [3.2, 13.8], first_bold=True),
              H2("2.2 Processing pipeline"),
              P("Each stage lives in its own package under <font face='Courier'>backend/app/pipelines</font>."),
              *flow_diagram([
                  ("Ingestion", "Validates type and size, detects encoding, merges multi-line stack traces, counts invalid lines.", "pipelines/ingestion/reader.py"),
                  ("Column map", "CSV only: applies the user-chosen mapping from CSV headers to log fields.", "reader.py, uploaded_files.column_map"),
                  ("Parsing", "Regex formats for Apache/Nginx, Python, Java, syslog, HDFS, BGL, HealthApp, bracketed service logs; structured CSV and JSON.", "pipelines/parsing/parser.py"),
                  ("Masking", "Masks emails, phones, tokens, passwords, API keys (optionally IPs and identifiers) before storage.", "pipelines/preprocessing"),
                  ("Normalization", "Replaces variable parts with placeholders such as IP, UUID, TIME, PATH, ID, NUM.", "preprocessing/normalizer.py"),
                  ("Templates", "Drain3 parse tree, plus a regex-only baseline for comparison.", "pipelines/templates/miner.py"),
                  ("Features", "TF-IDF (word and character n-grams reduced by SVD) or Sentence-Transformer embeddings (cached).", "pipelines/features/extractors.py"),
                  ("Clustering", "DBSCAN, HDBSCAN or K-Means on unique messages; noise re-attached to template groups.", "pipelines/clustering/engine.py"),
                  ("Anomalies", "Isolation Forest, rolling z-score, per-cluster spikes, new and rare patterns, error-ratio shift, component outliers.", "pipelines/anomaly_detection"),
                  ("Analysis", "Per-cluster statistics, trend, related clusters, priority score.", "services/analysis.py"),
                  ("Root cause", "Evidence collection, temporal precedence, hypothesis, evidence level, investigation steps.", "pipelines/root_cause"),
                  ("Summaries", "Rule-based text, optional LLM rewrite guarded against invented numbers.", "pipelines/summarization"),
                  ("Evaluation", "Supervised and unsupervised metrics, configuration grid, runtime and memory.", "pipelines/evaluation"),
                  ("Storage and API", "SQLAlchemy models, Alembic migrations, FastAPI routes feeding the dashboard and reports.", "models, api/routes.py")]),
              H2("2.3 Key design decisions"),
              *bullets(["Python backend, because the ML stack (scikit-learn, Drain3, sentence-transformers) lives there. The earlier Node prototype has been removed.",
                        "Clustering runs on unique normalized messages (frequency-weighted for DBSCAN and K-Means). Logs are very repetitive, so this is the main scalability lever; about 10 to 14 thousand logs per second were measured on synthetic data.",
                        "Both feature types produce dense L2-normalised vectors, so cosine and euclidean distance agree and one clustering code path serves both.",
                        "Algorithm noise is reported (raw noise ratio) and then re-attached to the log's Drain template group so every log has a cluster. Evaluation reports both views.",
                        "Jobs run in an in-process thread pool. Status and progress are persisted in analysis_jobs and polled by the UI. Stale jobs are failed on restart.",
                        "Log, template and cluster rows keep job-local ids plus global primary keys; the API exposes the cluster primary keys."])]
    story += [PageBreak()]

    # ------------------------------------------------------------------ 3 methodology
    story += [H1("3. Methodology"),
              H2("3.1 Normalization and masking"),
              P("Masking runs first, so no raw secrets are stored. Normalization then replaces variable fields with typed placeholders in a fixed order (UUID, URL, "
                "IP and port, timestamps, hex, paths, ports, measures, user ids, long numbers, numbers) while preserving meaningful words such as timeout, failed or exception."),
              H2("3.2 Template mining"),
              P("Drain3 builds a parse tree (depth 4, default similarity threshold 0.5). Template text is read after the full pass, because templates generalise as more lines "
                "arrive. A regex-normalized baseline is kept for comparison. The metric is the Loghub grouping accuracy."),
              H2("3.3 Feature extraction"),
              *bullets(["TF-IDF: word 1 to 2-grams (placeholder-aware token pattern) plus character 3 to 5-grams, sublinear term frequency, L2-normalised and reduced to at most 100 dimensions with truncated SVD.",
                        "Embeddings: all-MiniLM-L6-v2, batch size 64, normalised and cached on disk by content hash. If the model cannot load, an LSA character n-gram fallback is used and flagged as lsa-fallback in the results."]),
              H2("3.4 Clustering"),
              P("Clustering runs on unique normalized messages. DBSCAN uses frequency sample weights and takes eps from the k-distance knee (clamped between 0.05 and 0.9) unless "
                "given. HDBSCAN cannot weight points, so its minimum cluster size shrinks for small unique sets. The K-Means baseline uses k equal to the number of Drain "
                "templates (at most 50), which makes it an informed baseline rather than a blind one. Cluster names are the title-cased words of the dominant template, with keywords as "
                "fallback. Related clusters are found by centroid cosine similarity above 0.3."),
              H2("3.5 Anomaly detection"),
              *bullets(["Isolation Forest on 24 feature dimensions plus template rarity, severity and hour of day; contamination is configurable.",
                        "Rolling z-score over the preceding 12 buckets at 1 minute, 5 minutes and 1 hour for errors, per cluster (5 minutes) and error ratio (15 minutes).",
                        "New patterns (first seen in the second half of the window), rare templates and component error-rate outliers (z above 2).",
                        "Every anomaly stores a human-readable reason. Series longer than 20,000 buckets are skipped, for example mixed-year timestamps."]),
              H2("3.6 Priority score"),
              P("The score is 100 times the weighted sum of six factors: severity 0.35, frequency 0.15, anomaly 0.20, trend 0.10, recency 0.10 and impact (share of services) 0.10. "
                "Critical needs a score of at least 70 (or FATAL with at least 55), High at least 50 or FATAL, Medium at least 30, otherwise Low. This is a transparent "
                "heuristic and has not been validated against operator judgement. The interface shows the factor breakdown."),
              H2("3.7 Root-cause hypotheses"),
              P("For clusters where at least 20 percent of events are ERROR or FATAL, a category is chosen from a keyword knowledge base (template first, then representative messages). "
                "Evidence is listed and typed as observed fact, statistical finding or model prediction. Clusters that started up to 10 minutes earlier are shown as possible upstream "
                "triggers, with temporal order only. Evidence strength counts independent signals (volume of at least 20, rising trend, several services, each anomaly, a predecessor): "
                "four or more is Strong, two or more Moderate, otherwise Limited. This is deliberately not a probability."),
              H2("3.8 Summaries"),
              P("Summaries are rule-based from the statistics. When an LLM is configured it receives a JSON fact sheet only, and its output is discarded if it contains numbers that are "
                "not in the facts."),
              H2("3.9 Evaluation"),
              *bullets(["Supervised clustering: ARI, NMI, homogeneity, completeness and V-measure. Noise points count as singletons, so noise is penalised.",
                        "Unsupervised clustering: silhouette (cosine, non-noise, at most 5,000 points), Davies-Bouldin, Calinski-Harabasz. These assume convex clusters and ignore noise, so they are weak for density-based methods.",
                        "Anomalies: precision, recall and F1 at a threshold equal to the labelled positive rate, ROC-AUC and PR-AUC, with template-rarity and severity-only baselines.",
                        "Runtime via perf_counter and peak memory via tracemalloc."])]
    story += [PageBreak()]

    # ------------------------------------------------------------------ 4 data model
    story += [H1("4. Data model"),
              P("Ten tables. With PostgreSQL the schema is managed by Alembic (<font face='Courier'>alembic upgrade head</font>); with SQLite the tables are created at startup. "
                "Child tables reference <font face='Courier'>analysis_jobs</font> with ON DELETE CASCADE, so deleting a job removes its results."),
              *table([["Table", "Purpose", "Key columns"],
                      ["uploaded_files", "Every stored input file", "file_id, filename, stored_path, size_bytes, encoding, detected_format, dataset_name, is_synthetic, labels_path, column_map, uploaded_at"],
                      ["analysis_jobs", "One row per analysis run", "job_id, filename, status, progress, stage, error, total_logs, file_ids, configuration, stats, created_at, processing_started, processing_completed"],
                      ["logs", "Every parsed log line", "log_id, job_id, line_no, timestamp, severity, service, component, host, ip, request_id, original_message, normalized_message, template_id, cluster_id, anomaly_flag, anomaly_score"],
                      ["log_templates", "Mined templates", "template_id, job_id, local_id, template_text, occurrence_count, meta"],
                      ["clusters", "Named clusters", "cluster_id, job_id, local_id, cluster_name, cluster_size, severity, priority, priority_score, first_seen, last_seen, is_anomalous, summary, details"],
                      ["anomalies", "Detected anomalies", "anomaly_id, job_id, log_id, cluster_id, kind, anomaly_score, detection_reason, timestamp, severity, impact, log_ids"],
                      ["insights", "Root-cause hypotheses", "insight_id, job_id, cluster_id, title, hypothesis, summary, evidence, suspected_causes, recommended_actions, confidence_level, timeline"],
                      ["model_experiments", "Stored evaluation runs", "experiment_id, job_id, kind, algorithm, feature_method, parameters, metrics, execution_time"],
                      ["reports", "Generated report records", "report_id, job_id, format, created_at, size_bytes"],
                      ["users", "Reserved for multi-user use", "user_id, username, email, password_hash (authentication is not enforced yet)"]], [3.2, 4.0, 9.8], first_bold=True),
              P("Indexes cover the common filters: (job, cluster), (job, severity), (job, timestamp) and (job, service) on logs, priority on clusters, and status on analysis_jobs. "
                "Migrations: 0001 initial schema and 0002 adds uploaded_files.column_map.", "small")]

    # ------------------------------------------------------------------ 5 API
    story += [PageBreak(), H1("5. Backend API"),
              P("Interactive documentation is served at <font face='Courier'>/docs</font> (OpenAPI at <font face='Courier'>/openapi.json</font>). All routes are under "
                "<font face='Courier'>/api</font>. Errors are returned as {\"detail\": \"...\"}, and 5xx responses never contain a stack trace."),
              *table([["Method", "Path", "Purpose"],
                      ["GET", "/health", "liveness"],
                      ["GET", "/datasets", "catalog with real vs synthetic flag, licence, labels"],
                      ["POST", "/datasets/load", "copy or download a dataset, returns file_id and preview"],
                      ["POST", "/logs/upload", "validate and store files (multipart); per-file preview or error"],
                      ["GET", "/files/{id}/preview", "parsed preview, format, encoding, timestamp parse rate"],
                      ["GET", "/files/{id}/columns", "CSV: headers, sample rows, suggested and current mapping"],
                      ["PUT", "/files/{id}/column-map", "CSV: save column mapping (message required), returns new preview"],
                      ["POST", "/analysis/start", "start a background job (202)"],
                      ["GET", "/analysis", "job history, paginated"],
                      ["GET", "/analysis/{id}, /status", "job details and progress"],
                      ["DELETE", "/analysis/{id}", "remove job and its results"],
                      ["GET", "/analysis/{id}/summary, /timeline", "dashboard data"],
                      ["GET", "/analysis/{id}/logs", "filters: q, severity, service, cluster, anomaly, start, end, template, page, page_size"],
                      ["GET", "/analysis/{id}/facets, /templates", "filter options and mined templates"],
                      ["GET", "/analysis/{id}/clusters", "filters: priority, q, anomalous"],
                      ["GET", "/clusters/{id}, /clusters/{id}/logs", "cluster detail and member logs"],
                      ["GET", "/analysis/{id}/anomalies", "list (kind, min_score) and detail with logs"],
                      ["GET", "/analysis/{id}/insights", "root-cause hypotheses"],
                      ["GET", "/analysis/{id}/evaluation", "evaluation results and stored experiments"],
                      ["POST", "/analysis/{id}/evaluation/run", "run the feature x algorithm grid with chosen parameters"],
                      ["GET", "/analysis/{id}/export?format=", "report download: pdf, csv or json"]], [1.7, 6.3, 9.0]),
              H3("Analysis configuration"),
              P("Validated fields: features (tfidf or embeddings), algorithm (dbscan, hdbscan or kmeans), eps, min_samples, min_cluster_size, n_clusters, sim_threshold, "
                "contamination, z_threshold, lowercase, keep_stack_trace, run_evaluation, evaluation_max_unique, mask_rules and disabled_rules. The effective configuration, "
                "including the random seed, is stored with the job so a run can be reproduced.")]
    story += [PageBreak()]

    # ------------------------------------------------------------------ 6 frontend
    story += [H1("6. The dashboard"),
              P("The interface is a flat, report-style console with a dark and a light theme (toggle in the top bar). Pages are numbered in the sidebar. "
                "The Active analysis selector at the bottom of the sidebar chooses which run every page shows."),
              *table([["Page", "What you can do"],
                      ["Overview", "See counts, log volume and error timeline, error rate, anomaly timeline, severity split, top services, top clusters and recent anomalies."],
                      ["Log Explorer", "Search and filter logs by text, severity, service, cluster, anomaly flag and time range."],
                      ["Cluster Explorer", "Browse clusters by priority; open one to see its template, trend, priority explanation and member logs."],
                      ["Anomaly Center", "Review each anomaly with its score, reason, impact and the logs involved."],
                      ["Root-Cause Insights", "Read hypotheses with typed evidence, potential causes, suggested investigation steps and a timeline."],
                      ["Model Evaluation", "Compare TF-IDF and embeddings across DBSCAN, HDBSCAN and K-Means; run your own parameters."],
                      ["Upload and Analysis", "Upload files, map CSV columns, load datasets, configure and start an analysis, follow progress."],
                      ["Reports", "Download PDF, CSV or JSON reports."]], [4.2, 12.8], first_bold=True)]
    story += shot("clusters.jpg", "Figure 2. Cluster Explorer: clusters ranked by priority with severity, time range and services.")
    story += shot("anomalies.jpg", "Figure 3. Anomaly Center: every anomaly carries a reason and an impact statement.")
    story += shot("insights.jpg", "Figure 4. Root-Cause Insights: evidence is typed as observed fact, statistical finding or model prediction.")
    story += shot("evaluation.jpg", "Figure 5. Model Evaluation: every number is measured on the selected data in an executed run.")
    story += shot("upload.jpg", "Figure 6. Upload and Analysis, shown in the light theme.")
    story += [PageBreak()]

    # ------------------------------------------------------------------ 7 csv mapping
    story += [H1("7. Importing CSV with custom columns"),
              P("Standard headers such as timestamp, level, service and message are recognised automatically. If your CSV uses other names (for example Event Time, Sev, "
                "App Name and Description), use the column mapper."),
              *bullets(["Upload the CSV on the Upload and Analysis page.",
                        "Open Map CSV columns on the file card. Atlas suggests a mapping from the header names and shows sample rows.",
                        "Pick the column for each field: message (required), timestamp, level, service, component, host, ip, pid, thread, request_id, error_code and label.",
                        "Press Apply mapping. The preview is re-parsed with your choices, so you can check timestamps and severity before analysing.",
                        "Start the analysis. The mapping is stored in uploaded_files.column_map and applied by the reader when the job runs."]),
              P("A label column holding normal or anomaly is used as anomaly ground truth, which enables the supervised anomaly metrics on the Evaluation page. Any other label "
                "values are treated as cluster truth. The mapping is validated: unknown fields, unknown headers and a missing message column are rejected with a clear error."),
              H3("Example"),
              code("""
Event Time,Sev,App Name,Description,Is Bad
2026-11-01 10:00:01,ERROR,billing,Payment failed for order 1001 code 502,anomaly
2026-11-01 10:00:02,INFO,billing,Payment ok for order 1002,normal

mapping: timestamp=Event Time  level=Sev  service=App Name
         message=Description   label=Is Bad
"""),
              P("Before mapping, the timestamp parse rate of this file is 0 percent. After mapping it is 100 percent, and level, service and label are populated.")]

    # ------------------------------------------------------------------ 8 install
    story += [H1("8. Installation and setup"),
              H2("8.1 Requirements"),
              P("Python 3.11 or newer and Node 20 or newer. PostgreSQL is recommended but optional, because SQLite is the default."),
              H2("8.2 Run locally"),
              code("""
# backend: http://localhost:8000  (API docs at /docs)
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000

# frontend: http://localhost:5173  (proxies /api to :8000)
cd frontend
npm install
npm run dev
"""),
              P("Open Upload and Analysis, load a bundled synthetic dataset (works offline) or a Loghub dataset, and press Start analysis. No API key is needed."),
              H2("8.3 Use PostgreSQL and pgAdmin"),
              *bullets(["In pgAdmin, connect to your server. Expand it, right-click Databases, then Create, then Database, and create a database such as atlas.",
                        "Add the connection string to .env at the project root (this file is git-ignored). URL-encode special characters in the password, for example @ becomes %40.",
                        "Create the tables with alembic upgrade head, then start the backend.",
                        "Refresh atlas, Schemas, public, Tables in pgAdmin. New uploads and analyses made in the UI appear there."]),
              code("""
# .env
DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/atlas

cd backend
python -m alembic upgrade head
python -m uvicorn app.main:app --port 8000
"""),
              P("Useful pgAdmin tip: right-click a table and choose View/Edit Data, All Rows. The tables fill when an analysis runs, so they are empty until the first run."),
              H2("8.4 Docker Compose"),
              code("""
cp .env.example .env
docker compose up --build      # UI http://localhost:8080, API http://localhost:8000/docs
"""),
              P("Compose starts PostgreSQL 16, the backend (which runs alembic upgrade head first) and an nginx container serving the built frontend and proxying /api. "
                "The Docker build has not been exercised in the authoring environment."),
              H2("8.5 Split hosting"),
              *bullets(["Frontend on Vercel: root frontend/, build npm run build, output dist, environment variable VITE_API_URL pointing at the backend. vercel.json rewrites SPA routes.",
                        "Backend on any container host using backend/Dockerfile. Set DATABASE_URL to a managed PostgreSQL, CORS_ORIGINS to the frontend origin, and mount a persistent volume at /app/data.",
                        "Allow at least 2 GB of RAM for sentence-transformers, or set EMBEDDINGS_ENABLED=false.",
                        "Multi-instance deployments need a shared job queue and rate limiter, which are not provided."])]

    # ------------------------------------------------------------------ 9 config
    story += [H1("9. Configuration reference"),
              P("Settings are read from environment variables or a .env file (backend reads ../.env or backend/.env). Secrets must only ever be placed there."),
              *table([["Variable", "Default", "Meaning"],
                      ["DATABASE_URL", "local SQLite file", "postgresql+psycopg://user:password@host:5432/db for PostgreSQL"],
                      ["CORS_ORIGINS", "localhost dev ports", "comma list of allowed browser origins"],
                      ["MAX_UPLOAD_MB", "50", "upload size limit per file"],
                      ["RATE_LIMIT_PER_MINUTE", "600", "in-memory request limit; 0 disables it"],
                      ["MASK_RULES", "email,phone,token,password,apikey", "also ip and identifier, or none"],
                      ["EMBEDDING_MODEL", "all-MiniLM-L6-v2", "any Hugging Face sentence-embedding model id"],
                      ["EMBEDDINGS_ENABLED", "true", "false skips embeddings entirely"],
                      ["HF_TOKEN", "empty", "only needed for private or gated models"],
                      ["LLM_PROVIDER", "empty", "openai or gemini; empty runs fully offline"],
                      ["LLM_API_KEY, LLM_MODEL", "empty", "credentials and model for the optional summary rewrite"],
                      ["LOG_LEVEL", "INFO", "backend log level"],
                      ["VITE_API_URL", "proxied", "frontend build-time backend URL when hosted separately"],
                      ["POSTGRES_PASSWORD", "logmind", "used by docker-compose for the database container"]], [4.4, 4.4, 8.2], first_bold=True)]

    # ------------------------------------------------------------------ 10 datasets
    story += [H1("10. Datasets"),
              P("Real samples come from the public Loghub collection (research and academic use; see github.com/logpai/loghub). Synthetic data is bundled for offline demos and tests, "
                "and is always labelled Synthetic demo."),
              *table([["Dataset", "Lines", "Real?", "Labels", "Used for"],
                      ["Linux, Apache, HDFS, OpenSSH, HealthApp (Loghub 2k)", "2,000 each", "Real", "template id per line", "template extraction and clustering metrics"],
                      ["BGL (Loghub 2k)", "2,000", "Real", "template id and alert flag", "clustering and anomaly detection"],
                      ["Synthetic application, syslog, nginx", "6,000 / - / -", "Synthetic", "none", "demos, offline use"],
                      ["Synthetic labelled events and anomalies", "6,000", "Synthetic", "template or normal/anomaly", "tests and demos"]], [5.6, 2.2, 1.9, 3.3, 4.0]),
              P("Ground-truth labels are attached only if the raw-record count equals the label count, and synthetic data is never substituted silently. Full-size datasets "
                "(HDFS_v1 with 11M lines, BGL with 4.7M, Thunderbird with 211M) are not bundled; download one and upload the raw file.")]

    # ------------------------------------------------------------------ 11 testing
    story += [H1("11. Testing"),
              *table([["Suite", "Command", "Coverage"],
                      ["Backend", "cd backend && python -m pytest", "50 tests, about 15 s, offline with an isolated SQLite database. Covers file validation, encodings, multiline records, every parser format, normalization, masking, Drain3, features, all three clustering algorithms, anomaly metrics, priority, root-cause structure, LLM fallback, the full API workflow from upload to export and delete, SQL-wildcard safety, secret masking and CSV column mapping."],
                      ["Frontend", "cd frontend && npm test && npx tsc --noEmit", "Formatting utilities (vitest) and TypeScript type safety. UI flows are not covered by automated browser tests."]],
                    [2.4, 5.0, 9.6], first_bold=True),
              P("The tests never touch your configured database: they run against a temporary SQLite file.")]

    # ------------------------------------------------------------------ 12 experiments
    story += [H1("12. Experiments and findings"),
              P("Source: docs/experiments.md and docs/experiments_results.json, produced by backend/scripts/run_experiments.py on six real Loghub 2k samples (single run, fixed seeds, "
                "one machine). These are small samples; do not extrapolate to full-scale data."),
              *experiments_table(),
              *bullets(["Drain3 versus regex-only: Drain3 had higher grouping accuracy on Linux (0.685 vs 0.186), Apache (1.000 vs 0.582), OpenSSH (0.718 vs 0.336) and BGL (0.805 vs 0.333), and tied on HDFS (0.998). Regex-only is 30 to 50 times faster but fragments templates. HealthApp is low for both.",
                        "TF-IDF versus embeddings (DBSCAN): TF-IDF had the higher ARI on all six sets, for example HDFS 0.999 vs 0.107 and Apache 1.000 vs 0.538. Log messages are template-driven, so exact token overlap is a strong signal.",
                        "DBSCAN versus HDBSCAN: HDBSCAN labelled a large share of points as noise on several sets (BGL 0.567) and had lower ARI almost everywhere, so DBSCAN with a k-distance eps is the default.",
                        "K-Means with k from Drain is a strong baseline on several sets but needs k and cannot flag noise.",
                        "Anomalies on BGL: Isolation Forest ROC-AUC 0.779, template rarity 0.793, severity only 0.945. Here the alert flag correlates strongly with logged severity, and content-based unsupervised detection was weak.",
                        "Throughput: 6k to 96k synthetic logs at about 9 to 12 thousand logs per second with the evaluation grid disabled."]),
              P("Caveats: silhouette, Davies-Bouldin and Calinski-Harabasz are unreliable for density-based clusters; single run with no confidence intervals; 2,000-line samples.", "small")]

    # ------------------------------------------------------------------ 13 security
    story += [H1("13. Security and privacy"),
              *bullets(["Sensitive values (emails, phones, tokens, passwords, API keys, optionally IPs and identifiers) are masked before anything is stored.",
                        "Uploads are checked for extension and size, binary files are rejected, and filenames are sanitised so path tricks such as ../ are stripped.",
                        "Log search escapes SQL wildcards. All database access goes through SQLAlchemy parameters.",
                        "Server errors return a generic message; stack traces stay in server logs only.",
                        "Secrets (database URL, LLM key, Hugging Face token) are read only from the environment. .env is git-ignored.",
                        "The React frontend renders text, not HTML, so log content cannot inject markup.",
                        "A simple in-memory rate limit protects the API. Authentication is not implemented in this version."])]

    # ------------------------------------------------------------------ 14 limitations
    story += [H1("14. Limitations and future work"),
              *bullets(["Single-process job runner and in-memory rate limiter; a shared queue (for example Redis) would be needed to scale out.",
                        "No authentication or per-user data separation yet; the users table is reserved for that.",
                        "Priority weights are heuristic and not validated against operator judgement.",
                        "Evaluation used small samples and a single run per configuration.",
                        "The embedding model needs internet access the first time; an LSA fallback is used otherwise and is labelled in the results.",
                        "Full-size Loghub datasets need their label files attached manually.",
                        "Possible next steps: streaming ingestion, alert integrations, per-service baselines, user accounts and a feedback loop for priority tuning."])]

    # ------------------------------------------------------------------ 15 troubleshooting
    story += [H1("15. Troubleshooting"),
              *table([["Symptom", "Likely cause and fix"],
                      ["Connection refused to PostgreSQL", "Service not running, or wrong port. Check the Windows service or pg_isready, and the port in DATABASE_URL."],
                      ["password authentication failed", "Wrong password in DATABASE_URL. URL-encode special characters (@ becomes %40)."],
                      ["relation does not exist", "Tables were not created. Run python -m alembic upgrade head from the backend folder."],
                      ["Create Database dialog says Database cannot be empty", "Type the name in the Database field at the top of the General tab before saving."],
                      ["Embeddings fall back to LSA", "No internet or Hugging Face is blocked. The Evaluation page shows a warning. Set EMBEDDINGS_ENABLED=false to skip them."],
                      ["Upload rejected", "Check the extension (txt, log, csv, json, jsonl), the size limit (MAX_UPLOAD_MB) and that the file is text."],
                      ["Styles look old after a config change", "Restart the Vite dev server; it does not reload tailwind.config.js."],
                      ["npm install fails with ENOSPC on Windows", "The drive is full or a shim write failed. Free space or install node_modules on another drive and junction it."]],
                    [5.6, 11.4], first_bold=True)]

    # ------------------------------------------------------------------ appendix
    story += [H1("Appendix A. Project layout"),
              code("""
backend/app/{api,core,database,models,schemas,services,utils}
backend/app/pipelines/{ingestion,parsing,preprocessing,templates,features,
                       clustering,anomaly_detection,root_cause,
                       summarization,evaluation}
backend/{tests,migrations,scripts,sample_data}
frontend/src/{components,pages,layouts,charts,services,hooks,types,utils}
docs/   architecture, methodology, dataset, API, testing, deployment,
        experiments, images, this PDF
"""),
              P("To regenerate this document after changes: python backend/scripts/build_docs_pdf.py", "small")]

    doc = Doc(str(OUT))
    doc.multiBuild(story)
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    build()
