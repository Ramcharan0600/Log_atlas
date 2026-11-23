/** @type {import('tailwindcss').Config} */
const v = (n) => `hsl(var(--${n}) / <alpha-value>)`;
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["class", '[data-theme="dark"]'],
  theme: { extend: {
    fontFamily: { sans: ["'IBM Plex Sans'", "system-ui", "sans-serif"], mono: ["'JetBrains Mono'", "monospace"] },
    colors: { bg: v("bg"), panel: v("panel"), line: v("line"), ink: v("ink"), dim: v("dim"), accent: v("accent"), accent2: v("accent2"), crit: v("crit"), high: v("high"), med: v("med"), low: v("low") },
  } },
  plugins: [],
};
