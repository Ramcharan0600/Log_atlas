import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { api, errMsg } from "../services/api";
import { Job, Page } from "../types";

type Ctx = { jobs: Job[]; jobId: number | null; job?: Job; setJobId: (id: number) => void; refresh: () => Promise<void>; loaded: boolean; connError: string | null };
const JobCtx = createContext<Ctx>({ jobs: [], jobId: null, setJobId: () => {}, refresh: async () => {}, loaded: false, connError: null });

/** Pause between the end of one job-list request and the start of the next. */
const POLL_MS = 4000;

/** No response at all (busy, restarting or offline server) gets a plain explanation; otherwise show the server's own message. */
const connMessage = (e: unknown) => ((e as { response?: { status?: number } })?.response?.status ?? 503) >= 502 ? "The server is busy or unreachable." : errMsg(e);

const read = () => { try { return Number(localStorage.getItem("atlas.jobId")) || null; } catch { return null; } };

export function JobProvider({ children }: { children: ReactNode }) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobId, setId] = useState<number | null>(read);
  const [loaded, setLoaded] = useState(false);
  const setJobId = useCallback((id: number) => { try { localStorage.setItem("atlas.jobId", String(id)); } catch { /* storage unavailable */ } setId(id); }, []);
  const [connError, setConnError] = useState<string | null>(null);
  const refresh = useCallback(async () => {
    try {
      const { data } = await api.get<Page<Job>>("/analysis", { params: { page_size: 50 } });
      setJobs(data.items);
      setId((cur) => (cur && data.items.some((j) => j.id === cur) ? cur : data.items.find((j) => j.status === "completed")?.id ?? null));
      setConnError(null);
    } catch (e) { setConnError(connMessage(e)); throw e; } finally { setLoaded(true); }
  }, []);
  useEffect(() => { refresh().catch(() => {}); }, [refresh]);
  // poll while something is queued/running, or while retrying after a failure; the next request waits for the previous one
  const poll = connError !== null || jobs.some((j) => j.status === "queued" || j.status === "running");
  useEffect(() => {
    if (!poll) return;
    let live = true;
    let t: ReturnType<typeof setTimeout>;
    const next = () => { t = setTimeout(() => refresh().catch(() => {}).finally(() => { if (live) next(); }), POLL_MS); };
    next();
    return () => { live = false; clearTimeout(t); };
  }, [poll, refresh]);
  return <JobCtx.Provider value={{ jobs, jobId, job: jobs.find((j) => j.id === jobId), setJobId, refresh, loaded, connError }}>{children}</JobCtx.Provider>;
}
export const useJob = () => useContext(JobCtx);
