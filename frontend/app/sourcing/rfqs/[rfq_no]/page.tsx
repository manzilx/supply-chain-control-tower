"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";

import { AddQuoteForm } from "@/components/add-quote-form";
import { AwardForm } from "@/components/award-form";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { RFQStatusBadge } from "@/components/sourcing-badges";
import { TbePanel } from "@/components/tbe-panel";
import { EntityTrail } from "@/components/traceability";
import { fetchQuoteComparison, fetchQuotes, fetchRfq } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatDate, formatMoney } from "@/lib/format-date";
import { useToast } from "@/lib/toast-context";
import { useAsync } from "@/lib/use-async";

export default function RFQPage({ params }: { params: { rfq_no: string } }) {
  const router = useRouter();
  const toast = useToast();
  const { hasPerm } = useAuth();
  const canAward = hasPerm("award", "create");

  const rfq = useAsync(() => fetchRfq(params.rfq_no), [params.rfq_no]);
  const quotes = useAsync(() => fetchQuotes(params.rfq_no), [params.rfq_no]);
  const comparison = useAsync(() => fetchQuoteComparison(params.rfq_no), [params.rfq_no]);
  const [awardReload, setAwardReload] = useState(0);

  const reloadEvaluations = useCallback(() => {
    comparison.reload();
    setAwardReload((k) => k + 1);
  }, [comparison]);

  const commercialWinner = comparison.data?.evaluations[0] ?? null;

  if (rfq.loading) return <EmptyState title="Loading RFQ..." />;
  if (rfq.error || !rfq.data) {
    return <div className="panel-sm border-[rgba(255,117,117,0.3)] text-[#ff9d9d]">{rfq.error ?? "RFQ not found"}</div>;
  }

  const data = rfq.data;
  const quotedVendors = new Set((quotes.data ?? []).map((q) => q.vendor));
  const awardable = data.status !== "awarded" && data.status !== "cancelled";

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="RFQ"
        title={`${data.rfq_no} · ${data.code}`}
        description={data.description}
        right={<RFQStatusBadge status={data.status} />}
      />

      <section className="panel grid grid-cols-2 md:grid-cols-4 gap-4">
        <Field label="PR">
          <div className="flex items-center gap-2 flex-wrap">
            <Link href={`/sourcing/prs/${data.pr_no}`} className="text-accent hover:underline font-mono text-xs">
              {data.pr_no}
            </Link>
            {data.project_id ? (
              <Link
                href={`/projects/${encodeURIComponent(data.project_id)}/process?stage=${
                  data.status === "evaluated" ? "technical_eval" : data.status === "quotes_received" ? "quotes" : "rfq"
                }`}
                className="text-[0.62rem] uppercase tracking-[0.1em] font-bold text-accent"
              >
                Process
              </Link>
            ) : null}
          </div>
        </Field>
        <Field label="Quantity">
          <span>{data.quantity} {data.uom}</span>
        </Field>
        <Field label="Issued">
          <span>{formatDate(data.issued_at)}</span>
        </Field>
        <Field label="Due">
          <span>{formatDate(data.due_at)}</span>
        </Field>
        <div className="col-span-2 md:col-span-4">
          <div className="text-[0.65rem] uppercase tracking-[0.12em] text-muted font-bold">Vendors invited</div>
          <div className="flex flex-wrap gap-2 mt-2">
            {data.vendors.map((v) => (
              <span
                key={v}
                className={[
                  "inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold",
                  quotedVendors.has(v) ? "bg-accent/15 text-accent" : "bg-white/5 text-muted",
                ].join(" ")}
              >
                {v} {quotedVendors.has(v) ? "· quoted" : "· pending"}
              </span>
            ))}
          </div>
          {data.notes ? <div className="mt-3 text-sm text-muted">{data.notes}</div> : null}
        </div>
      </section>

      <section className="panel space-y-3">
        <h2 className="m-0 text-lg font-bold">Quotes</h2>
        {quotes.loading ? (
          <EmptyState title="Loading quotes..." />
        ) : (quotes.data ?? []).length === 0 ? (
          <EmptyState title="No quotes yet" hint="Enter a quote below." />
        ) : (
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Vendor</th>
                  <th>Unit Price</th>
                  <th>Qty</th>
                  <th>Total</th>
                  <th>Lead Time</th>
                  <th>Incoterm</th>
                  <th>Valid</th>
                  <th>Notes</th>
                </tr>
              </thead>
              <tbody>
                {(quotes.data ?? []).map((q) => (
                  <tr key={q.quote_id}>
                    <td className="font-semibold text-ink">{q.vendor}</td>
                    <td>{formatMoney(q.unit_price_usd)}</td>
                    <td>{q.quantity}</td>
                    <td className="font-bold">{formatMoney(q.total_usd)}</td>
                    <td>{q.lead_time_days}d</td>
                    <td className="text-muted">{q.incoterm}</td>
                    <td className="text-muted">{q.validity_days}d</td>
                    <td className="text-xs text-muted max-w-md">{q.notes ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {awardable ? (
        <section className="panel space-y-4">
          <h2 className="m-0 text-lg font-bold">Add a Quote</h2>
          <AddQuoteForm
            rfqNo={params.rfq_no}
            vendors={data.vendors}
            onSaved={(reply) => {
              if (reply.status === "pending_approval") {
                toast.warn("Quote exceeds budget — sent for approval", { label: "View approvals", href: "/approvals" });
              } else {
                toast.success("Quote recorded");
              }
              quotes.reload();
              reloadEvaluations();
              rfq.reload();
            }}
          />
        </section>
      ) : null}

      <section className="panel space-y-3">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <h2 className="m-0 text-lg font-bold">Commercial Comparison</h2>
            <p className="text-xs text-muted mt-1 m-0">
              Price and lead-time ranking only — not the award recommendation. See TBE combined ranking below.
            </p>
          </div>
          {commercialWinner ? (
            <span className="chip text-muted">Commercial #1: {commercialWinner.vendor}</span>
          ) : null}
        </div>
        {comparison.loading ? (
          <EmptyState title="Evaluating..." />
        ) : !comparison.data || comparison.data.evaluations.length === 0 ? (
          <EmptyState title="Comparison needs quotes" />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Rank</th>
                    <th>Vendor</th>
                    <th>Total</th>
                    <th>Lead Time</th>
                    <th>Price Index</th>
                    <th>Lead Index</th>
                    <th>OTD</th>
                    <th>PPM</th>
                    <th>Reliability</th>
                    <th>Composite</th>
                    <th>Scope</th>
                  </tr>
                </thead>
                <tbody>
                  {comparison.data.evaluations.map((ev) => (
                    <tr key={ev.quote_id} className={ev.rank === 1 ? "bg-accent/5" : ""}>
                      <td className="font-bold text-ink">#{ev.rank}</td>
                      <td className="font-semibold text-ink">{ev.vendor}</td>
                      <td>{formatMoney(ev.total_usd)}</td>
                      <td>{ev.lead_time_days}d</td>
                      <td>{(ev.price_index * 100).toFixed(0)}%</td>
                      <td>{(ev.lead_time_index * 100).toFixed(0)}%</td>
                      <td className="text-muted">{ev.otd_pct !== null && ev.otd_pct !== undefined ? `${ev.otd_pct.toFixed(0)}%` : "—"}</td>
                      <td className="text-muted">{ev.quality_ppm ?? "—"}</td>
                      <td>{ev.reliability_score.toFixed(0)}</td>
                      <td className="font-bold">{ev.composite_score.toFixed(1)}</td>
                      <td className="text-xs text-muted">Commercial only</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {comparison.data.recommendation_rationale ? (
              <div className="panel-sm">
                <div className="section-title mb-2">Commercial rationale</div>
                <p className="text-sm text-ink leading-relaxed m-0">{comparison.data.recommendation_rationale}</p>
              </div>
            ) : null}

            {comparison.data.notes.length > 0 ? (
              <ul className="text-xs text-muted list-disc pl-5 space-y-1">
                {comparison.data.notes.map((n, i) => <li key={i}>{n}</li>)}
              </ul>
            ) : null}
          </>
        )}
      </section>

      {(quotes.data ?? []).length > 0 ? (
        <TbePanel
          rfqNo={params.rfq_no}
          quotes={quotes.data ?? []}
          onUpdated={reloadEvaluations}
        />
      ) : null}

      {awardable && canAward && comparison.data && comparison.data.evaluations.length > 0 ? (
        <section className="panel space-y-4">
          <div>
            <h2 className="m-0 text-lg font-bold">Award RFQ</h2>
            <p className="text-sm text-muted mt-1 m-0">
              Awards follow the TBE combined ranking (commercial + technical). Approval gating still applies for high-value awards.
            </p>
          </div>
          <AwardForm
            rfqNo={params.rfq_no}
            reloadKey={awardReload}
            onAwarded={(reply) => {
              if (reply.status === "pending_approval") {
                toast.warn(
                  `Awaiting ${reply.approval.required_role.replace("_", " ")} approval`,
                  { label: "View approvals", href: "/approvals" },
                );
                rfq.reload();
              } else {
                toast.success(
                  reply.po ? `Awarded — ${reply.po.po_no} drafted` : "RFQ awarded",
                  { label: "View POs", href: "/pos" },
                );
                router.push("/sourcing");
              }
            }}
          />
        </section>
      ) : null}

      <EntityTrail kind="rfq" id={params.rfq_no} />
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[0.65rem] uppercase tracking-[0.12em] text-muted font-bold">{label}</span>
      {children}
    </label>
  );
}
