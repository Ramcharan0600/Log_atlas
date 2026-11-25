/** @type {import('tailwindcss').Config} */
const v = (n) => `hsl(var(--${n}) / <alpha-value>)`;
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["class", '[data-theme="dark"]'],
  theme: { extend: {
    fontFamily: { sans: ["'Hanken Grotesk'", "system-ui", "sans-serif"], display: ["'Bricolage Grotesque'", "'Hanken Grotesk'", "sans-serif"], mono: ["'JetBrains Mono'", "ui-monospace", "monospace"] },
    // tighter corners everywhere: the default rounded-xl/2xl "friendly SaaS" look is deliberately dialed down
    borderRadius: { none: "0", sm: "2px", DEFAULT: "2px", md: "3px", lg: "4px", xl: "4px", "2xl": "6px", full: "9999px" },
    colors: { bg: v("bg"), panel: v("panel"), line: v("line"), ink: v("ink"), dim: v("dim"), accent: v("accent"), "on-accent": v("on-accent"), accent2: v("accent2"), crit: v("crit"), high: v("high"), med: v("med"), low: v("low") },
  } },
  plugins: [],
};
