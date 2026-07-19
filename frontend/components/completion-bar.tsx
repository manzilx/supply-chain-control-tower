import type { ProjectProgress } from "@/lib/types";

/** Colour by completion band — red <25, amber 25-70, green >70. */
function toneFor(pct: number): { bar: string; text: string } {
  if (pct >= 70) return { bar: "bg-accent", text: "text-accent" };
  if (pct >= 25) return { bar: "bg-warning", text: "text-warning" };
  return { bar: "bg-danger", text: "text-danger" };
}

export function CompletionBar({
  progress,
  showBreakdown = false,
}: {
  progress: ProjectProgress;
  showBreakdown?: boolean;
}) {
  const pct = progress.completion_pct;
  const tone = toneFor(pct);
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-[0.65rem] uppercase tracking-[0.12em] text-muted font-bold">
          Completion
        </span>
        <span className={`text-sm font-bold ${tone.text}`}>{pct.toFixed(0)}%</span>
      </div>
      <div className="h-2 w-full rounded-full bg-white/10 overflow-hidden">
        <div
          className={`h-full rounded-full ${tone.bar} transition-[width] duration-500`}
          style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
        />
      </div>
      {showBreakdown ? (
        <div className="grid grid-cols-3 gap-2 mt-3 text-xs">
          <Segment
            label="Milestones"
            pct={progress.milestones_pct}
            detail={`${progress.milestones_passed}/${progress.milestones_total} passed`}
          />
          <Segment
            label="BOM delivered"
            pct={progress.bom_delivered_pct}
            detail={`${progress.bom_delivered}/${progress.bom_total} lines`}
          />
          <Segment
            label="Spend committed"
            pct={progress.spend_committed_pct}
            detail={moneyShort(progress.committed_value_usd)}
          />
        </div>
      ) : null}
    </div>
  );
}

function Segment({ label, pct, detail }: { label: string; pct: number; detail: string }) {
  return (
    <div>
      <div className="text-[0.6rem] uppercase tracking-[0.1em] text-muted font-bold">{label}</div>
      <div className="text-ink font-semibold mt-0.5">{pct.toFixed(0)}%</div>
      <div className="text-muted">{detail}</div>
    </div>
  );
}

function moneyShort(v: number): string {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `$${(v / 1_000).toFixed(0)}k`;
  return `$${v.toFixed(0)}`;
}
