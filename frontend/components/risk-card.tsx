import type { RiskRecord } from "@/lib/types";

type Props = {
  risk: RiskRecord;
};

export function RiskCard({ risk }: Props) {
  return (
    <article className="panel-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="font-bold text-ink">{risk.title}</div>
        <span className={`badge severity-${risk.severity} shrink-0`}>
          {risk.severity} · {risk.score}
        </span>
      </div>
      <p className="mt-2 text-sm text-muted leading-relaxed">{risk.summary}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Pill>Owner: {risk.owner}</Pill>
        {risk.supplier_name ? <Pill>Supplier: {risk.supplier_name}</Pill> : null}
        {risk.sku ? <Pill>SKU: {risk.sku}</Pill> : null}
      </div>
    </article>
  );
}

function Pill({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold bg-white/5 text-muted">
      {children}
    </span>
  );
}
