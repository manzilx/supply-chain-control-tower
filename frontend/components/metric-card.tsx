import type { WatchMetric } from "@/lib/types";

type Props = {
  metric: WatchMetric;
};

const DIR_COLOR: Record<WatchMetric["direction"], string> = {
  up: "text-danger",
  down: "text-accent",
  steady: "text-steady",
};

export function MetricCard({ metric }: Props) {
  return (
    <article className="panel-sm">
      <span className="block text-[0.7rem] uppercase tracking-[0.14em] text-muted font-bold mb-2">
        {metric.label}
      </span>
      <strong className="block text-2xl font-extrabold">{metric.value}</strong>
      <span className={`inline-flex mt-2 text-xs ${DIR_COLOR[metric.direction]}`}>
        {metric.direction}
      </span>
    </article>
  );
}
