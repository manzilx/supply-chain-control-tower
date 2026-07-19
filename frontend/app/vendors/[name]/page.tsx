"use client";

import Link from "next/link";

import { EmptyState } from "@/components/empty-state";
import { ExplainButton } from "@/components/explain-button";
import { KpiTile } from "@/components/kpi-tile";
import { PageHeader } from "@/components/page-header";
import { ScorecardRadar } from "@/components/scorecard-radar";
import { fetchVendorBriefing, fetchVendorScorecard } from "@/lib/api";
import { formatMoney } from "@/lib/format-date";
import { useAsync } from "@/lib/use-async";
import type { Grade } from "@/lib/types";

const GRADE_TONE: Record<Grade, "good" | "neutral" | "warn" | "bad"> = {
  A: "good",
  B: "good",
  C: "neutral",
  D: "warn",
  F: "bad",
};

export default function VendorDetailPage({ params }: { params: { name: string } }) {
  const name = decodeURIComponent(params.name);
  const { data, loading, error } = useAsync(() => fetchVendorScorecard(name), [name]);
  const briefing = useAsync(() => fetchVendorBriefing(name), [name]);

  if (loading) return <EmptyState title="Loading vendor..." />;
  if (error || !data) {
    return <div className="panel-sm border-[rgba(255,117,117,0.3)] text-[#ff9d9d]">{error ?? "Vendor not found"}</div>;
  }

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Vendor"
        title={data.vendor}
        description={`${data.category} · ${data.country} · lead time ${data.lead_time_days} days`}
        right={
          <Link href="/vendors" className="btn btn-secondary text-sm">
            ← All vendors
          </Link>
        }
      />

      {briefing.data ? (
        <section className="rounded-2xl border border-accent/30 bg-accent/[0.05] p-5">
          <div className="flex items-baseline justify-between gap-3 mb-2">
            <div className="text-[0.65rem] uppercase tracking-[0.14em] text-accent font-bold">
              AI risk briefing
            </div>
            <span className="text-[0.6rem] uppercase tracking-[0.14em] text-muted">
              via {briefing.data.source}
            </span>
          </div>
          <h3 className="text-base font-semibold text-ink mb-2">{briefing.data.headline}</h3>
          <div className="text-sm text-ink/90 whitespace-pre-wrap leading-relaxed mb-3">
            {briefing.data.body}
          </div>
          {briefing.data.watchlist.length > 0 ? (
            <div>
              <div className="text-[0.6rem] uppercase tracking-[0.14em] text-muted font-bold mb-1">
                Watchlist
              </div>
              <ul className="list-disc pl-5 space-y-0.5 text-xs text-ink">
                {briefing.data.watchlist.map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            </div>
          ) : null}
        </section>
      ) : briefing.loading ? (
        <div className="text-sm text-muted">Generating risk briefing…</div>
      ) : null}

      <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiTile
          label="Composite Score"
          value={`${data.composite_score}`}
          hint={`Grade ${data.composite_grade}`}
          tone={GRADE_TONE[data.composite_grade]}
        />
        <KpiTile
          label="Annual Spend"
          value={formatMoney(data.annual_spend_usd)}
        />
        <KpiTile
          label="Category Share"
          value={`${data.concentration_pct.toFixed(0)}%`}
          tone={data.concentration_pct >= 70 ? "warn" : "neutral"}
        />
        <KpiTile
          label="Alternates"
          value={String(data.approved_alternatives)}
          tone={data.approved_alternatives === 0 ? "bad" : "neutral"}
          hint={data.single_source_exposure ? "Single-source exposure" : undefined}
        />
      </section>

      <details className="panel-sm">
        <summary className="cursor-pointer flex items-center justify-between select-none">
          <div>
            <div className="text-[0.65rem] uppercase tracking-[0.14em] text-muted font-bold">How this is scored</div>
            <div className="text-sm text-ink mt-0.5">
              6-axis composite — click to see what data feeds each one and how to influence it.
            </div>
          </div>
          <span className="text-xs text-accent">expand</span>
        </summary>
        <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
          <ScoringAxis
            label="Delivery · 25%"
            inputs="on_time_delivery_pct"
            rubric="≥97 → A · ≥90 → B · <80 → D/F"
            color="text-accent"
          />
          <ScoringAxis
            label="Quality · 20%"
            inputs="quality_ppm (lower = better)"
            rubric="<300 PPM → A · <800 → B · >2000 → D/F"
            color="text-accent"
          />
          <ScoringAxis
            label="Price · 15%"
            inputs="annual_spend_usd vs category total"
            rubric="Benchmarked relative to peers in same category"
            color="text-warning"
          />
          <ScoringAxis
            label="Responsiveness · 15%"
            inputs="risk_flags count + approved_alternatives"
            rubric="Fewer flags + ≥1 alternate → A. 0 alternates penalty."
            color="text-steady"
          />
          <ScoringAxis
            label="Claims · 10%"
            inputs="quality_ppm + 'late NCR' flags"
            rubric="Derived from quality + open-NCR signals"
            color="text-steady"
          />
          <ScoringAxis
            label="Risk · 15%"
            inputs="risk_flags + single-source exposure"
            rubric="Each flag ≈ -18. No alternates = -25 baseline."
            color="text-danger"
          />
        </div>
        <div className="text-xs text-muted mt-4">
          To add or update a vendor, go to <Link href="/vendors" className="text-accent">All vendors → + Add vendor</Link>.
          The composite score recomputes the moment you save.
        </div>
      </details>

      <section className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        <div className="panel">
          <h2 className="m-0 text-lg font-bold mb-2">Scorecard</h2>
          <ScorecardRadar components={data.components} />
        </div>

        <div className="panel">
          <h2 className="m-0 text-lg font-bold mb-3">Components</h2>
          <div className="space-y-2">
            {data.components.map((c) => (
              <article key={c.dimension} className="panel-sm">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-bold text-ink">{c.label}</div>
                    <div className="text-xs text-muted">{c.value}</div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="text-2xl font-extrabold">{c.score}</div>
                    <div className="text-xs font-bold text-muted">Grade {c.grade}</div>
                  </div>
                </div>
                <p className="text-sm text-muted mt-2 leading-relaxed">{c.note}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      {data.flags.length > 0 ? (
        <section className="panel">
          <h2 className="m-0 text-lg font-bold mb-3">Active Flags</h2>
          <div className="flex flex-wrap gap-2">
            {data.flags.map((f) => (
              <span key={f} className="badge severity-medium">{f}</span>
            ))}
          </div>
        </section>
      ) : null}

      <section className="panel">
        <h2 className="m-0 text-lg font-bold mb-3">Approved Alternates</h2>
        {data.alternates.length === 0 ? (
          <EmptyState
            title="No alternates on file"
            hint="Qualify a second source to reduce single-source exposure."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Vendor</th>
                  <th>Country</th>
                  <th>Score</th>
                  <th>OTD</th>
                  <th>Lead Time</th>
                  <th>Why</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {data.alternates.map((a) => (
                  <tr key={a.name}>
                    <td className="font-semibold text-ink">{a.name}</td>
                    <td className="text-muted">{a.country}</td>
                    <td className="font-bold">{a.composite_score}</td>
                    <td>{a.on_time_delivery_pct.toFixed(0)}%</td>
                    <td>{a.lead_time_days}d</td>
                    <td className="text-xs text-muted max-w-md">{a.reason}</td>
                    <td>
                      <Link
                        className="btn btn-secondary text-xs"
                        href={`/vendors/${encodeURIComponent(a.name)}`}
                      >
                        View
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function ScoringAxis({
  label,
  inputs,
  rubric,
  color,
}: {
  label: string;
  inputs: string;
  rubric: string;
  color: string;
}) {
  return (
    <div className="panel-sm">
      <div className={`text-xs font-bold ${color}`}>{label}</div>
      <div className="text-[0.65rem] uppercase tracking-[0.1em] text-muted font-bold mt-2">Inputs</div>
      <div className="text-xs text-ink"><code>{inputs}</code></div>
      <div className="text-[0.65rem] uppercase tracking-[0.1em] text-muted font-bold mt-1.5">Rubric</div>
      <div className="text-xs text-muted">{rubric}</div>
    </div>
  );
}
