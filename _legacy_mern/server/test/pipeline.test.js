import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "fs";
import { normalize } from "../src/pipeline/normalizer.js";
import { parseLine } from "../src/pipeline/parser.js";
import { priorityLabel } from "../src/pipeline/priority.js";
import { parseFiles, analyze } from "../src/pipeline/runner.js";

const S = new URL("../sample_data/", import.meta.url);

test("normalization examples from the spec", () => {
  assert.equal(normalize("Connection timeout for server 192.168.1.15 at 10:30:22"), "Connection timeout for server <IP> at <TIME>");
  assert.equal(normalize("Database connection failed for user 1042"), "Database connection failed for user <ID>");
});
test("parses python logging", () => {
  const p = parseLine(1, "2026-03-14 12:00:01,123 - app.db - ERROR - Connection refused");
  assert.equal(p.level, "ERROR"); assert.equal(p.component, "app.db"); assert.equal(p.timestamp.getUTCFullYear(), 2026);
});
test("parses nginx access", () => {
  const p = parseLine(1, '10.0.0.1 - - [14/Mar/2026:12:00:00 +0000] "GET /x HTTP/1.1" 502 120 "-" "curl"');
  assert.equal(p.level, "ERROR"); assert.equal(p.error_code, "502"); assert.equal(p.ip, "10.0.0.1");
});
test("FATAL is always Critical; 55 is High", () => { assert.equal(priorityLabel(10, "FATAL"), "Critical"); assert.equal(priorityLabel(55, "ERROR"), "High"); });

test("end-to-end detects the injected DB incident", async () => {
  const { rows, meta } = parseFiles([{ name: "app_service.log", data: fs.readFileSync(new URL("app_service.log", S)) }]);
  assert.equal(meta.files[0].format, "service_bracketed");
  const res = await analyze(rows, { run_evaluation: false });
  assert.ok(res.clusters.slice(0, 8).some((c) => c.template.toLowerCase().includes("database connection timeout")));
  assert.ok(res.anomalies.some((a) => a.kind.startsWith("frequency_spike")));
  assert.ok(res.insights.length && res.insights.every((i) => i.disclaimer.toLowerCase().includes("not confirmed")));
});
test("labeled evaluation gives good ARI", async () => {
  const { rows } = parseFiles([{ name: "labeled_events.jsonl", data: fs.readFileSync(new URL("labeled_events.jsonl", S)) }]);
  const res = await analyze(rows.slice(0, 2500), { run_evaluation: true });
  console.log("final", res.evaluation.final, "tga", res.evaluation.template_grouping_accuracy);
  assert.ok(res.evaluation.final.ARI > 0.5);
});
