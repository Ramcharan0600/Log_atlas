import axios from "axios";

const base = (import.meta.env.VITE_API_URL || "") + "/api";
export const api = axios.create({ baseURL: base, timeout: 120000 });
export const exportUrl = (jobId: number, format: "pdf" | "csv" | "json") => `${base}/analysis/${jobId}/export?format=${format}`;

/** Extracts a user-safe message from an axios error (server never returns stack traces). */
export function errMsg(e: unknown): string {
  const ae = e as { response?: { data?: { detail?: unknown } }; message?: string };
  const d = ae?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x: { msg?: string }) => x.msg).filter(Boolean).join("; ");
  return ae?.message || "Request failed";
}
