// Replace variable fields with typed placeholders + configurable noise reduction.
export const RULES = [
  ["uuid", /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi, "<UUID>"],
  ["url", /\bhttps?:\/\/[^\s"']+/g, "<URL>"],
  ["ip_port", /\b(?:\d{1,3}\.){3}\d{1,3}:\d{1,5}\b/g, "<IP>:<PORT>"],
  ["ip", /\b(?:\d{1,3}\.){3}\d{1,3}\b/g, "<IP>"],
  ["datetime", /\b\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?\b/g, "<TIMESTAMP>"],
  ["time", /\b\d{1,2}:\d{2}:\d{2}(?:\.\d+)?\b/g, "<TIME>"],
  ["date", /\b\d{4}-\d{2}-\d{2}\b/g, "<DATE>"],
  ["hex", /\b0x[0-9a-f]+\b/gi, "<HEX>"],
  ["blk", /\bblk_-?\d+\b/g, "<BLK>"],
  ["path", /(?<![\w<])(?:\/[\w.@-]+){2,}\/?/g, "<PATH>"],
  ["port", /\bport[ =:]+\d{2,5}\b/gi, "port <PORT>"],
  ["duration", /\b\d+(?:\.\d+)?\s?(?:ms|s|sec|seconds|min|MB|KB|GB|bytes|%)(?!\w)/gi, "<NUM>"],
  ["id_after_kw", /\b(user|id|session|order|account|txn|job|pid|tid|thread)[ =:#]+\d+\b/gi, "$1 <ID>"],
  ["longnum", /\b\d{4,}\b/g, "<ID>"],
  ["num", /(?<![<\w])\d+(?:\.\d+)?(?![\w>])/g, "<NUM>"],
];
export const ERROR_KEYWORDS = ["error", "fail", "exception", "timeout", "refused", "denied", "fatal", "critical", "unavailable", "crash", "oom", "killed", "panic", "deadlock"];

export function normalize(message, cfg = {}) {
  const { lowercase = false, keep_stack_trace = false, max_length = 500, disabled_rules = [] } = cfg;
  let t = keep_stack_trace ? message : message.split("\n")[0];
  for (const [name, re, repl] of RULES) if (!disabled_rules.includes(name)) t = t.replace(re, repl);
  t = t.replace(/[ \t]+/g, " ").replace(/(<NUM>[ ,]*){2,}/g, "<NUM> ").replace(/([=\-*_#])\1{3,}/g, "$1").trim();
  if (lowercase) t = t.replace(/(?<!<)\b[A-Za-z]+\b(?!>)/g, (w) => w.toLowerCase());
  return t.slice(0, max_length);
}
