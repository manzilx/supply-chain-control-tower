"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { RFQStatusBadge } from "@/components/sourcing-badges";
import {
  addQuote,
  awardRfq,
  fetchQuoteComparison,
  fetchQuotes,
  fetchRfq,
} from "@/lib/api";
import { formatDate, formatMoney } from "@/lib/format-date";
import { useAsync } from "@/lib/use-async";
import type { CreateQuoteRequest, Incoterm } from "@/lib/types";

const INCOTERMS: Incoterm[] = ["EXW", "FCA", "FOB", "CIF", "CIP", "DAP", "DDP"];

export default function RFQPage({ params }: { params: { rfq_no: string } }) {
  const router = useRouter();
  const rfq = useAsync(() => fetchRfq(params.rfq_no), [params.rfq_no]);
  const quotes = useAsync(() => fetchQuotes(params.rfq_no), [params.rfq_no]);
  const comparison = useAsync(() => fetchQuoteComparison(params.rfq_no), [params.rfq_no]);

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
      await addQuote(params.rfq_no, {
        vendor: (quoteDraft.vendor || selectedVendor) as string,
        unit_price_usd: Number(quoteDraft.unit_price_usd),
        lead_time_days: Number(quoteDraft.lead_time_days),
        incoterm: quoteDraft.incoterm ?? "CIP",
        validity_days: Number(quoteDraft.validity_days ?? 30),
        notes: quoteDraft.notes ?? null,
      });
      setQuoteDraft({ incoterm: "CIP", validity_days: 30 });
      setSelectedVendor("");
      quotes.reload();
      comparison.reload();
      rfq.reload();
    } catch (err) {
      setQuoteErr(err instanceof Error ? err.message : "Failed to save quote");
    } finally {
      setSavingQuote(false);
    }
  }

  async function handleAward(quoteId: string, rationale?: string) {
    if (!rfq.data) return;
    if (!confirm("Award this quote and auto-draft a PO?")) return;
    setAwarding(true);
    setAwardErr(null);
    try {
      await awardRfq(params.rfq_no, {
        quote_id: quoteId,
        rationale: rationale || awardRationale || null,
      });
      router.push("/sourcing");
    } catch (err) {
      setAwardErr(err instanceof Error ? err.message : "Failed to award RFQ");
      setAwarding(false);
    }
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
        <div className="flex items-center justify-between">
          <h2 className="m-0 text-lg font-bold">Comparison</h2>
          {comparison.data?.recommended_vendor ? (
            <span className="chip">Recommended: {comparison.data.recommended_vendor}</span>
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
                    <th></th>
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
                      <td>
                        {awardable ? (
                          <button
                            className="btn btn-secondary text-xs"
                            onClick={() => void handleAward(ev.quote_id)}
                            disabled={awarding}
                          >
                            Award
                          </button>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {comparison.data.recommendation_rationale ? (
              <div className="panel-sm">
                <div className="section-title mb-2">Rationale</div>
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

      {awardable && comparison.data && comparison.data.evaluations.length > 0 ? (
        <section className="panel space-y-3">
          <h2 className="m-0 text-lg font-bold">Award with Custom Rationale</h2>
          <p className="text-sm text-muted">
            Leaving this blank uses the auto-generated rationale based on score.
          </p>
          <textarea
            rows={3}
            value={awardRationale}
            onChange={(e) => setAwardRationale(e.target.value)}
            placeholder="Why this vendor? Any commercial or technical notes worth recording..."
          />
          {awardErr ? <div className="text-[#ff9d9d] text-sm">{awardErr}</div> : null}
          <div>
            <button
              className="btn btn-primary"
              onClick={() => {
                const winner = comparison.data?.evaluations[0];
                if (winner) void handleAward(winner.quote_id);
              }}
              disabled={awarding}
            >
              {awarding ? "Awarding..." : `Award to #1 (${comparison.data.evaluations[0].vendor})`}
            </button>
          </div>
        </section>
      ) : null}
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
