"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { SkeletonCard } from "@/components/skeleton";
import { approveApproval, fetchApprovals, rejectApproval } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatTimestamp } from "@/lib/format";
import { useToast } from "@/lib/toast-context";
import { useAsync } from "@/lib/use-async";
import type { Approval, ApprovalKind, ApprovalStatus } from "@/lib/types";

const KIND_LABEL: Record<ApprovalKind, string> = {
  po_create: "PO ≥ threshold",
  award_single_source: "Single-source award",
  quote_above_budget: "Over-budget quote",
  variation_order: "Variation order",
  vendor_onboarding: "Vendor onboarding",
};

const STATUS_TONE: Record<ApprovalStatus, string> = {
  pending: "severity-high",
  approved: "severity-low",
  rejected: "severity-critical",
  auto_approved: "severity-low",
};

function resultLink(a: Approval): { label: string; href: string } | undefined {
  if (!a.result_ref) return undefined;
  if (a.kind === "vendor_onboarding") {
    return { label: "View vendor", href: `/vendors/${encodeURIComponent(a.result_ref)}` };
  }
  if (a.result_ref.startsWith("SPO") || a.kind === "po_create" || a.kind === "award_single_source") {
    return { label: "View POs", href: "/pos" };
  }
  if (a.kind === "quote_above_budget") {
    const rfq = typeof a.payload?.rfq_no === "string" ? a.payload.rfq_no : null;
    if (rfq) return { label: "View RFQ", href: `/sourcing/rfqs/${encodeURIComponent(rfq)}` };
  }
  return undefined;
}

export default function ApprovalsPage() {
  const { data, loading, error, reload } = useAsync(fetchApprovals, []);
  const { permissions } = useAuth();
  const toast = useToast();
  const [filter, setFilter] = useState<ApprovalStatus | "all">("pending");
  const [busy, setBusy] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});

  const canDecide = permissions.includes("approval:decide") || permissions.includes("*");

  const rows = useMemo(() => {
    const items = data ?? [];
    return filter === "all" ? items : items.filter((a) => a.status === filter);
  }, [data, filter]);

  const pendingCount = (data ?? []).filter((a) => a.status === "pending").length;

  async function decide(a: Approval, approve: boolean) {
    setBusy(a.approval_id);
    try {
      const fn = approve ? approveApproval : rejectApproval;
      const result = await fn(a.approval_id, { note: notes[a.approval_id] || undefined });
      if (approve) {
        const link = resultLink(result);
        const msg = result.result_ref
          ? a.kind === "vendor_onboarding"
            ? `Approved — vendor ${result.result_ref} onboarded`
            : `Approved — ${result.result_ref} created`
          : "Approved — committed";
        toast.success(msg, link);
      } else {
        toast.warn("Request rejected");
      }
      reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not record decision");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Governance"
        title="Approvals"
        description={
          canDecide
            ? "High-risk procurement writes wait here for your decision. Approving commits the original request."
            : "Requests you've raised that need a procurement head's sign-off."
        }
      />

      <div className="flex flex-wrap gap-2">
        {(["pending", "approved", "rejected", "auto_approved", "all"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
              filter === f
                ? "border-accent text-accent bg-accent/[0.06]"
                : "border-line text-muted hover:text-ink"
            }`}
          >
            {f === "all" ? "All" : f.replace("_", " ")}
            {f === "pending" && pendingCount ? ` (${pendingCount})` : ""}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-3"><SkeletonCard /><SkeletonCard /></div>
      ) : error ? (
        <div className="panel-sm border-[rgba(255,117,117,0.3)] text-[#ff9d9d]">{error}</div>
      ) : rows.length === 0 ? (
        <EmptyState
          title={filter === "pending" ? "Nothing awaiting approval" : "No approvals here"}
          hint={
            filter === "pending"
              ? "Single-source awards, large POs, over-budget quotes, and new vendor onboarding will surface here."
              : undefined
          }
        />
      ) : (
        <div className="space-y-3">
          {rows.map((a) => {
            const link = resultLink(a);
            return (
            <article key={a.approval_id} className="panel animate-fade-up">
              <div className="flex items-start justify-between gap-3 flex-wrap">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <span className="text-[0.6rem] uppercase tracking-[0.12em] text-muted font-bold">
                      {a.approval_id}
                    </span>
                    <span className="badge severity-medium">{KIND_LABEL[a.kind] ?? a.kind}</span>
                    <span className={`badge ${STATUS_TONE[a.status]}`}>{a.status.replace("_", " ")}</span>
                  </div>
                  <h3 className="m-0 text-base font-bold">{a.title}</h3>
                  <p className="text-sm text-muted mt-1 m-0">{a.summary}</p>
                  <div className="text-xs text-muted mt-2">
                    Raised by {a.requested_by_name} · {formatTimestamp(a.requested_at)}
                    {a.decided_by_name ? ` · decided by ${a.decided_by_name}` : ""}
                    {a.result_ref ? (
                      <>
                        {" · "}
                        {link ? (
                          <Link href={link.href} className="text-accent hover:underline">
                            {a.result_ref}
                          </Link>
                        ) : (
                          <span className="text-accent">{a.result_ref}</span>
                        )}
                      </>
                    ) : null}
                  </div>
                  {a.decision_note ? (
                    <div className="text-xs text-muted mt-1 italic">“{a.decision_note}”</div>
                  ) : null}
                </div>

                {a.status === "pending" && canDecide ? (
                  <div className="flex flex-col gap-2 w-full sm:w-auto sm:min-w-[240px]">
                    <input
                      placeholder="Decision note (optional)…"
                      value={notes[a.approval_id] ?? ""}
                      onChange={(e) => setNotes((n) => ({ ...n, [a.approval_id]: e.target.value }))}
                      className="text-sm"
                    />
                    <div className="flex gap-2">
                      <button
                        className="btn btn-primary flex-1"
                        disabled={busy === a.approval_id}
                        onClick={() => void decide(a, true)}
                      >
                        {busy === a.approval_id ? "…" : "Approve"}
                      </button>
                      <button
                        className="btn btn-secondary flex-1"
                        disabled={busy === a.approval_id}
                        onClick={() => void decide(a, false)}
                      >
                        Reject
                      </button>
                    </div>
                  </div>
                ) : null}
              </div>
            </article>
            );
          })}
        </div>
      )}

      {!canDecide && (data ?? []).length === 0 && !loading ? (
        <div className="text-xs text-muted">
          Tip: sign in as a procurement head (e.g. <code>arcforge-head-01</code>) to action approvals, or as a buyer to raise them by{" "}
          <Link href="/sourcing" className="text-accent">awarding a single-source RFQ</Link>
          {" "}or{" "}
          <Link href="/vendors" className="text-accent">onboarding a vendor</Link>.
        </div>
      ) : null}
    </div>
  );
}
