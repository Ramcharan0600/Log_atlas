import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { api } from "../services/api";
import { Job, Page } from "../types";

type Ctx = { jobs: Job[]; jobId: number | null; job?: Job; setJobId: (id: number) => void; refresh: () => Promise<void>; loaded: boolean };
const JobCtx = createContext<Ctx>({ jobs: [], jobId: null, setJobId: () => {}, refresh: async () => {}, loaded: false });

const read = () => { try { return Number(localStorage.getItem("atlas.jobId")) || null; } catch { return null; } };

export function JobProvider({ children }: { children: ReactNode }) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobId, setId] = useState<number | null>(read);
  const [loaded, setLoaded] = useState(false);
  const setJobId = useCallback((id: number) => { try { localStorage.setItem("atlas.jobId", String(id)); } catch { /* storage unavailable */ } setId(id); }, []);
  const refresh = useCallback(async () => {
    try {
      const { data } = await api.get<Page<Job>>("/analysis", { params: { page_size: 50 } });
      setJobs(data.items);
      setId((cur) => (cur && data.items.some((j) => j.id === cur) ? cur : data.items.find((j) => j.status === "completed")?.id ?? null));
    } finally { setLoaded(true); }
  }, []);
  useEffect(() => { refresh().catch(() => setLoaded(true)); }, [refresh]);
  // poll while something is queued/running
  const busy = jobs.some((j) => j.status === "queued" || j.status === "running");
  useEffect(() => { if (!busy) return; const t = setInterval(() => refresh().catch(() => {}), 1500); return () => clearInterval(t); }, [busy, refresh]);
  return <JobCtx.Provider value={{ jobs, jobId, job: jobs.find((j) => j.id === jobId), setJobId, refresh, loaded }}>{children}</JobCtx.Provider>;
}
export const useJob = () => useContext(JobCtx);
