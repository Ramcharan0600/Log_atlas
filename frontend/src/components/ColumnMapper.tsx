import { useEffect, useState } from "react";
import { Columns3, Wand2 } from "lucide-react";
import { api, errMsg } from "../services/api";
import { useToast } from "../hooks/useToast";
import { ColumnInfo, Preview } from "../types";

const HINTS: Record<string, string> = {
  message: "Required. The text that is clustered and summarized.", timestamp: "Used for timelines, trends and spike detection.", level: "Severity (INFO, WARN, ERROR…).",
  service: "Which service/app produced the line.", label: "Optional ground truth (normal/anomaly) used for evaluation.",
};

/** Lets the user say which CSV column feeds which log field, then saves the mapping and refreshes the preview. */
export default function ColumnMapper({ fileId, onApplied }: { fileId: number; onApplied: (preview: Preview) => void }) {
  const { notify } = useToast();
  const [info, setInfo] = useState<ColumnInfo | null>(null);
  const [map, setMap] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false); const [err, setErr] = useState(""); const [open, setOpen] = useState(false);

  useEffect(() => {
    let live = true;
    api.get<ColumnInfo>(`/files/${fileId}/columns`).then((r) => { if (live) { setInfo(r.data); setMap(r.data.current_mapping ?? r.data.suggested_mapping); } })
      .catch((e) => live && setErr(errMsg(e)));
    return () => { live = false; };
  }, [fileId]);

  if (err) return <div className="text-crit text-sm mb-3">{err}</div>;
  if (!info) return null;

  const apply = async () => {
    setBusy(true); setErr("");
    try {
      const r = await api.put<{ preview: Preview }>(`/files/${fileId}/column-map`, { mapping: map });
      onApplied(r.data.preview); notify("Column mapping saved");
    } catch (e) { setErr(errMsg(e)); } finally { setBusy(false); }
  };

  return (
    <div className="border border-line rounded-md p-3 mb-3 text-sm">
      <button className="flex items-center gap-2 font-medium" onClick={() => setOpen(!open)} aria-expanded={open}><Columns3 size={15} /> Map CSV columns {open ? "▾" : "▸"}
        <span className="text-dim font-normal">{Object.keys(map).length} of {info.fields.length} fields mapped</span></button>
      {open && (
        <div className="mt-3 space-y-3">
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
            {info.fields.map((f) => (
              <label key={f} className="block"><div className="text-dim mb-1">{f}{f === "message" && <span className="text-crit"> *</span>}<span className="ml-1 text-xs">{HINTS[f] ?? ""}</span></div>
                <select className="input w-full" value={map[f] ?? ""} onChange={(e) => { const m = { ...map }; if (e.target.value) m[f] = e.target.value; else delete m[f]; setMap(m); }}>
                  <option value="">— not in this file —</option>{info.headers.map((h) => <option key={h} value={h}>{h}</option>)}</select></label>))}
          </div>
          <div className="overflow-x-auto"><table className="tbl"><thead><tr>{info.headers.map((h) => <th key={h}>{h}</th>)}</tr></thead>
            <tbody>{info.sample_rows.map((r, i) => <tr key={i}>{info.headers.map((h) => <td key={h} className="mono truncate max-w-xs">{r[h]}</td>)}</tr>)}</tbody></table></div>
          <div className="flex gap-2">
            <button className="btn-ghost" onClick={() => setMap(info.suggested_mapping)}><Wand2 size={14} /> Auto-detect</button>
            <button className="btn-primary" disabled={busy || !map.message} onClick={apply}>{busy ? "Saving…" : "Apply mapping"}</button></div>
        </div>)}
    </div>
  );
}
