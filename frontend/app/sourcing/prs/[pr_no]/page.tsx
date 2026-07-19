"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { PRStatusBadge, StrategyPill } from "@/components/sourcing-badges";
import { SubmitToSapButton } from "@/components/sap-status";
import { EntityTrail, TraceabilityLadder } from "@/components/traceability";
import {
  fetchPr,
  fetchSuggestedVendors,
  issueRfq,
} from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatDate, formatMoney } from "@/lib/format-date";
import { useAsync } from "@/lib/use-async";

export default function PRPage({ params }: { params: { pr_no: string } }) {
  const router = useRouter();
  const { hasPerm } = useAuth();
  const pr = useAsync(() => fetchPr(params.pr_no), [params.pr_no]);
  const suggestions = useAsync(() => fetchSuggestedVendors(params.pr_no), [params.pr_no]);

  const [vendors, setVendors] = useState<string[]>([]);
  const [newVendor, setNewVendor] = useState("");
  const [dueInDays, setDueInDays] = useState(10);
  const [notes, setNotes] = useState("");
  const [issuing, setIssuing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (vendors.length === 0 && suggestions.data && suggestions.data.length > 0) {
      setVendors(suggestions.data.slice(0, 3));
    }
  }, [suggestions.data, vendors.length]);

  const canIssue = useMemo(
    () => pr.data?.status === "draft" && vendors.length > 0 && !issuing,
    [pr.data?.status, vendors.length, issuing],
  );

  function toggleVendor(name: string) {
    setVendors((v) => (v.includes(name) ? v.filter((n) => n !== name) : [...v, name]));
  }

  function addVendor() {
    const name = newVendor.trim();
    if (!name || vendors.includes(name)) return;
    setVendors((v) => [...v, name]);
    setNewVendor("");
  }

  async function handleIssue() {
    if (!canIssue || !pr.data) return;
    setIssuing(true);
    setError(null);
    try {
      const rfq = await issueRfq({
        pr_no: pr.data.pr_no,
        vendors,
        due_in_days: dueInDays,
        notes: notes || null,
      });
      router.push(`/sourcing/rfqs/${rfq.rfq_no}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to issue RFQ");
      setIssuing(false);
    }
  }

  if (pr.loading) return <EmptyState title="Loading PR..." />;
  if (pr.error || !pr.data) {
    return <div className="panel-sm border-[rgba(255,117,117,0.3)] text-[#ff9d9d]">{pr.error ?? "PR not found"}</div>;
  }

  const data = pr.data;

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="PR"
        title={`${data.pr_no} · ${data.code}`}
        description={data.description}
        right={
          <div className="flex items-center gap-3">
            <PRStatusBadge status={data.status} />
            <SubmitToSapButton
              kind="pr"
              refNo={data.pr_no}
              currentStatus={data.sap_status ?? "draft"}
              sapDocNo={data.sap_pr_no}
              onResult={() => pr.reload()}
            />
          </div>
        }
      />

      <section className="panel grid grid-cols-2 md:grid-cols-4 gap-4">
        <Field label="Project">
          <Link href={`/projects/${encodeURIComponent(data.project_id)}`} className="text-accent hover:underline font-mono text-xs">
            {data.project_id}
          </Link>
        </Field>
        <Field label="Quantity">
          <span>{data.quantity} {data.uom}</span>
        </Field>
        <Field label="Need by">
          <span>{formatDate(data.need_by)}</span>
        </Field>
        <Field label="Milestone">
          <span className="text-muted">{data.milestone_code ?? "—"}</span>
        </Field>
        <Field label="Budget">
          <span>{formatMoney(data.budget_value_usd)}</span>
        </Field>
        <Field label="Buyer">
          <span>{data.buyer}</span>
        </Field>
        <Field label="Strategy">
          <StrategyPill strategy={data.strategy} />
        </Field>
        <Field label="Created">
          <span className="text-muted">{formatDate(data.created_at)}</span>
        </Field>
      </section>

      {data.rfq_no ? (
        <section className="panel flex items-center justify-between gap-4">
          <div>
            <div className="text-[0.7rem] uppercase tracking-[0.14em] text-muted font-bold">RFQ in flight</div>
            <div className="font-mono text-ink mt-1">{data.rfq_no}</div>
          </div>
          <Link href={`/sourcing/rfqs/${data.rfq_no}`} className="btn btn-primary">
            Open RFQ
          </Link>
        </section>
      ) : null}

      {data.status === "draft" && hasPerm("rfq", "create") ? (
        <section className="panel space-y-4">
          <div>
            <h2 className="m-0 text-lg font-bold">Issue RFQ</h2>
            <p className="text-sm text-muted mt-1">
              Pick vendors to invite. Suggestions come from the approved vendor list and the BOM item's preferred supplier.
            </p>
          </div>

          <Field label="Vendors">
            <div className="space-y-2">
              <div className="flex flex-wrap gap-2">
                {vendors.length === 0 ? (
                  <span className="text-sm text-muted">No vendors selected.</span>
                ) : vendors.map((v) => (
                  <button
                    key={v}
                    type="button"
                    onClick={() => toggleVendor(v)}
                    className="badge severity-low hover:opacity-75 cursor-pointer"
                  >
                    {v} ·×
                  </button>
                ))}
              </div>
              {suggestions.data && suggestions.data.length > 0 ? (
                <div className="text-xs text-muted">
                  Suggestions:
                  <div className="flex flex-wrap gap-2 mt-1">
                    {suggestions.data
                      .filter((s) => !vendors.includes(s))
                      .map((s) => (
                        <button
                          key={s}
                          type="button"
                          onClick={() => toggleVendor(s)}
                          className="text-xs px-2 py-1 rounded-full bg-white/5 text-ink hover:bg-white/10"
                        >
                          + {s}
                        </button>
                      ))}
                  </div>
                </div>
              ) : null}
              <div className="flex gap-2">
                <input
                  placeholder="Add vendor by name..."
                  value={newVendor}
                  onChange={(e) => setNewVendor(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && addVendor()}
                />
                <button type="button" className="btn btn-secondary" onClick={addVendor}>
                  Add
                </button>
              </div>
            </div>
          </Field>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Field label="Due in (days)">
              <input
                type="number"
                min={1}
                value={dueInDays}
                onChange={(e) => setDueInDays(Number(e.target.value) || 10)}
              />
            </Field>
          </div>
          <Field label="Notes to vendors">
            <textarea
              rows={3}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Spec references, delivery terms, inspection requirements..."
            />
          </Field>

          {error ? <div className="text-[#ff9d9d] text-sm">{error}</div> : null}

          <div>
            <button className="btn btn-primary" onClick={handleIssue} disabled={!canIssue}>
              {issuing ? "Issuing..." : `Issue RFQ to ${vendors.length} vendor${vendors.length === 1 ? "" : "s"}`}
            </button>
          </div>
        </section>
      ) : null}

      <TraceabilityLadder kind="pr" id={data.pr_no} />
      <EntityTrail kind="pr" id={data.pr_no} />
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[0.65rem] uppercase tracking-[0.12em] text-muted font-bold">{label}</span>
      <div>{children}</div>
    </div>
  );
}
