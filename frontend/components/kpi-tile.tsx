import type { ReactNode } from "react";

type Props = {
  label: string;
  value: string;
  hint?: string;
  tone?: "neutral" | "good" | "warn" | "bad";
  trailing?: ReactNode;
};

const TONE: Record<NonNullable<Props["tone"]>, string> = {
  neutral: "text-ink",
  good: "text-accent",
  warn: "text-warning",
  bad: "text-danger",
};

export function KpiTile({ label, value, hint, tone = "neutral", trailing }: Props) {
  return (
    <article className="panel-sm flex flex-col gap-2 min-h-[112px]">
      <div className="flex items-start justify-between gap-2">
        <span className="text-[0.7rem] uppercase tracking-[0.14em] text-muted font-bold">
          {label}
        </span>
        {trailing}
      </div>
      <strong className={`text-3xl font-extrabold leading-none ${TONE[tone]}`}>{value}</strong>
      {hint ? <span className="text-xs text-muted">{hint}</span> : null}
    </article>
  );
}
