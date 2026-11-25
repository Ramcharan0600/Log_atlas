/** Chart colours read the CSS theme variables so charts follow the dark/light toggle. */
const css = (n: string) => `hsl(var(--${n}))`;
export const CHART = {
  grid: "hsl(var(--line))", axis: "hsl(var(--dim))", accent: css("accent"), crit: css("crit"), high: css("high"), med: css("med"), low: css("low"),
  tooltip: { background: "hsl(var(--panel))", border: "1px solid hsl(var(--line))", fontSize: 11, color: "hsl(var(--ink))", borderRadius: 2, fontFamily: "JetBrains Mono, monospace", boxShadow: "none" } as React.CSSProperties,
};
