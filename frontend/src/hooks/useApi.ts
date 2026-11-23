import { useCallback, useEffect, useState } from "react";
import { api, errMsg } from "../services/api";

/** GET `path` (null = skip). Re-fetches when path changes; `reload()` forces a refresh. */
export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!path) { setData(null); return; }
    let live = true;
    setLoading(true); setError(null);
    api.get<T>(path).then((r) => live && setData(r.data)).catch((e) => live && setError(errMsg(e))).finally(() => live && setLoading(false));
    return () => { live = false; };
  }, [path, tick]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload };
}
