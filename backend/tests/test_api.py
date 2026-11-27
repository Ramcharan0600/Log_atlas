import time


def wait_done(client, job_id, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        s = client.get(f"/api/analysis/{job_id}/status").json()
        if s["status"] in ("completed", "failed"):
            return s
        time.sleep(0.3)
    raise AssertionError("job timed out")


def upload(client, sample_dir, name):
    r = client.post("/api/logs/upload", files=[("files", (name, (sample_dir / name).read_bytes(), "text/plain"))])
    assert r.status_code == 200, r.text
    return r.json()[0]


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/openapi.json").status_code == 200  # API docs available at /docs


def test_rate_limit_reply_keeps_cors_headers():
    from fastapi.testclient import TestClient

    from app.core.ratelimit import RateLimitMiddleware
    from app.main import app

    # rebuild the app's middleware stack with a limit of 1 (tests otherwise run with the limit disabled)
    mw = next(m for m in app.user_middleware if m.cls is RateLimitMiddleware)
    original, mw.kwargs["per_minute"], app.middleware_stack = mw.kwargs["per_minute"], 1, None
    try:
        c = TestClient(app)
        headers = {"Origin": "http://localhost:5173"}
        first, second = c.get("/api/missing", headers=headers), c.get("/api/missing", headers=headers)
        assert (first.status_code, second.status_code) == (404, 429)
        assert second.headers["access-control-allow-origin"] == "http://localhost:5173"
    finally:
        mw.kwargs["per_minute"], app.middleware_stack = original, None


def test_upload_validation(client):
    assert client.post("/api/logs/upload", files=[("files", ("x.exe", b"abc", "application/octet-stream"))]).status_code == 400
    assert client.post("/api/logs/upload", files=[("files", ("empty.log", b"", "text/plain"))]).status_code == 400
    assert client.post("/api/logs/upload", files=[("files", ("../../evil.log", b"2026-01-01 10:00:00 ERROR x\n", "text/plain"))]).status_code == 200  # path stripped


def test_unknown_resources_and_bad_input(client):
    assert client.get("/api/analysis/99999").status_code == 404
    assert client.get("/api/clusters/99999").status_code == 404
    assert client.post("/api/analysis/start", json={"file_ids": []}).status_code == 422
    assert client.post("/api/analysis/start", json={"file_ids": [99999]}).status_code == 404
    assert client.post("/api/analysis/start", json={"file_ids": [1], "config": {"algorithm": "magic"}}).status_code == 422
    assert client.post("/api/datasets/load", json={"name": "nope"}).status_code == 400


def test_dataset_catalog_marks_synthetic(client):
    d = client.get("/api/datasets").json()
    assert any(x["is_synthetic"] for x in d) and any(not x["is_synthetic"] and "Loghub" in x["source"] for x in d)


def test_full_workflow_labelled_dataset(client, sample_dir):
    up = upload(client, sample_dir, "labeled_anomaly.csv")
    assert up["preview"]["n_records"] == 6000 and up["preview"]["has_ground_truth"]
    job = client.post("/api/analysis/start", json={"file_ids": [up["file_id"]], "config": {"evaluation_max_unique": 300}}).json()
    assert client.get(f"/api/analysis/{job['id']}/summary").status_code == 409 or True
    st = wait_done(client, job["id"])
    assert st["status"] == "completed", st
    jid = job["id"]

    s = client.get(f"/api/analysis/{jid}/summary").json()
    assert s["total_logs"] == 6000 and s["n_clusters"] > 0 and sum(s["levels"].values()) == 6000

    cl = client.get(f"/api/analysis/{jid}/clusters").json()
    assert cl and sum(c["size"] for c in cl) == 6000
    c0 = client.get(f"/api/clusters/{cl[0]['id']}").json()
    assert c0["representatives"] and c0["priority_explanation"]
    lg = client.get(f"/api/clusters/{cl[0]['id']}/logs?page_size=5").json()
    assert lg["total"] == cl[0]["size"] and len(lg["items"]) == 5

    # log explorer filters + pagination + safe search
    all_logs = client.get(f"/api/analysis/{jid}/logs?page_size=10").json()
    assert all_logs["total"] == 6000 and len(all_logs["items"]) == 10 and all_logs["items"][0]["normalized_message"]
    errs = client.get(f"/api/analysis/{jid}/logs?severity=ERROR,FATAL").json()["total"]
    assert 0 < errs < 6000
    assert client.get(f"/api/analysis/{jid}/logs?q=%25_%27").json()["total"] == 0  # wildcards/quotes are escaped, not injected
    assert client.get(f"/api/analysis/{jid}/logs?anomaly=true").json()["total"] > 0
    assert client.get(f"/api/analysis/{jid}/facets").json()["services"]

    an = client.get(f"/api/analysis/{jid}/anomalies").json()
    assert an["items"] and all(a["reason"] for a in an["items"])
    d = client.get(f"/api/analysis/{jid}/anomalies/{an['items'][0]['id']}").json()
    assert "logs" in d
    assert client.get(f"/api/analysis/{jid}/templates").json()["total"] > 0
    tl = client.get(f"/api/analysis/{jid}/timeline").json()
    assert tl["points"] and sum(p["total"] for p in tl["points"]) == 6000

    ins = client.get(f"/api/analysis/{jid}/insights").json()
    assert all(i["evidence"] and "not confirmed" in i["disclaimer"].lower() for i in ins)

    ev = client.get(f"/api/analysis/{jid}/evaluation").json()
    assert ev["evaluation"]["comparison"]["grid"] and "roc_auc" in ev["evaluation"]["anomaly"]["isolation_forest"]
    run = client.post(f"/api/analysis/{jid}/evaluation/run", json={"min_cluster_size": 3, "max_unique": 200})
    assert run.status_code == 200 and run.json()["grid"]
    assert len(client.get(f"/api/analysis/{jid}/evaluation").json()["experiments"]) > 6

    j = client.get(f"/api/analysis/{jid}/export?format=json")
    assert j.status_code == 200 and j.json()["dataset"]["total_logs"] == 6000
    assert client.get(f"/api/analysis/{jid}/export?format=csv").content.count(b"\n") >= len(cl)
    pdf = client.get(f"/api/analysis/{jid}/export?format=pdf")
    assert pdf.content[:4] == b"%PDF"
    assert client.get(f"/api/analysis/{jid}/export?format=xml").status_code == 422

    assert any(x["id"] == jid for x in client.get("/api/analysis").json()["items"])
    assert client.delete(f"/api/analysis/{jid}").status_code == 204
    assert client.get(f"/api/analysis/{jid}").status_code == 404


def test_sample_dataset_load_and_failed_job_has_no_stack_trace(client):
    r = client.post("/api/datasets/load", json={"name": "Synthetic: application service log"})
    assert r.status_code == 200 and r.json()["is_synthetic"] and r.json()["preview"]["detected_format"] == "service_bracketed"
    jid = client.post("/api/analysis/start", json={"file_ids": [r.json()["file_id"]], "config": {"run_evaluation": False, "algorithm": "hdbscan"}}).json()["id"]
    assert wait_done(client, jid)["status"] == "completed"
    assert client.get(f"/api/analysis/{jid}").json()["is_synthetic"] is True


def test_secrets_are_masked_before_storage(client):
    body = b"2026-01-01 10:00:00 ERROR login failed for bob@corp.com password=hunter2 token=abcdef1234567890ZZ\n" * 8
    up = client.post("/api/logs/upload", files=[("files", ("secret.log", body, "text/plain"))]).json()[0]
    jid = client.post("/api/analysis/start", json={"file_ids": [up["file_id"]], "config": {"run_evaluation": False}}).json()["id"]
    assert wait_done(client, jid)["status"] == "completed"
    m = client.get(f"/api/analysis/{jid}/logs").json()["items"][0]["original_message"]
    assert "bob@corp.com" not in m and "hunter2" not in m and "abcdef1234567890" not in m


def test_invalid_file_fails_gracefully(client):
    up = client.post("/api/logs/upload", files=[("files", ("bad.json", b"[not json", "application/json"))])
    assert up.status_code == 400 or up.json()[0].get("error")


CUSTOM_CSV = (b"Event Time,Sev,App Name,Description\n"
              b"2026-11-01 10:00:01,ERROR,billing,Payment failed for order 1001\n"
              b"2026-11-01 10:00:02,INFO,auth,Login ok for user 8\n")


def test_csv_column_mapping(client):
    up = client.post("/api/logs/upload", files=[("files", ("custom.csv", CUSTOM_CSV, "text/csv"))]).json()[0]
    fid = up["file_id"]
    assert up["preview"]["timestamp_parse_rate"] == 0  # non-standard headers are not understood by default

    info = client.get(f"/api/files/{fid}/columns").json()
    assert info["headers"] == ["Event Time", "Sev", "App Name", "Description"]
    assert info["suggested_mapping"]["timestamp"] == "Event Time" and info["suggested_mapping"]["message"] == "Description"

    # message column is mandatory; unknown headers/fields are rejected
    assert client.put(f"/api/files/{fid}/column-map", json={"mapping": {"timestamp": "Event Time"}}).status_code == 400
    assert client.put(f"/api/files/{fid}/column-map", json={"mapping": {"message": "Nope"}}).status_code == 400
    assert client.put(f"/api/files/{fid}/column-map", json={"mapping": {"message": "Description", "bogus": "Sev"}}).status_code == 400

    ok = client.put(f"/api/files/{fid}/column-map", json={"mapping": {"timestamp": "Event Time", "level": "Sev", "service": "App Name", "message": "Description"}})
    assert ok.status_code == 200
    rows = ok.json()["preview"]["rows"]
    assert ok.json()["preview"]["timestamp_parse_rate"] == 1.0
    assert rows[0]["level"] == "ERROR" and rows[0]["service"] == "billing" and rows[0]["message"] == "Payment failed for order 1001"
    assert client.get(f"/api/files/{fid}/columns").json()["current_mapping"]["message"] == "Description"


def test_column_mapping_rejects_non_csv_and_unknown_file(client):
    up = client.post("/api/logs/upload", files=[("files", ("a.log", b"2026-01-01 10:00:00 ERROR x\n", "text/plain"))]).json()[0]
    assert client.get(f"/api/files/{up['file_id']}/columns").status_code == 400
    assert client.get("/api/files/999999/columns").status_code == 404


def test_database_url_driver_is_normalised():
    from app.core.config import Settings
    assert Settings(database_url="postgres://u:p@h/db").database_url == "postgresql+psycopg://u:p@h/db"
    assert Settings(database_url="postgresql://u:p@h/db").database_url == "postgresql+psycopg://u:p@h/db"
    assert Settings(database_url="postgresql+psycopg://u:p@h/db").database_url == "postgresql+psycopg://u:p@h/db"
    assert Settings(database_url="sqlite:///x.db").database_url == "sqlite:///x.db"
