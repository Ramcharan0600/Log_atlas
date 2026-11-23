from datetime import datetime

import numpy as np
import pytest

from app.pipelines.anomaly_detection.detectors import bucket_series, detect_all, zscore_spikes
from app.pipelines.clustering.engine import attach_noise_to_templates, run_clustering
from app.pipelines.evaluation.metrics import anomaly_metrics, clustering_metrics
from app.pipelines.features.extractors import embedding_features, tfidf_features
from app.pipelines.ingestion.reader import IngestionError, read_records, validate_file
from app.pipelines.parsing.parser import detect_format, parse_record, parse_timestamp
from app.pipelines.preprocessing.normalizer import mask_sensitive, normalize
from app.pipelines.root_cause.analyzer import build_insights, categorize
from app.pipelines.root_cause.priority import priority_label, priority_score
from app.pipelines.summarization.summarizer import llm_enhance, rule_summary
from app.pipelines.templates.miner import grouping_accuracy, mine_templates
from app.services.analysis import analyze
from app.services.jobs import parse_files


def rec(text, ext="log"):
    return read_records(text.encode(), f"x.{ext}")


# ---- ingestion / validation ------------------------------------------------------------------------
def test_validate_file_rules():
    validate_file("a.log", 10)
    for name, size in (("a.exe", 10), ("a.log", 0), ("a.log", 60 * 1024 * 1024)):
        with pytest.raises(IngestionError):
            validate_file(name, size)


def test_encoding_detection_and_binary_rejection():
    assert read_records("2024-01-01 10:00:00 ERROR héllo".encode("utf-16"), "a.log").encoding == "utf-16"
    assert read_records("caf\xe9 ERROR x".encode("latin-1"), "a.log").records
    with pytest.raises(IngestionError):
        read_records(b"\x00\x01\x02binary", "a.log")


def test_multiline_stack_trace_merged():
    r = rec("2024-01-01 10:00:00 ERROR boom\n  at com.x.Y(Y.java:1)\n  at com.x.Z(Z.java:2)\n2024-01-01 10:00:01 INFO ok\n")
    assert len(r.records) == 2 and "Y.java" in r.records[0].text


def test_invalid_jsonl_lines_counted():
    r = read_records(b'{"message":"a"}\nnot json\n{"message":"b"}\n', "a.jsonl")
    assert len(r.records) == 2 and r.invalid_lines == 1


def test_csv_and_json_array():
    assert rec("level,message\nERROR,disk full\n", "csv").records[0].text == "disk full"
    assert len(rec('[{"msg":"a"},{"msg":"b"}]', "json").records) == 2
    with pytest.raises(IngestionError):
        rec("[not json", "json")


# ---- parsing -----------------------------------------------------------------------------------------
@pytest.mark.parametrize("line,fmt,level,service", [
    ('10.0.0.1 - - [14/Mar/2026:12:00:00 +0000] "GET /a HTTP/1.1" 503 12 "-" "curl"', "apache_nginx_access", "ERROR", "web"),
    ("2026-03-14 12:00:00,123 - app.db - ERROR - connection lost", "python_logging", "ERROR", None),
    ("2026-03-14 12:00:00.323 INFO [api-gateway][174] Scheduled job finished", "service_bracketed", "INFO", "api-gateway"),
    ("Mar 14 12:00:05 web-01 sshd[24187]: Accepted publickey for deploy", "syslog", "UNKNOWN", "sshd"),
    ("081109 203615 148 INFO dfs.DataNode$PacketResponder: Received block", "hdfs", "INFO", None),
])
def test_formats_detected_and_parsed(line, fmt, level, service):
    assert detect_format([line]) == fmt
    p = parse_record(rec(line).records[0], fmt)
    assert p.level == level and p.timestamp is not None
    if service:
        assert p.service == service


def test_bgl_alert_label_and_timestamp():
    line = "KERNDTLB 1117838570 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-15.42.50.675872 R02-M1-N0-C:J12-U11 RAS KERNEL FATAL data TLB error interrupt"
    p = parse_record(rec(line).records[0], "bgl")
    assert p.anomaly_truth == "anomaly" and p.level == "FATAL" and p.timestamp == datetime(2005, 6, 3, 15, 42, 50, 675872)
    assert parse_record(rec(line.replace("KERNDTLB", "-", 1)).records[0], "bgl").anomaly_truth == "normal"


def test_missing_timestamp_unknown_level_and_garbage_never_raise():
    p = parse_record(rec("something weird happened with no structure").records[0])
    assert p.timestamp is None and p.level == "UNKNOWN" and p.message
    assert parse_record(rec("connection refused by upstream").records[0]).level == "ERROR"
    assert parse_timestamp("not a date") is None and parse_timestamp("") is None


def test_structured_labels_split_cluster_vs_anomaly_truth():
    a = parse_record(read_records(b'{"message":"x","label":"anomaly"}\n', "a.jsonl").records[0])
    b = parse_record(read_records(b'{"message":"x","label":"job_ok"}\n', "a.jsonl").records[0])
    assert a.anomaly_truth == "anomaly" and a.cluster_truth is None and b.cluster_truth == "job_ok"


# ---- preprocessing -----------------------------------------------------------------------------------
def test_normalization_examples_from_spec():
    assert normalize("Connection timeout for server 192.168.1.15 at 10:30:22") == "Connection timeout for server <IP> at <TIME>"
    assert normalize("Database connection failed for user 1042") == "Database connection failed for user <ID>"
    assert "<UUID>" in normalize("req 123e4567-e89b-12d3-a456-426614174000 failed")
    assert normalize("open /var/log/app/x.log failed") == "open <PATH> failed"
    assert "failed" in normalize("ERROR   failed   with   code") and "  " not in normalize("a   b")


def test_normalization_configurable_and_multiline():
    assert normalize("a 1\nstack line 2") == "a <NUM>"
    assert "stack line" in normalize("a 1\nstack line 2", {"keep_stack_trace": True})
    assert normalize("10.0.0.1", {"disabled_rules": ["ip"]}) != "<IP>"


def test_masking():
    t = mask_sensitive("user bob@example.com password=hunter2 token=abcdef1234567890XYZ call 555-123-4567", ["email", "password", "token", "phone"])
    assert "bob@" not in t and "hunter2" not in t and "abcdef12" not in t and "555-123" not in t


# ---- templates ---------------------------------------------------------------------------------------
def test_drain_extracts_template_and_counts():
    msgs = [normalize(f"Connection timeout for server 192.168.1.{i}") for i in (10, 15, 18)] + ["Disk full on volume <PATH>"] * 2
    ids, info = mine_templates(msgs)
    assert ids[0] == ids[1] == ids[2] != ids[3]
    assert info[ids[0]]["count"] == 3 and "timeout" in info[ids[0]]["template"]


def test_drain_generalises_beyond_regex():
    msgs = [f"Failed to connect to host{h} after {n} retries" for h, n in [("a", 1), ("b", 2), ("c", 3), ("d", 4)]]
    ids, info = mine_templates(msgs)
    assert len(set(ids)) == 1 and "<*>" in info[ids[0]]["template"]


def test_grouping_accuracy():
    assert grouping_accuracy([0, 0, 1], ["a", "a", "b"]) == 1.0
    assert grouping_accuracy([0, 0, 0], ["a", "a", "b"]) == 0.0


# ---- features ----------------------------------------------------------------------------------------
TEXTS = ["Connection timeout for server <IP>", "Connection timed out to <IP>", "Disk full on <PATH>", "No space left on <PATH>"] * 3


@pytest.mark.parametrize("mode", ["word", "char", "word+char"])
def test_tfidf_unit_norm(mode):
    f = tfidf_features(TEXTS, mode)
    assert f.matrix.shape[0] == len(TEXTS) and np.allclose(np.linalg.norm(f.matrix, axis=1), 1, atol=1e-4)


def test_embeddings_fallback_is_labelled(monkeypatch):
    f = embedding_features(TEXTS, use_cache=False)  # EMBEDDINGS_ENABLED=false in tests
    assert f.backend == "lsa-fallback" and "fallback" in f.note.lower()


# ---- clustering --------------------------------------------------------------------------------------
def blobs():
    rs = np.random.RandomState(0)
    X = np.vstack([rs.normal(c, 0.02, (30, 5)) for c in (0, 1, 2)])
    return X / np.linalg.norm(X, axis=1, keepdims=True), np.repeat([0, 1, 2], 30)


@pytest.mark.parametrize("algo", ["dbscan", "hdbscan", "kmeans"])
def test_clustering_algorithms_run(algo):
    X, y = blobs()
    lab, params = run_clustering(X, np.ones(len(X)), algo, None, 3, 5, 3)
    assert len(lab) == len(X) and params["algorithm"] == algo


def test_clustering_empty_and_tiny():
    assert len(run_clustering(np.zeros((0, 3)), None)[0]) == 0
    assert len(run_clustering(np.ones((2, 3)), None)[0]) == 2


def test_noise_attached_to_templates_and_metrics_penalise_noise():
    lab = np.array([0, 0, -1, -1, -1])
    out = attach_noise_to_templates(lab, np.array([7, 7, 7, 9, 9]))
    assert (out >= 0).all() and out[2] == 0 and out[3] == out[4] != 0
    m = clustering_metrics(np.eye(5), np.array([0, 0, 1, 1, -1]), ["a", "a", "b", "b", "b"])
    assert m["noise_ratio"] == 0.2 and 0 <= m["ari"] < 1


def test_anomaly_metrics():
    m = anomaly_metrics([0, 0, 1, 1], [0.1, 0.2, 0.9, 0.8], 0.5)
    assert m["precision"] == m["recall"] == m["roc_auc"] == 1.0
    assert "note" in anomaly_metrics([0, 0], [0.1, 0.2], 0.5)


# ---- anomaly detection -------------------------------------------------------------------------------
def make_rows(n_normal=300, burst=60):
    base = datetime(2026, 1, 1, 12, 0, 0)
    lines = []
    for i in range(n_normal):
        lines.append(f"2026-01-01 12:{i // 60:02d}:{i % 60:02d} INFO [api][1] request {i} ok")
        if i % 30 == 0:
            lines.append(f"2026-01-01 12:{i // 60:02d}:{i % 60:02d} ERROR [db][2] query {i} slow")
    for k in range(burst):
        lines.append(f"2026-01-01 12:04:{k % 60:02d} ERROR [db][2] Connection pool exhausted for host 10.0.0.{k % 5}")
    files = [{"name": "a.log", "data": "\n".join(lines).encode()}]
    return parse_files(files)[0]


def test_zscore_spike_detection():
    import pandas as pd
    s = pd.Series([2, 3, 2, 3, 2, 3, 2, 40, 3, 2], index=pd.date_range("2026-01-01", periods=10, freq="1min"))
    sp = zscore_spikes(s, z=3)
    assert len(sp) == 1 and sp[0]["count"] == 40 and sp[0]["z"] > 3


def test_no_anomalies_on_flat_data():
    rows = parse_files([{"name": "a.log", "data": "\n".join(f"2026-01-01 12:{i // 60:02d}:{i % 60:02d} INFO [api][1] heartbeat ok" for i in range(120)).encode()}])[0]
    out = analyze(rows, {"run_evaluation": False})
    assert all(a["kind"] not in ("frequency_spike_1min", "severity_shift") for a in out["anomalies"]) and out["stats"]["total_logs"] == 120


# ---- end-to-end pure analysis, root cause, priority, summaries ---------------------------------------
@pytest.fixture(scope="module")
def result():
    return analyze(make_rows(), {"run_evaluation": True, "evaluation_max_unique": 200})


def test_analysis_produces_consistent_structure(result):
    rows, clusters = result["rows"], result["clusters"]
    assert all(r.cluster_id >= 0 and r.template_id >= 0 and r.normalized for r in rows)
    assert sum(c["size"] for c in clusters) == len(rows)
    pool = next(c for c in clusters if "pool" in c["template"].lower())
    assert pool["size"] == 60 and pool["priority"] in ("Critical", "High") and "<IP>" in pool["template"]
    assert pool["name"] and pool["summary"] and pool["representatives"]


def test_burst_detected_with_explanation(result):
    spikes = [a for a in result["anomalies"] if a["kind"].startswith("frequency_spike")]
    assert spikes and all("z=" in a["reason"] for a in spikes)


def test_insights_are_evidence_based_and_hedged(result):
    ins = next(i for i in result["insights"] if "pool" in i["title"].lower() or "Database" in i["title"])
    assert ins["evidence"] and ins["recommendations"] and ins["confidence"] in ("Strong evidence", "Moderate evidence", "Limited evidence")
    assert "not confirmed" in ins["disclaimer"].lower() and "confirmed" not in ins["hypothesis"].lower().replace("not confirmed", "")
    assert {e["type"] for e in ins["evidence"]} <= {"observed", "statistical", "model"}


def test_evaluation_contains_measured_values(result):
    ev = result["evaluation"]
    assert ev["comparison"]["grid"] and {g["algorithm"] for g in ev["comparison"]["grid"]} == {"dbscan", "hdbscan", "kmeans"}
    assert all("cluster_seconds" in g and "peak_memory_mb" in g for g in ev["comparison"]["grid"] if "error" not in g)
    assert ev["logs_per_second"] > 0 and "warning" in ev["comparison"]  # embeddings disabled in tests -> fallback is flagged


def test_categorize_and_priority():
    assert categorize("Database connection timeout")[0].startswith("Database")
    assert categorize("zzz qqq")[0].startswith("Unclassified")
    s, parts = priority_score("FATAL", 500, 1000, 0.9, 3, 0.9, 3, 4)
    assert priority_label(s, "FATAL") == "Critical" and set(parts) == {"severity", "frequency", "anomaly", "trend", "recency", "impact"}
    assert priority_label(5, "INFO") == "Low"


def test_llm_disabled_falls_back_without_key():
    c = {"name": "x", "size": 3, "severity": "ERROR", "priority": "High", "template": "t", "services": {"a": 3}, "first_seen": None, "last_seen": None,
         "keywords": [], "is_anomalous": False, "trend_ratio": 1.0}
    assert llm_enhance(rule_summary(c), c, "", "") == (rule_summary(c), "rule")
    assert llm_enhance(rule_summary(c), c, "openai", "")[1] == "rule"


def test_edge_cases_empty_and_duplicates():
    with pytest.raises(IngestionError):
        parse_files([{"name": "a.log", "data": b"\n\n   \n"}])
    rows = parse_files([{"name": "a.log", "data": b"ERROR same thing\n" * 50}])[0]
    out = analyze(rows, {"run_evaluation": False})
    assert out["stats"]["n_clusters"] == 1 and out["stats"]["total_logs"] == 50


def test_mixed_formats_and_missing_timestamps():
    data = ("2026-03-14 12:00:00,1 - app - ERROR - boom\nMar 14 12:00:05 web-01 sshd[1]: failed login\nplain line with no timestamp\n" * 20).encode()
    rows = parse_files([{"name": "m.log", "data": data}])[0]
    out = analyze(rows, {"run_evaluation": False})
    assert out["stats"]["total_logs"] == 60 and out["stats"]["unparsed_timestamps"] == 20


def test_healthapp_format_and_priority_floor():
    line = "20171223-22:15:29:606|Step_LSC|30002312|onStandStepChanged 3579"
    assert detect_format([line]) == "healthapp"
    p = parse_record(rec(line).records[0], "healthapp")
    assert p.timestamp == datetime(2017, 12, 23, 22, 15, 29, 606000) and p.message.startswith("onStandStepChanged")
    assert priority_label(40, "FATAL") == "High" and priority_label(60, "FATAL") == "Critical"
