import type { PRStatus, RFQStatus, SourcingStrategy } from "@/lib/types";

const PR_TONE: Record<PRStatus, string> = {
  draft: "severity-low",
  rfq_issued: "severity-medium",
  quoted: "severity-medium",
  awarded: "severity-low",
  po_created: "severity-low",
  cancelled: "severity-high",
};

const RFQ_TONE: Record<RFQStatus, string> = {
  open: "severity-medium",
  quotes_received: "severity-medium",
  evaluated: "severity-medium",
  awarded: "severity-low",
  cancelled: "severity-high",
};

const STRATEGY_LABEL: Record<SourcingStrategy, string> = {
  single_source: "Single source",
  multi_source: "Multi-source",
  rate_contract: "Rate contract",
  emergency_buy: "Emergency buy",
};

export function PRStatusBadge({ status }: { status: PRStatus }) {
  return <span className={`badge ${PR_TONE[status]}`}>{status.replace(/_/g, " ")}</span>;
}

export function RFQStatusBadge({ status }: { status: RFQStatus }) {
  return <span className={`badge ${RFQ_TONE[status]}`}>{status.replace(/_/g, " ")}</span>;
}

export function StrategyPill({ strategy }: { strategy: SourcingStrategy }) {
  return (
    <span className="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold bg-white/5 text-muted">
      {STRATEGY_LABEL[strategy]}
    </span>
  );
}
