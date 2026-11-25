import { createContext, ReactNode, useCallback, useContext, useState } from "react";
import { CheckCircle2, XCircle, X } from "lucide-react";

type Toast = { id: number; kind: "ok" | "err"; text: string };
const Ctx = createContext<{ notify: (text: string, kind?: "ok" | "err") => void }>({ notify: () => {} });
let seq = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const dismiss = (id: number) => setItems((t) => t.filter((x) => x.id !== id));
  const notify = useCallback((text: string, kind: "ok" | "err" = "ok") => {
    const id = ++seq;
    setItems((t) => [...t, { id, kind, text }]);
    setTimeout(() => dismiss(id), 5000);
  }, []);
  return (
    <Ctx.Provider value={{ notify }}>
      {children}
      <div className="fixed bottom-4 right-4 z-[60] space-y-2 w-[min(92vw,360px)]" role="status" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`card !p-3 flex gap-2 items-start text-sm ${t.kind === "err" ? "border-crit/60" : "border-accent/60"}`}>
            {t.kind === "err" ? <XCircle size={16} className="text-crit mt-0.5 shrink-0" /> : <CheckCircle2 size={16} className="text-accent mt-0.5 shrink-0" />}
            <span className="flex-1">{t.text}</span>
            <button aria-label="Dismiss" onClick={() => dismiss(t.id)}><X size={14} className="text-dim" /></button>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}
export const useToast = () => useContext(Ctx);
