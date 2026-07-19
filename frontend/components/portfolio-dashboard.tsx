"use client";

import Link from "next/link";

import { Skeleton } from "@/components/skeleton";
import { fetchPortfolioSummary } from "@/lib/api";
import { useAsync } from "@/lib/use-async";
import type {
  PortfolioActivity,
  PortfolioCompletionBucket,
  PortfolioScheduleItem,
  PortfolioSummary,
} from "@/lib/types";

function moneyShort(v: number): string {
  if (v >= 1_000_000_000) return `$${(v / 1_000_000_000).toFixed(2)}B`;
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `$${(v / 1_000).toFixed(0)}k`;
  return `$${v.toFixed(0)}`;
}

function bucketTone(label: string): string {
  if (label.startsWith("Executing")) return "text-accent";
  if (label.startsWith("In progress")) return "text-warning";
  if (label.startsWith("Kickoff")) return "text-steady";
  return "text-muted";
}

function CompletionDonut({ pct }: { pct: number }) {
  const R = 38;
  const C = 2 * Math.PI * R;
  const dash = (Math.min(100, Math.max(0, pct)) / 100) * C;
  const tone = pct >= 70 ? "#57d4c0" : pct >= 25 ? "#f0b44c" : "#ff7575";
  return (
    <svg viewBox="0 0 100 100" className="w-28 h-28">
      <circle cx="50" cy="50" r={R} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="10" />
      <circle
        cx="50"
        cy="50"
        r={R}
        fill="none"
        stroke={tone}
        strokeWidth="10"
        strokeLinecap="round"
        strokeDasharray={`${dash} ${C - dash}`}
        transform="rotate(-90 50 50)"
        style={{ transition: "stroke-dasharray 0.6s ease" }}
      />
      <text x="50" y="48" textAnchor="middle" className="fill-ink" style={{ font: "bold 18px sans-serif" }}>
        {pct.toFixed(0)}%
      </text>
      <text x="50" y="62" textAnchor="middle" className="fill-muted" style={{ font: "9px sans-serif", letterSpacing: "0.1em" }}>
        AVG
      </text>
    </svg>
  );
}

function CountChip({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="flex flex-col">
      <div className="text-[0.6rem] uppercase tracking-[0.12em] text-muted font-bold">{label}</div>
      <div className="text-lg font-bold text-ink mt-0.5">{value}</div>
    </div>
  );
}

function Hero({ summary }: { summary: PortfolioSummary }) {
  const spendPct = summary.spend.committed_pct;
  return (
    <section className="panel animate-fade-up">
      <div className="flex flex-wrap items-center gap-6">
        <div className="flex items-center gap-4">
          <CompletionDonut pct={summary.average_completion_pct} />
          <div>
            <div className="text-[0.7rem] uppercase tracking-[0.14em] text-muted font-bold">Portfolio</div>
            <div className="text-2xl font-bold text-ink">Average completion</div>
            <div className="text-sm text-muted">Across {summary.counts.projects} active projects</div>
          </div>
        </div>

        <div className="hidden md:block w-px h-20 bg-line" />

        <div className="flex-1 grid grid-cols-2 md:grid-cols-5 gap-4 min-w-0">
          <CountChip label="Projects" value={summary.counts.projects} />
          <CountChip label="BOM lines" value={summary.counts.bom_lines} />
          <CountChip label="Open PRs" value={summary.spend.open_prs} />
          <CountChip label="Active RFQs" value={summary.counts.rfqs} />
          <CountChip label="POs" value={summary.counts.pos} />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-6 pt-6 border-t border-line">
        <SpendCard
          label="Total budget"
          primary={moneyShort(summary.spend.total_budget_usd)}
          hint={`${summary.counts.projects} projects`}
        />
        <SpendCard
          label="Committed"
          primary={moneyShort(summary.spend.total_committed_usd)}
          hint={`${spendPct.toFixed(1)}% of budget`}
          tone={spendPct >= 80 ? "warn" : "good"}
          progress={spendPct}
        />
        <SpendCard
          label="Awarded via sourcing"
          primary={moneyShort(summary.spend.total_awarded_usd)}
          hint={`From ${summary.counts.pos} PO${summary.counts.pos === 1 ? "" : "s"}`}
        />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-5">
        {summary.completion_buckets.map((b) => (
          <Bucket key={b.label} bucket={b} />
        ))}
      </div>
    </section>
  );
}

function SpendCard({
  label,
  primary,
  hint,
  tone = "neutral",
  progress,
}: {
  label: string;
  primary: string;
  hint?: string;
  tone?: "neutral" | "good" | "warn";
  progress?: number;
}) {
  const toneClass = tone === "warn" ? "text-warning" : tone === "good" ? "text-accent" : "text-ink";
  const barTone = tone === "warn" ? "bg-warning" : "bg-accent";
  return (
    <div>
      <div className="text-[0.65rem] uppercase tracking-[0.12em] text-muted font-bold">{label}</div>
      <div className={`text-2xl font-bold mt-1 ${toneClass}`}>{primary}</div>
      {hint ? <div className="text-xs text-muted mt-1">{hint}</div> : null}
      {progress !== undefined ? (
        <div className="h-1 mt-2 rounded-full bg-white/10 overflow-hidden">
          <div
            className={`h-full ${barTone} transition-[width] duration-500`}
            style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
          />
        </div>
      ) : null}
    </div>
  );
}

function Bucket({ bucket }: { bucket: PortfolioCompletionBucket }) {
  return (
    <div className="panel-sm flex items-center justify-between">
      <div>
        <div className={`text-xs font-bold ${bucketTone(bucket.label)}`}>{bucket.label}</div>
        <div className="text-[0.6rem] text-muted mt-0.5">Projects</div>
      </div>
      <div className="text-2xl font-bold text-ink">{bucket.count}</div>
    </div>
  );
}

function ScheduleRow({ item }: { item: PortfolioScheduleItem }) {
  const d = item.days_until;
  const tone = d < 0 ? "text-danger" : d <= 14 ? "text-danger" : d <= 30 ? "text-warning" : "text-ink";
  return (
    <Link
      href={`/projects/${item.project_id}`}
      className="flex items-center justify-between gap-3 py-2.5 px-3 -mx-3 rounded-lg hover:bg-white/[0.03] transition-colors"
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-[0.6rem] uppercase tracking-[0.1em] text-muted font-bold">{item.milestone_code}</span>
          {item.at_risk ? <span className="badge severity-high">AT RISK</span> : null}
        </div>
        <div className="font-bold text-ink text-sm truncate">{item.milestone_name}</div>
        <div className="text-xs text-muted truncate">{item.project_name}</div>
      </div>
      <div className="text-right shrink-0">
        <div className={`font-bold ${tone}`}>{d < 0 ? `${Math.abs(d)}d ago` : `in ${d}d`}</div>
        <div className="text-[0.65rem] text-muted">{item.completion_pct.toFixed(0)}% done</div>
      </div>
    </Link>
  );
}

function relativeTime(iso: string): string {
  const d = new Date(iso);
  const diffMs = Date.now() - d.getTime();
  const s = Math.floor(diffMs / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const days = Math.floor(h / 24);
  return `${days}d ago`;
}

function ActivityRow({ ev }: { ev: PortfolioActivity }) {
  return (
    <div className="flex items-start gap-3 py-2.5 px-3 -mx-3 rounded-lg hover:bg-white/[0.03] transition-colors">
      <div className="w-1.5 h-1.5 rounded-full bg-accent mt-2 shrink-0" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-[0.6rem] uppercase tracking-[0.1em] text-muted font-bold">{ev.entity_kind}</span>
          <span className="text-[0.6rem] text-muted">·</span>
          <span className="text-[0.6rem] uppercase tracking-[0.08em] text-accent font-bold">{ev.action}</span>
        </div>
        <div className="text-sm text-ink mt-0.5 truncate">{ev.summary}</div>
      </div>
      <div className="text-[0.65rem] text-muted shrink-0">{relativeTime(ev.at)}</div>
    </div>
  );
}

export function PortfolioDashboard() {
  const { data, loading, error } = useAsync(fetchPortfolioSummary, []);

  if (loading) return <DashboardSkeleton />;
  if (error)
    return <div className="panel-sm border-[rgba(255,117,117,0.3)] text-[#ff9d9d]">{error}</div>;
  if (!data) return null;

  return (
    <div className="space-y-5">
      <Hero summary={data} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <section className="panel animate-fade-up">
          <div className="flex items-center justify-between mb-3">
            <div>
              <div className="text-[0.7rem] uppercase tracking-[0.14em] text-muted font-bold">Schedule</div>
              <h3 className="m-0 text-base font-bold">At-risk + upcoming (14d)</h3>
            </div>
            <Link href="/projects" className="text-xs text-accent hover:text-accent-strong">
              All projects →
            </Link>
          </div>
          {data.schedule.at_risk.length === 0 && data.schedule.upcoming_14d.length === 0 ? (
            <div className="text-sm text-muted">Nothing critical in the next 14 days.</div>
          ) : (
            <div className="space-y-1">
              {data.schedule.at_risk.map((it) => (
                <ScheduleRow key={`r-${it.project_id}-${it.milestone_code}`} item={it} />
              ))}
              {data.schedule.upcoming_14d
                .filter(
                  (u) =>
                    !data.schedule.at_risk.find(
                      (r) => r.project_id === u.project_id && r.milestone_code === u.milestone_code,
                    ),
                )
                .map((it) => (
                  <ScheduleRow key={`u-${it.project_id}-${it.milestone_code}`} item={it} />
                ))}
            </div>
          )}
        </section>

        <section className="panel animate-fade-up">
          <div className="flex items-center justify-between mb-3">
            <div>
              <div className="text-[0.7rem] uppercase tracking-[0.14em] text-muted font-bold">Activity</div>
              <h3 className="m-0 text-base font-bold">Recent events</h3>
            </div>
            <Link href="/audit" className="text-xs text-accent hover:text-accent-strong">
              Audit log →
            </Link>
          </div>
          {data.activity.length === 0 ? (
            <div className="text-sm text-muted">
              No activity yet. Create a PR or issue an RFQ to see the trail.
            </div>
          ) : (
            <div className="space-y-1 max-h-[420px] overflow-y-auto pr-1">
              {data.activity.map((ev, i) => (
                <ActivityRow key={`${ev.at}-${i}`} ev={ev} />
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="space-y-5">
      <div className="panel">
        <div className="flex items-center gap-6">
          <Skeleton height={112} width={112} className="rounded-full" />
          <div className="flex-1 space-y-3">
            <Skeleton height={14} width="30%" />
            <Skeleton height={22} width="60%" />
            <Skeleton height={12} width="40%" />
          </div>
        </div>
        <div className="grid grid-cols-3 gap-4 mt-6">
          <Skeleton height={68} />
          <Skeleton height={68} />
          <Skeleton height={68} />
        </div>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Skeleton height={320} />
        <Skeleton height={320} />
      </div>
    </div>
  );
}
