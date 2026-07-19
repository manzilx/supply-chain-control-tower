"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useMemo, useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { RFQStatusBadge } from "@/components/sourcing-badges";
import { TbePanel } from "@/components/tbe-panel";
import { EntityTrail } from "@/components/traceability";
import {
  addQuote,
  awardRfq,
  fetchQuoteComparison,
  fetchQuotes,
  fetchRfq,
  fetchTbe,
} from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatDate, formatMoney } from "@/lib/format-date";
import { useToast } from "@/lib/toast-context";
import type { CombinedEvaluation, CreateQuoteRequest, Incoterm, TBE } from "@/lib/types";
import { useAsync } from "@/lib/use-async";

const INCOTERMS: Incoterm[] = ["EXW", "FCA", "FOB", "CIF", "CIP", "DAP", "DDP"];

type TbeAwardState =
  | { mode: "tbe"; target: CombinedEvaluation; rationale: string | null }
  | { mode: "blocked"; reason: string; target?: CombinedEvaluation }
  | { mode: "not_run" }
  | { mode: "no_data" };

function resolveTbeAward(tbe: TBE | null | undefined): TbeAwardState {
  if (!tbe || tbe.combined.length === 0) return { mode: "no_data" };
  if (tbe.technical_evaluations.length === 0) return { mode: "not_run" };

  const leader =
    tbe.combined.find((c) => c.combined_rank === 1) ??
    [...tbe.combined].sort((a, b) => a.combined_rank - b.combined_rank)[0];

  if (leader.disqualified) {
    return {
      mode: "blocked",
      target: leader,
      reason: `Combined #1 (${leader.vendor}) is disqualified on mandatory technical criteria. Resolve the evaluation before awarding.`,
    };
  }

  return {
    mode: "tbe",
    target: leader,
    rationale: tbe.recommendation_rationale ?? null,
  };
}

export default function RFQPage({ params }: { params: { rfq_no: string } }) {
  const router = useRouter();
  const toast = useToast();
  const { hasPerm } = useAuth();
  const canAward = hasPerm("award", "create");

  const rfq = useAsync(() => fetchRfq(params.rfq_no), [params.rfq_no]);
  const quotes = useAsync(() => fetchQuotes(params.rfq_no), [params.rfq_no]);
  const comparison = useAsync(() => fetchQuoteComparison(params.rfq_no), [params.rfq_no]);
  const tbe = useAsync(() => fetchTbe(params.rfq_no), [params.rfq_no]);

  const reloadEvaluations = useCallback(() => {
    comparison.reload();
    tbe.reload();
  }, [comparison, tbe]);

  const tbeAward = useMemo(() => resolveTbeAward(tbe.data), [tbe.data]);
  const commercialWinner = comparison.data?.evaluations[0] ?? null;

  const [quoteDraft, setQuoteDraft] = useState<Partial<CreateQuoteRequest>>({
    incoterm: "CIP",
    validity_days: 30,
  });
  const [selectedVendor, setSelectedVendor] = useState<string>("");
  const [savingQuote, setSavingQuote] = useState(false);
  const [quoteErr, setQuoteErr] = useState<string | null>(null);

  const [awardRationale, setAwardRationale] = useState("");
  const [awarding, setAwarding] = useState(false);
  const [awardErr, setAwardErr] = useState<string | null>(null);

  async function handleAddQuote(e: React.FormEvent) {
    e.preventDefault();
    if (!quoteDraft.vendor && !selectedVendor) {
      setQuoteErr("Pick a vendor.");
      return;
    }
    if (!quoteDraft.unit_price_usd || !quoteDraft.lead_time_days) {
      setQuoteErr("Unit price and lead time are required.");
      return;
    }
    setSavingQuote(true);
    setQuoteErr(null);
    try {
      const reply = await addQuote(params.rfq_no, {
        vendor: (quoteDraft.vendor || selectedVendor) as string,
        unit_price_usd: Number(quoteDraft.unit_price_usd),
        lead_time_days: Number(quoteDraft.lead_time_days),
        incoterm: quoteDraft.incoterm ?? "CIP",
        validity_days: Number(quoteDraft.validity_days ?? 30),
        notes: quoteDraft.notes ?? null,
      });
      setQuoteDraft({ incoterm: "CIP", validity_days: 30 });
      setSelectedVendor("");
      if (reply.status === "pending_approval") {
        toast.warn("Quote exceeds budget — sent for approval", { label: "View approvals", href: "/approvals" });
      } else {
        toast.success("Quote recorded");
      }
      quotes.reload();
      comparison.reload();
      tbe.reload();
      rfq.reload();
    } catch (err) {
      setQuoteErr(err instanceof Error ? err.message : "Failed to save quote");
    } finally {
      setSavingQuote(false);
    }
  }

  async function handleAward(
    quoteId: string,
    opts?: { confirmMessage?: string; rationale?: string },
  ) {
    if (!rfq.data) return;
    const message = opts?.confirmMessage ?? "Award this quote and auto-draft a PO?";
    if (!confirm(message)) return;
    setAwarding(true);
    setAwardErr(null);
    try {
      const reply = await awardRfq(params.rfq_no, {
        quote_id: quoteId,
        rationale: (opts?.rationale ?? awardRationale) || null,
      });
      if (reply.status === "pending_approval") {
        toast.warn(
          `Awaiting ${reply.approval.required_role.replace("_", " ")} approval`,
          { label: "View approvals", href: "/approvals" },
        );
        rfq.reload();
        setAwarding(false);
      } else {
        toast.success(
          reply.po ? `Awarded — ${reply.po.po_no} drafted` : "RFQ awarded",
          { label: "View POs", href: "/pos" },
        );
        router.push("/sourcing");
      }
    } catch (err) {
      setAwardErr(err instanceof Error ? err.message : "Failed to award RFQ");
      setAwarding(false);
    }
  }

  function buildTbeConfirmMessage(target: CombinedEvaluation, rationale: string | null): string {
    const lines = [
      `Award to ${target.vendor} (TBE combined #1, score ${target.combined_score.toFixed(1)})?`,
      `Commercial ${target.commercial_score.toFixed(0)} · Technical ${target.technical_score} · ${target.deviations_count} deviation(s).`,
    ];
    if (rationale) lines.push("", rationale);
    lines.push("", "Proceed and auto-draft a PO?");
    return lines.join("\n");
  }

  function handleAwardRecommended() {
    if (tbeAward.mode !== "tbe") return;
    void handleAward(tbeAward.target.quote_id, {
      confirmMessage: buildTbeConfirmMessage(tbeAward.target, tbeAward.rationale),
    });
  }

  function handleCommercialOverride() {
    if (!commercialWinner) return;
    void handleAward(commercialWinner.quote_id, {
      confirmMessage: [
        `Commercial-only override: award to ${commercialWinner.vendor} (commercial #1)?`,
        "",
        "This bypasses technical bid evaluation. Use only when TBE has not been completed.",
        "",
        "Proceed and auto-draft a PO?",
      ].join("\n"),
    });
  }

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
          <Link href={`/sourcing/prs/${data.pr_no}`} className="text-accent hover:underline font-mono text-xs">
            {data.pr_no}
          </Link>
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
          <form onSubmit={handleAddQuote} className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <Field label="Vendor">
              <select
                value={selectedVendor || quoteDraft.vendor || ""}
                onChange={(e) => {
                  const v = e.target.value;
                  setSelectedVendor(v);
                  setQuoteDraft((d) => ({ ...d, vendor: v }));
                }}
              >
                <option value="">Select vendor...</option>
                {data.vendors.map((v) => (
                  <option key={v} value={v}>{v}</option>
                ))}
              </select>
            </Field>
            <Field label="Unit Price (USD)">
              <input
                type="number"
                step="0.01"
                value={quoteDraft.unit_price_usd ?? ""}
                onChange={(e) => setQuoteDraft((d) => ({ ...d, unit_price_usd: Number(e.target.value) }))}
              />
            </Field>
            <Field label="Lead Time (days)">
              <input
                type="number"
                min={1}
                value={quoteDraft.lead_time_days ?? ""}
                onChange={(e) => setQuoteDraft((d) => ({ ...d, lead_time_days: Number(e.target.value) }))}
              />
            </Field>
            <Field label="Incoterm">
              <select
                value={quoteDraft.incoterm ?? "CIP"}
                onChange={(e) => setQuoteDraft((d) => ({ ...d, incoterm: e.target.value as Incoterm }))}
              >
                {INCOTERMS.map((i) => <option key={i} value={i}>{i}</option>)}
              </select>
            </Field>
            <Field label="Validity (days)">
              <input
                type="number"
                min={1}
                value={quoteDraft.validity_days ?? 30}
                onChange={(e) => setQuoteDraft((d) => ({ ...d, validity_days: Number(e.target.value) }))}
              />
            </Field>
            <Field label="Notes">
              <input
                value={quoteDraft.notes ?? ""}
                onChange={(e) => setQuoteDraft((d) => ({ ...d, notes: e.target.value }))}
                placeholder="Optional"
              />
            </Field>
            <div className="md:col-span-3 flex items-center gap-3">
              <button type="submit" className="btn btn-primary" disabled={savingQuote}>
                {savingQuote ? "Saving..." : "Add Quote"}
              </button>
              {quoteErr ? <span className="text-[#ff9d9d] text-sm">{quoteErr}</span> : null}
            </div>
          </form>
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

          {tbe.loading ? (
            <EmptyState title="Loading TBE recommendation..." />
          ) : tbeAward.mode === "tbe" ? (
            <div className="panel-sm space-y-3 border border-emerald-500/30 bg-emerald-500/[0.04]">
              <div className="flex items-start justify-between gap-3 flex-wrap">
                <div>
                  <div className="text-[0.65rem] uppercase tracking-[0.12em] text-emerald-300 font-bold">
                    TBE recommended
                  </div>
                  <div className="text-lg font-bold text-ink mt-1">
                    {tbeAward.target.vendor}
                    <span className="text-sm text-muted font-normal ml-2">
                      combined {tbeAward.target.combined_score.toFixed(1)}
                    </span>
                  </div>
                  <div className="text-xs text-muted mt-1">
                    Commercial {tbeAward.target.commercial_score.toFixed(0)} · Technical {tbeAward.target.technical_score}
                    · rank #{tbeAward.target.combined_rank}
                    {tbeAward.target.deviations_count > 0
                      ? ` · ${tbeAward.target.deviations_count} deviation(s)`
                      : ""}
                  </div>
                </div>
                <button
                  className="btn btn-primary"
                  onClick={handleAwardRecommended}
                  disabled={awarding}
                >
                  {awarding ? "Awarding..." : `Award recommended (${tbeAward.target.vendor})`}
                </button>
              </div>
              {tbeAward.rationale ? (
                <p className="text-sm text-ink leading-relaxed m-0">{tbeAward.rationale}</p>
              ) : null}
            </div>
          ) : tbeAward.mode === "blocked" ? (
            <div className="panel-sm border border-rose-500/30 bg-rose-500/[0.04] text-sm">
              <div className="font-bold text-rose-300 mb-1">Award blocked</div>
              <p className="text-ink m-0">{tbeAward.reason}</p>
              <Link href="#tbe-panel" className="inline-block mt-2 text-accent text-xs hover:underline">
                Review TBE panel →
              </Link>
            </div>
          ) : tbeAward.mode === "not_run" ? (
            <div className="panel-sm space-y-3">
              <div>
                <div className="font-bold text-ink">Run TBE before awarding</div>
                <p className="text-sm text-muted mt-1 m-0">
                  Technical bid evaluation has not been completed. Score vendors in the TBE panel, then award the combined #1.
                </p>
                <Link href="#tbe-panel" className="inline-block mt-2 text-accent text-sm hover:underline">
                  Go to Technical Bid Evaluation →
                </Link>
              </div>
              {commercialWinner ? (
                <div className="pt-3 border-t border-line">
                  <p className="text-xs text-muted m-0 mb-2">
                    Emergency override — awards commercial #1 without technical evaluation.
                  </p>
                  <button
                    className="btn btn-secondary text-xs"
                    onClick={handleCommercialOverride}
                    disabled={awarding}
                  >
                    {awarding ? "Awarding..." : `Commercial-only override (${commercialWinner.vendor})`}
                  </button>
                </div>
              ) : null}
            </div>
          ) : (
            <EmptyState title="Award needs quotes and TBE data" />
          )}

          <div className="space-y-2">
            <div className="text-[0.65rem] uppercase tracking-[0.12em] text-muted font-bold">
              Custom rationale (optional)
            </div>
            <textarea
              rows={3}
              value={awardRationale}
              onChange={(e) => setAwardRationale(e.target.value)}
              placeholder="Why this vendor? Any commercial or technical notes worth recording..."
            />
            {awardErr ? <div className="text-[#ff9d9d] text-sm">{awardErr}</div> : null}
          </div>
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
