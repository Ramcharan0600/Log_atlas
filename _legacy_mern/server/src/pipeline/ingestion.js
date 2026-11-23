// File validation, encoding handling, CSV/JSON/JSONL/TXT reading, multiline (stack trace) merging.
export const ALLOWED_EXT = ["txt", "log", "csv", "json", "jsonl"];

export function validateFile(name, size, maxMb = 50) {
  const ext = name.includes(".") ? name.split(".").pop().toLowerCase() : "";
  if (!ALLOWED_EXT.includes(ext)) throw new Error(`Unsupported file type '.${ext}'. Allowed: ${ALLOWED_EXT.join(", ")}`);
  if (size === 0) throw new Error("File is empty");
  if (size > maxMb * 1024 * 1024) throw new Error(`File exceeds ${maxMb} MB limit`);
}

export function decode(buf) {
  if (buf[0] === 0xff && buf[1] === 0xfe) return { text: buf.toString("utf16le").slice(1), encoding: "utf-16le" };
  if (buf[0] === 0xef && buf[1] === 0xbb && buf[2] === 0xbf) return { text: buf.toString("utf8").slice(1), encoding: "utf-8-sig" };
  const text = buf.toString("utf8");
  const bad = (text.match(/\uFFFD/g) || []).length;
  if (bad > text.length * 0.01) return { text: buf.toString("latin1"), encoding: "latin1" };
  return { text, encoding: "utf-8" };
}

const MSG_KEYS = ["message", "msg", "log", "text", "content"];
function fromObj(lineNo, obj) {
  const lower = Object.fromEntries(Object.entries(obj).map(([k, v]) => [k.toLowerCase(), v]));
  const k = MSG_KEYS.find((k) => k in lower);
  return { lineNo, text: k ? String(lower[k]) : JSON.stringify(obj), fields: lower };
}

export function parseCsv(text) {
  const rows = []; let row = [], cur = "", q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) { if (c === '"' && text[i + 1] === '"') { cur += '"'; i++; } else if (c === '"') q = false; else cur += c; }
    else if (c === '"') q = true; else if (c === ",") { row.push(cur); cur = ""; }
    else if (c === "\n" || c === "\r") { if (c === "\r" && text[i + 1] === "\n") i++; row.push(cur); rows.push(row); row = []; cur = ""; }
    else cur += c;
  }
  if (cur || row.length) { row.push(cur); rows.push(row); }
  const [head, ...body] = rows.filter((r) => r.some((x) => x !== ""));
  return body.map((r) => Object.fromEntries(head.map((h, i) => [h.trim(), r[i] ?? ""])));
}

const isContinuation = (line) => {
  const s = line.trimStart();
  return /^[ \t]/.test(line) && !/^\d/.test(s) || s.startsWith("Caused by") || s.startsWith("Traceback");
};

export function mergeMultiline(lines) {
  const out = [];
  lines.forEach((line, i) => {
    if (!line.trim()) return;
    if (out.length && isContinuation(line)) out[out.length - 1].text += "\n" + line.trimEnd();
    else out.push({ lineNo: i + 1, text: line.trimEnd(), fields: null });
  });
  return out;
}

export function readRecords(buf, filename) {
  const { text, encoding } = decode(buf);
  const ext = filename.split(".").pop().toLowerCase();
  let invalid = 0, recs = [];
  if (ext === "csv") recs = parseCsv(text).map((r, i) => fromObj(i + 1, r));
  else if (ext === "json" || ext === "jsonl") {
    const t = text.trim();
    if (t.startsWith("[")) recs = JSON.parse(t).map((o, i) => (typeof o === "object" ? fromObj(i + 1, o) : { lineNo: i + 1, text: String(o), fields: null }));
    else text.split(/\r?\n/).forEach((l, i) => {
      if (!l.trim()) return;
      try { const o = JSON.parse(l); recs.push(typeof o === "object" ? fromObj(i + 1, o) : { lineNo: i + 1, text: String(o), fields: null }); } catch { invalid++; }
    });
  } else recs = mergeMultiline(text.split(/\r?\n/));
  return { recs, encoding, invalid };
}
