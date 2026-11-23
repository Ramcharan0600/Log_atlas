// Pluggable log parser: each format is a regex + optional post-processor. Unknown lines fall back to heuristics.
const LEVELS = ["FATAL", "CRITICAL", "ERROR", "WARN", "WARNING", "NOTICE", "INFO", "DEBUG", "TRACE"];
const LEVEL_MAP = { WARNING: "WARN", CRITICAL: "FATAL", NOTICE: "INFO", TRACE: "DEBUG", SEVERE: "ERROR", ERR: "ERROR" };
const LEVEL_RE = new RegExp(`\\b(${LEVELS.join("|")})\\b`, "i");
const IP_RE = /\b(?:\d{1,3}\.){3}\d{1,3}\b/;
const REQ_RE = /\b(?:req(?:uest)?[_-]?id|trace[_-]?id)[=: ]+([\w-]+)/i;
const CODE_RE = /\b(?:code|errno|status)[=: ]+(\d{3,5})\b|\b([A-Z]{2,5}-?\d{3,5})\b/;
const TS_RE = /(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?|\d{2}\/\w{3}\/\d{4}:\d{2}:\d{2}:\d{2} [+-]\d{4}|\w{3}\s+\d{1,2} \d{2}:\d{2}:\d{2}|\d{4}\/\d{2}\/\d{2} \d{2}:\d{2}:\d{2}|\d{6} \d{6})/;
const MONTHS = { Jan: 0, Feb: 1, Mar: 2, Apr: 3, May: 4, Jun: 5, Jul: 6, Aug: 7, Sep: 8, Oct: 9, Nov: 10, Dec: 11 };

export function parseTimestamp(s) {
  if (!s) return null;
  if (s instanceof Date) return s;
  s = String(s).trim();
  let m;
  if ((m = s.match(/^(\d{4})[-/](\d{2})[-/](\d{2})[ T](\d{2}):(\d{2}):(\d{2})(?:[.,](\d+))?/)))
    return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6], m[7] ? +m[7].slice(0, 3).padEnd(3, "0") : 0));
  if ((m = s.match(/^(\d{2})\/(\w{3})\/(\d{4}):(\d{2}):(\d{2}):(\d{2})/)))
    return new Date(Date.UTC(+m[3], MONTHS[m[2]], +m[1], +m[4], +m[5], +m[6]));
  if ((m = s.match(/^(\w{3})\s+(\d{1,2}) (\d{2}):(\d{2}):(\d{2})/)) && m[1] in MONTHS)
    return new Date(Date.UTC(new Date().getUTCFullYear(), MONTHS[m[1]], +m[2], +m[3], +m[4], +m[5]));
  if ((m = s.match(/^(\d{2})(\d{2})(\d{2}) (\d{2})(\d{2})(\d{2})$/)))
    return new Date(Date.UTC(2000 + +m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]));
  const d = new Date(s);
  return isNaN(d) ? null : d;
}

const apachePost = (d) => {
  const st = +d.status || 0;
  return { ...d, level: st >= 500 ? "ERROR" : st >= 400 ? "WARN" : "INFO", error_code: String(st), message: `${d.method} ${d.path} ${st}`, service: "web" };
};

export const FORMATS = [
  { name: "apache_nginx_access", re: /^(?<ip>\S+) \S+ \S+ \[(?<timestamp>[^\]]+)\] "(?<method>\w+) (?<path>\S+)[^"]*" (?<status>\d{3}) \S+/, post: apachePost },
  { name: "apache_error", re: /^\[(?<timestamp>[^\]]+)\] \[(?:(?<component>\w+):)?(?<level>\w+)\](?: \[pid (?<pid>\d+)(?::tid (?<thread>\d+))?\])?(?: \[client (?<ip>[\d.]+)(?::\d+)?\])? (?<message>.*)$/s },
  { name: "python_logging", re: /^(?<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}[,.]\d+) - (?<component>[\w.]+) - (?<level>\w+) - (?<message>.*)$/s },
  { name: "java_log4j", re: /^(?<timestamp>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}[,.]?\d*)\s+(?<level>[A-Z]+)\s+\[(?<thread>[^\]]+)\]\s+(?<component>[\w.$]+)\s*[-:]\s*(?<message>.*)$/s },
  { name: "service_bracketed", re: /^(?<timestamp>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?Z?)\s+\[?(?<level>[A-Za-z]+)\]?\s+\[?(?<service>[\w.-]+)\]?(?:\[(?<pid>\d+)\])?:?\s+(?<message>.*)$/s },
  { name: "syslog", re: /^(?<timestamp>\w{3}\s+\d{1,2} \d{2}:\d{2}:\d{2}) (?<host>\S+) (?<service>[\w./-]+?)(?:\[(?<pid>\d+)\])?: (?<message>.*)$/s },
  { name: "hdfs", re: /^(?<timestamp>\d{6} \d{6}) (?<pid>\d+) (?<level>\w+) (?<component>[\w.$]+): (?<message>.*)$/s },
];

export function detectFormat(sample) {
  let best = "generic", bestN = 0;
  for (const f of FORMATS) { const n = sample.filter((s) => f.re.test(s)).length; if (n > bestN) { best = f.name; bestN = n; } }
  return bestN >= Math.max(1, sample.length * 0.3) ? best : "generic";
}

function normLevel(level, msg) {
  let lv = (level || "").toUpperCase();
  if (!LEVELS.includes(lv) && !(lv in LEVEL_MAP)) {
    const m = msg.match(LEVEL_RE);
    lv = m ? m[1].toUpperCase() : /exception|failed|failure|fatal|refused|timeout/i.test(msg) ? "ERROR" : "UNKNOWN";
  }
  return LEVEL_MAP[lv] || lv;
}

export function parseLine(lineNo, text, fields, fmtHint) {
  let d = {};
  if (fields) {
    const f = fields;
    d = { timestamp: f.timestamp || f.time || f["@timestamp"] || f.date, level: f.level || f.severity || f.loglevel,
      service: f.service || f.app || f.application, component: f.component || f.logger || f.module, host: f.host || f.hostname,
      ip: f.ip || f.client_ip, pid: f.pid, thread: f.thread, request_id: f.request_id || f.trace_id, error_code: f.error_code || f.status,
      label: f.label ?? f.anomaly, message: text };
  } else {
    const ordered = [...FORMATS].sort((a, b) => (a.name === fmtHint ? -1 : b.name === fmtHint ? 1 : 0));
    for (const f of ordered) {
      const m = text.match(f.re);
      if (m) { d = Object.fromEntries(Object.entries(m.groups).filter(([, v]) => v !== undefined)); if (f.post) d = f.post(d); break; }
    }
    if (!Object.keys(d).length) {
      const m = text.match(TS_RE);
      d = { timestamp: m?.[1], message: m ? text.slice(m.index + m[0].length).replace(/^[\s\-:|\]]+/, "") : text };
    }
  }
  const msg = String(d.message ?? text);
  const first = msg.split("\n")[0];
  let code = d.error_code;
  if (!code) { const m = first.match(CODE_RE); code = m ? m[1] || m[2] : null; }
  return {
    line_no: lineNo, message: msg, timestamp: parseTimestamp(d.timestamp), level: normLevel(d.level, first),
    service: d.service || d.component || null, component: d.component || null, host: d.host || null,
    ip: d.ip || text.match(IP_RE)?.[0] || null, pid: d.pid ? String(d.pid) : null, thread: d.thread || null,
    request_id: d.request_id || text.match(REQ_RE)?.[1] || null, error_code: code ? String(code) : null,
    label: d.label !== undefined && d.label !== "" && d.label !== null ? String(d.label) : null,
  };
}
