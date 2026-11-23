import { useEffect, useState } from "react";

type Theme = "dark" | "light";
const initial = (): Theme => {
  try { const s = localStorage.getItem("atlas.theme"); if (s === "light" || s === "dark") return s; } catch { /* ignore */ }
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
};

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(initial);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("atlas.theme", theme); } catch { /* ignore */ }
  }, [theme]);
  return { theme, toggle: () => setTheme((t) => (t === "dark" ? "light" : "dark")) };
}
