import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import mongoose from "mongoose";
import request from "supertest";
import { MongoMemoryServer } from "mongodb-memory-server";

let mongo, app;
before(async () => { mongo = await MongoMemoryServer.create(); await mongoose.connect(mongo.getUri()); ({ app } = await import("../src/app.js")); });
after(async () => { await mongoose.disconnect(); await mongo.stop(); });

test("full API flow", async () => {
  const up = (await request(app).post("/api/samples/nginx_access.log")).body;
  const job = (await request(app).post("/api/jobs").send({ file_ids: [up.file_id], config: { run_evaluation: false } })).body;
  let j;
  for (let i = 0; i < 120; i++) { j = (await request(app).get(`/api/jobs/${job.id}`)).body; if (["completed", "failed"].includes(j.status)) break; await new Promise((r) => setTimeout(r, 250)); }
  assert.equal(j.status, "completed", j.error);
  assert.equal((await request(app).get(`/api/jobs/${job.id}/overview`)).body.total_logs, 1500);
  assert.ok((await request(app).get(`/api/jobs/${job.id}/logs?level=ERROR`)).body.total > 0);
  const pdf = await request(app).get(`/api/jobs/${job.id}/report.pdf`).buffer(true).parse((res, cb) => { const c = []; res.on("data", (d) => c.push(d)); res.on("end", () => cb(null, Buffer.concat(c))); });
  assert.equal(pdf.body.subarray(0, 4).toString(), "%PDF");
  assert.equal((await request(app).post("/api/upload").attach("files", Buffer.from("abc"), "x.exe")).status, 400);
});
