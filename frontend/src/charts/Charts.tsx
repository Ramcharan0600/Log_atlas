import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CHART } from "./theme";
import { fmtShort, SEV_COLORS } from "../utils/format";
import { Timeline } from "../types";

const tick = { fontSize: 10, fill: "hsl(var(--dim))", fontFamily: "JetBrains Mono, monospace" };
const tf = (s: string) => fmtShort(s);

export const VolumeChart = ({ data }: { data: Timeline["points"] }) => (
  <ResponsiveContainer height={260}>
    <AreaChart data={data}>
      <CartesianGrid stroke={CHART.grid} vertical={false} /><XAxis dataKey="t" tick={tick} tickFormatter={tf} minTickGap={40} /><YAxis tick={tick} />
      <Tooltip contentStyle={CHART.tooltip} labelFormatter={tf} /><Legend wrapperStyle={{ fontSize: 11 }} />
      <Area dataKey="total" name="All logs" stroke={CHART.axis} fill={CHART.grid} />
      <Area dataKey="errors" name="Errors" stroke={CHART.crit} fill={CHART.crit} fillOpacity={0.22} strokeWidth={1.5} />
    </AreaChart>
  </ResponsiveContainer>
);

export const ErrorRateChart = ({ data }: { data: Timeline["points"] }) => (
  <ResponsiveContainer height={200}>
    <LineChart data={data.map((p) => ({ ...p, rate: p.total ? +(100 * p.errors / p.total).toFixed(1) : 0 }))}>
      <CartesianGrid stroke={CHART.grid} vertical={false} /><XAxis dataKey="t" tick={tick} tickFormatter={tf} minTickGap={40} /><YAxis tick={tick} unit="%" />
      <Tooltip contentStyle={CHART.tooltip} labelFormatter={tf} /><Line dataKey="rate" name="Error rate %" stroke={CHART.crit} dot={false} />
    </LineChart>
  </ResponsiveContainer>
);

export const AnomalyTimeline = ({ data }: { data: Timeline["points"] }) => (
  <ResponsiveContainer height={200}>
    <BarChart data={data}>
      <CartesianGrid stroke={CHART.grid} vertical={false} /><XAxis dataKey="t" tick={tick} tickFormatter={tf} minTickGap={40} /><YAxis tick={tick} />
      <Tooltip contentStyle={CHART.tooltip} labelFormatter={tf} /><Bar dataKey="anomalies" name="Flagged logs" fill={CHART.high} />
    </BarChart>
  </ResponsiveContainer>
);

export const SeverityPie = ({ levels }: { levels: Record<string, number> }) => (
  <ResponsiveContainer height={260}>
    <PieChart>
      <Pie data={Object.entries(levels).map(([name, value]) => ({ name, value }))} dataKey="value" nameKey="name" innerRadius={62} outerRadius={95} paddingAngle={0} stroke="hsl(var(--panel))" strokeWidth={2}>
        {Object.keys(levels).map((k) => <Cell key={k} fill={SEV_COLORS[k] || CHART.axis} />)}
      </Pie>
      <Tooltip contentStyle={CHART.tooltip} /><Legend wrapperStyle={{ fontSize: 11 }} />
    </PieChart>
  </ResponsiveContainer>
);

export const HBar = ({ data, color = CHART.accent, name = "count" }: { data: { label: string; value: number }[]; color?: string; name?: string }) => (
  <ResponsiveContainer height={Math.max(160, data.length * 28 + 30)}>
    <BarChart data={data} layout="vertical" margin={{ left: 8 }}>
      <XAxis type="number" tick={tick} /><YAxis type="category" dataKey="label" width={120} tick={tick} />
      <Tooltip contentStyle={CHART.tooltip} /><Bar dataKey="value" name={name} fill={color} />
    </BarChart>
  </ResponsiveContainer>
);

export const TrendChart = ({ data }: { data: { t: string; count: number }[] }) => (
  <ResponsiveContainer height={160}>
    <AreaChart data={data}>
      <CartesianGrid stroke={CHART.grid} vertical={false} /><XAxis dataKey="t" tick={tick} tickFormatter={tf} minTickGap={40} /><YAxis tick={tick} />
      <Tooltip contentStyle={CHART.tooltip} labelFormatter={tf} /><Area dataKey="count" name="events" stroke={CHART.accent} fill={CHART.accent} fillOpacity={0.25} />
    </AreaChart>
  </ResponsiveContainer>
);

export const ClusterSizes = ({ data }: { data: { label: string; value: number; priority: string }[] }) => (
  <ResponsiveContainer height={Math.max(180, data.length * 30 + 30)}>
    <BarChart data={data} layout="vertical" margin={{ left: 8 }}>
      <XAxis type="number" tick={tick} /><YAxis type="category" dataKey="label" width={150} tick={tick} />
      <Tooltip contentStyle={CHART.tooltip} />
      <Bar dataKey="value" name="events">{data.map((d, i) => <Cell key={i} fill={{ Critical: CHART.crit, High: CHART.high, Medium: CHART.med, Low: CHART.low }[d.priority] || CHART.accent} />)}</Bar>
    </BarChart>
  </ResponsiveContainer>
);

export const MetricBars = ({ data, keys }: { data: Record<string, any>[]; keys: { key: string; name: string; color: string }[] }) => (
  <ResponsiveContainer height={260}>
    <BarChart data={data}>
      <CartesianGrid stroke={CHART.grid} vertical={false} /><XAxis dataKey="label" tick={tick} interval={0} angle={-15} textAnchor="end" height={60} /><YAxis tick={tick} />
      <Tooltip contentStyle={CHART.tooltip} /><Legend wrapperStyle={{ fontSize: 11 }} />
      {keys.map((k) => <Bar key={k.key} dataKey={k.key} name={k.name} fill={k.color} />)}
    </BarChart>
  </ResponsiveContainer>
);
