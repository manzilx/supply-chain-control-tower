"use client";

import {
  Bar,
  BarChart,
  Cell,
  Funnel,
  FunnelChart,
  LabelList,
  Legend,
  Pie,
  PieChart,
  PolarAngleAxis,
  RadialBar,
  RadialBarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  CartesianGrid,
  Line,
  LineChart,
} from "recharts";
import { motion, useMotionValue, useSpring, useTransform, useInView } from "framer-motion";
import { useEffect, useRef, useState, type ReactNode } from "react";

// ---------------------------------------------------------------- palette --

export const CHART_PALETTE = {
  accent:    "#57d4c0",   // primary teal
  gold:      "#f0b44c",
  sky:       "#7dc4ff",
  rose:      "#ff7a9a",
  violet:    "#b29bff",
  lime:      "#b8e54a",
  ember:     "#ff8552",
  slate:     "#7c8ea1",
  text:      "#9db0c1",
  textInk:   "#f1f5f9",
  grid:      "rgba(132, 165, 191, 0.18)",
  bg:        "#0c1728",
  bgCard:    "#172435",
};

export const SEVERITY_COLOR: Record<string, string> = {
  low:      "#7c8ea1",
  medium:   "#7dc4ff",
  high:     "#f0b44c",
  critical: "#ff7a9a",
};

export const URGENCY_COLOR: Record<string, string> = {
  ok:       "#57d4c0",
  watch:    "#7dc4ff",
  nudge:    "#f0b44c",
  escalate: "#ff7a9a",
};

export const PRIORITY_COLOR: Record<string, string> = {
  P1: "#ff7a9a",
  P2: "#f0b44c",
  P3: "#7dc4ff",
};

const SERIES = [CHART_PALETTE.accent, CHART_PALETTE.gold, CHART_PALETTE.sky, CHART_PALETTE.rose, CHART_PALETTE.violet, CHART_PALETTE.lime, CHART_PALETTE.ember, CHART_PALETTE.slate];

// ---------------------------------------------------------- animated number --

export function AnimatedNumber({
  value,
  format = (v) => Math.round(v).toLocaleString(),
  duration = 1.0,
  className = "",
}: {
  value: number;
  format?: (v: number) => string;
  duration?: number;
  className?: string;
}) {
  const mv = useMotionValue(0);
  const spring = useSpring(mv, { duration: duration * 1000, bounce: 0 });
  const display = useTransform(spring, (latest) => format(latest));
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: "-20% 0px" });
  useEffect(() => {
    if (inView) mv.set(value);
  }, [inView, value, mv]);
  return <motion.span ref={ref} className={className}>{display}</motion.span>;
}

// ----------------------------------------------------- motion-wrapped panel --

export function MotionPanel({
  children,
  delay = 0,
  className = "",
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, delay, ease: [0.22, 1, 0.36, 1] }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

// --------------------------------------------------------- chart container --

function ChartFrame({ title, subtitle, height = 240, children }: { title?: string; subtitle?: string; height?: number; children: ReactNode }) {
  return (
    <div className="panel">
      {title ? (
        <div className="flex items-baseline justify-between mb-2">
          <div>
            <div className="text-[0.65rem] uppercase tracking-[0.12em] text-accent font-bold">{title}</div>
            {subtitle ? <div className="text-xs text-muted mt-0.5">{subtitle}</div> : null}
          </div>
        </div>
      ) : null}
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          {children as any}
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// ----------------------------------------------------------------- tooltip --

const TooltipBox = (props: any) => {
  if (!props.active || !props.payload || props.payload.length === 0) return null;
  const items = props.payload as Array<{ name?: string; value?: number; payload?: any; color?: string }>;
  return (
    <div className="bg-[rgba(7,16,24,0.95)] border border-line rounded-md px-3 py-2 text-xs shadow-xl">
      {props.label ? <div className="text-ink font-semibold mb-1">{props.label}</div> : null}
      {items.map((it, i) => (
        <div key={i} className="flex items-center gap-2 text-muted">
          <span className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: it.color }} />
          <span>{it.name ?? it.payload?.name ?? ""}</span>
          <span className="text-ink font-mono ml-1">
            {typeof it.value === "number" ? it.value.toLocaleString() : String(it.value)}
          </span>
        </div>
      ))}
    </div>
  );
};

// ------------------------------------------------------------------- donut --

export function Donut({
  data,
  title,
  subtitle,
  height = 240,
  colorMap,
  centerLabel,
  centerValue,
}: {
  data: { name: string; value: number; color?: string }[];
  title?: string;
  subtitle?: string;
  height?: number;
  colorMap?: Record<string, string>;
  centerLabel?: string;
  centerValue?: string | number;
}) {
  return (
    <div className="panel">
      {title ? (
        <div className="mb-2">
          <div className="text-[0.65rem] uppercase tracking-[0.12em] text-accent font-bold">{title}</div>
          {subtitle ? <div className="text-xs text-muted mt-0.5">{subtitle}</div> : null}
        </div>
      ) : null}
      <div className="relative" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              nameKey="name"
              innerRadius="60%"
              outerRadius="85%"
              paddingAngle={2}
              stroke="none"
              animationDuration={900}
              animationBegin={100}
              isAnimationActive
            >
              {data.map((d, i) => (
                <Cell
                  key={i}
                  fill={d.color ?? colorMap?.[d.name] ?? SERIES[i % SERIES.length]}
                />
              ))}
            </Pie>
            <Tooltip content={<TooltipBox />} />
            <Legend
              verticalAlign="bottom"
              iconType="circle"
              wrapperStyle={{ fontSize: 11, color: CHART_PALETTE.text }}
            />
          </PieChart>
        </ResponsiveContainer>
        {centerValue !== undefined ? (
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center -translate-y-3">
            <div className="text-2xl font-bold text-ink">
              {typeof centerValue === "number" ? <AnimatedNumber value={centerValue} /> : centerValue}
            </div>
            {centerLabel ? (
              <div className="text-[0.6rem] uppercase tracking-[0.14em] text-muted mt-0.5">{centerLabel}</div>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

// -------------------------------------------------------------- gauge ----

export function Gauge({
  value,
  max = 100,
  title,
  subtitle,
  height = 220,
  tone,
  unit = "/100",
}: {
  value: number;
  max?: number;
  title?: string;
  subtitle?: string;
  height?: number;
  tone?: "good" | "warn" | "bad" | "neutral";
  unit?: string;
}) {
  const color =
    tone === "bad"  ? CHART_PALETTE.rose :
    tone === "warn" ? CHART_PALETTE.gold :
    tone === "good" ? CHART_PALETTE.accent :
    value >= 80 ? CHART_PALETTE.rose : value >= 60 ? CHART_PALETTE.gold : value >= 30 ? CHART_PALETTE.sky : CHART_PALETTE.accent;
  const data = [{ name: "score", value: Math.min(value, max), fill: color }];
  return (
    <div className="panel">
      {title ? (
        <div className="mb-2">
          <div className="text-[0.65rem] uppercase tracking-[0.12em] text-accent font-bold">{title}</div>
          {subtitle ? <div className="text-xs text-muted mt-0.5">{subtitle}</div> : null}
        </div>
      ) : null}
      <div className="relative" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <RadialBarChart
            data={data}
            innerRadius="68%"
            outerRadius="92%"
            startAngle={210}
            endAngle={-30}
            barSize={20}
          >
            <PolarAngleAxis type="number" domain={[0, max]} tick={false} />
            <RadialBar dataKey="value" cornerRadius={10} background={{ fill: "rgba(132,165,191,0.12)" }} animationDuration={900} />
          </RadialBarChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center -translate-y-1">
          <div className="text-3xl font-bold" style={{ color }}>
            <AnimatedNumber value={value} />
          </div>
          <div className="text-[0.6rem] uppercase tracking-[0.14em] text-muted mt-1">{unit}</div>
        </div>
      </div>
    </div>
  );
}

// ----------------------------------------------------- horizontal bar chart --

export function HBar({
  data,
  title,
  subtitle,
  height = 240,
  valueFormat,
  color,
}: {
  data: { name: string; value: number; color?: string }[];
  title?: string;
  subtitle?: string;
  height?: number;
  valueFormat?: (v: number) => string;
  color?: string;
}) {
  return (
    <ChartFrame title={title} subtitle={subtitle} height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, left: 4, bottom: 4 }}>
        <CartesianGrid stroke={CHART_PALETTE.grid} horizontal={false} />
        <XAxis type="number" tick={{ fill: CHART_PALETTE.text, fontSize: 11 }} stroke={CHART_PALETTE.grid} tickFormatter={valueFormat} />
        <YAxis dataKey="name" type="category" tick={{ fill: CHART_PALETTE.textInk, fontSize: 12 }} width={140} stroke={CHART_PALETTE.grid} />
        <Tooltip content={<TooltipBox />} cursor={{ fill: "rgba(132,165,191,0.06)" }} />
        <Bar dataKey="value" radius={[0, 4, 4, 0]} animationDuration={900}>
          {data.map((d, i) => (
            <Cell key={i} fill={d.color ?? color ?? SERIES[i % SERIES.length]} />
          ))}
        </Bar>
      </BarChart>
    </ChartFrame>
  );
}

// ------------------------------------------------------- vertical / grouped --

export function VBar({
  data,
  series,
  title,
  subtitle,
  height = 260,
  stacked,
  valueFormat,
}: {
  data: any[];
  series: { key: string; name: string; color?: string }[];
  title?: string;
  subtitle?: string;
  height?: number;
  stacked?: boolean;
  valueFormat?: (v: number) => string;
}) {
  return (
    <ChartFrame title={title} subtitle={subtitle} height={height}>
      <BarChart data={data} margin={{ top: 4, right: 16, left: 4, bottom: 4 }}>
        <CartesianGrid stroke={CHART_PALETTE.grid} vertical={false} />
        <XAxis dataKey="name" tick={{ fill: CHART_PALETTE.text, fontSize: 11 }} stroke={CHART_PALETTE.grid} interval={0} angle={-15} textAnchor="end" height={50} />
        <YAxis tick={{ fill: CHART_PALETTE.text, fontSize: 11 }} stroke={CHART_PALETTE.grid} tickFormatter={valueFormat} />
        <Tooltip content={<TooltipBox />} cursor={{ fill: "rgba(132,165,191,0.06)" }} />
        <Legend wrapperStyle={{ fontSize: 11, color: CHART_PALETTE.text }} />
        {series.map((s, i) => (
          <Bar
            key={s.key}
            dataKey={s.key}
            name={s.name}
            stackId={stacked ? "x" : undefined}
            fill={s.color ?? SERIES[i % SERIES.length]}
            radius={stacked ? 0 : [4, 4, 0, 0]}
            animationDuration={900}
            animationBegin={i * 60}
          />
        ))}
      </BarChart>
    </ChartFrame>
  );
}

// ------------------------------------------------------- shipment funnel  --

export function StageFunnel({
  data,
  title,
  height = 280,
}: {
  data: { name: string; value: number; color?: string }[];
  title?: string;
  height?: number;
}) {
  return (
    <ChartFrame title={title} height={height}>
      <FunnelChart>
        <Tooltip content={<TooltipBox />} />
        <Funnel dataKey="value" data={data} isAnimationActive animationDuration={900}>
          {data.map((d, i) => (
            <Cell key={i} fill={d.color ?? SERIES[i % SERIES.length]} />
          ))}
          <LabelList position="right" fill={CHART_PALETTE.textInk} stroke="none" dataKey="name" style={{ fontSize: 11 }} />
        </Funnel>
      </FunnelChart>
    </ChartFrame>
  );
}

// ------------------------------------------------------------- sparkline ---

export function Sparkline({
  data,
  color = CHART_PALETTE.accent,
  height = 40,
  width = 120,
}: {
  data: number[];
  color?: string;
  height?: number;
  width?: number;
}) {
  const series = data.map((v, i) => ({ x: i, y: v }));
  return (
    <div style={{ width, height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={series} margin={{ top: 2, right: 2, left: 2, bottom: 2 }}>
          <Line type="monotone" dataKey="y" stroke={color} strokeWidth={2} dot={false} isAnimationActive animationDuration={800} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ----------------------------------------------------- animated KPI tile  --

export function AnimatedKpiTile({
  label,
  value,
  hint,
  tone = "neutral",
  delay = 0,
  prefix = "",
  suffix = "",
  format = (v) => Math.round(v).toLocaleString(),
  spark,
}: {
  label: string;
  value: number;
  hint?: string;
  tone?: "good" | "warn" | "bad" | "neutral";
  delay?: number;
  prefix?: string;
  suffix?: string;
  format?: (v: number) => string;
  spark?: number[];
}) {
  const toneCls = {
    good: "text-emerald-300",
    warn: "text-amber-300",
    bad:  "text-rose-300",
    neutral: "text-ink",
  }[tone];
  const sparkColor = {
    good: CHART_PALETTE.accent,
    warn: CHART_PALETTE.gold,
    bad:  CHART_PALETTE.rose,
    neutral: CHART_PALETTE.sky,
  }[tone];
  return (
    <MotionPanel delay={delay}>
      <div className="panel-sm flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[0.62rem] uppercase tracking-[0.12em] text-muted font-bold mb-1">{label}</div>
          <div className={`text-2xl font-bold leading-tight ${toneCls}`}>
            {prefix}<AnimatedNumber value={value} format={format} />{suffix}
          </div>
          {hint ? <div className="text-[0.65rem] text-muted mt-1">{hint}</div> : null}
        </div>
        {spark && spark.length > 1 ? (
          <div className="shrink-0">
            <Sparkline data={spark} color={sparkColor} width={80} height={36} />
          </div>
        ) : null}
      </div>
    </MotionPanel>
  );
}

// ------------------------------------------------------- status flip badge --

/**
 * A badge that briefly pulses when its label changes. Use for live status
 * transitions (e.g. SAP submit, expedite urgency).
 */
export function FlipBadge({
  label,
  className = "",
}: {
  label: string;
  className?: string;
}) {
  const [prev, setPrev] = useState(label);
  const [pulse, setPulse] = useState(false);
  useEffect(() => {
    if (label !== prev) {
      setPulse(true);
      setPrev(label);
      const t = setTimeout(() => setPulse(false), 700);
      return () => clearTimeout(t);
    }
  }, [label, prev]);
  return (
    <motion.span
      key={label}
      initial={pulse ? { scale: 0.92, opacity: 0.6 } : false}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      className={className}
    >
      {label}
    </motion.span>
  );
}
