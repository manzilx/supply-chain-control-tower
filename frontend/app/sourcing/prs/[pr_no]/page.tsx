"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";

import { EmptyState } from "@/components/empty-state";
import { IssueRfqForm } from "@/components/issue-rfq-form";
import { PageHeader } from "@/components/page-header";
import { PRStatusBadge, StrategyPill } from "@/components/sourcing-badges";
import { SubmitToSapButton } from "@/components/sap-status";
import { EntityTrail, TraceabilityLadder } from "@/components/traceability";
import { fetchPr } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatDate, formatMoney } from "@/lib/format-date";
import { useAsync } from "@/lib/use-async";

export default function PRPage({ params }: { params: { pr_no: string } }) {
  const router = useRouter();
  const { hasPerm } = useAuth();
  const pr = useAsync(() => fetchPr(params.pr_no), [params.pr_no]);

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
          <div className="flex items-center gap-2 flex-wrap">
            <Link href={`/projects/${encodeURIComponent(data.project_id)}`} className="text-accent hover:underline font-mono text-xs">
              {data.project_id}
            </Link>
            <Link
              href={`/projects/${encodeURIComponent(data.project_id)}/process?stage=pr`}
              className="text-[0.62rem] uppercase tracking-[0.1em] font-bold text-accent"
            >
              Process
            </Link>
          </div>
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
              Pick vendors to invite. Suggestions come from the approved vendor list and the BOM item&apos;s preferred supplier.
            </p>
          </div>
          <IssueRfqForm
            prNo={data.pr_no}
            onIssued={(rfqNo) => router.push(`/sourcing/rfqs/${rfqNo}`)}
          />
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
