"use client";

import Link from "next/link";

import { EmptyState } from "@/components/empty-state";
import { KpiTile } from "@/components/kpi-tile";
import { PageHeader } from "@/components/page-header";
import { ScorecardRadar } from "@/components/scorecard-radar";
import { fetchVendorScorecard } from "@/lib/api";
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
