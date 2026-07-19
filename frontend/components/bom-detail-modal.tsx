"use client";

import Link from "next/link";
import { useEffect } from "react";

import { daysFromNow, formatDate, formatMoney } from "@/lib/format-date";
import type { BOMItem, BomStatus } from "@/lib/types";

const STATUS_TONE: Record<BomStatus, string> = {
  spec_missing: "severity-high",
  planned: "severity-low",
  requisitioned: "severity-medium",
  ordered: "severity-medium",
  delivered: "severity-low",
};

type Props = {
  item: BOMItem;
  onClose: () => void;
  onCreatePr: (bomItemId: string) => void;
  onRequestSpec?: (item: BOMItem) => void;
  creatingPr: boolean;
};

export function BomDetailModal({ item, onClose, onCreatePr, onRequestSpec, creatingPr }: Props) {
  // Close on Escape.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const days = daysFromNow(item.planned_need_date);
  const tight = days !== null && (item.long_lead_days ?? 0) > days;
  const extended =
    item.unit_cost_usd != null ? item.unit_cost_usd * item.quantity : null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="panel w-full max-w-2xl max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between mb-4 gap-3">
          <div>
            <div className="text-[0.68rem] uppercase tracking-[0.14em] text-muted font-bold">
              BOM line · {item.code}
            </div>
            <h2 className="m-0 text-xl font-bold mt-1">{item.description}</h2>
            <div className="flex items-center gap-2 mt-2">
              {item.category ? (
                <span className="text-sm text-muted">{item.category}</span>
              ) : null}
              <span className={`badge ${STATUS_TONE[item.status]}`}>
                {item.status.replace(/_/g, " ")}
              </span>
            </div>
          </div>
          <button className="btn btn-secondary text-xs" onClick={onClose}>
            Close
          </button>
        </div>

        {/* Value strip */}
        <div className="grid grid-cols-3 gap-3 mb-4">
          <ValueTile label="Quantity" value={`${item.quantity} ${item.uom}`} />
          <ValueTile label="Unit Cost" value={formatMoney(item.unit_cost_usd)} />
          <ValueTile label="Extended Value" value={formatMoney(extended)} accent />
        </div>

        {/* Lead-time risk callout */}
        {tight ? (
          <div className="panel-sm mb-4 border-l-2 border-warning">
            <div className="text-warning font-semibold text-sm">
              Lead-time risk
            </div>
            <div className="text-xs text-muted mt-1">
              Long-lead {item.long_lead_days}d exceeds the {days}d remaining until
              need-by. Order now or the milestone slips.
            </div>
          </div>
        ) : null}

        {/* Detail grid */}
        <div className="panel-sm grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-3 text-sm mb-4">
          <Field label="Supplier">
            {item.supplier_name ? (
              <Link
                href={`/vendors/${encodeURIComponent(item.supplier_name)}`}
                className="text-accent hover:underline"
              >
                {item.supplier_name}
              </Link>
            ) : (
              <span className="text-muted">Unassigned</span>
            )}
          </Field>
          <Field label="Milestone">
            <span className="text-ink">{item.milestone_code ?? "—"}</span>
          </Field>
          <Field label="Lead Time">
            <span className={tight ? "text-warning font-bold" : "text-ink"}>
              {item.long_lead_days ? `${item.long_lead_days} days` : "—"}
            </span>
          </Field>
          <Field label="Need By">
            <span className="text-ink">{formatDate(item.planned_need_date)}</span>
            {days !== null ? (
              <span
                className={`ml-2 text-xs ${
                  days < 0 ? "text-danger" : days <= 30 ? "text-warning" : "text-muted"
                }`}
              >
                {days < 0 ? `${Math.abs(days)}d ago` : `in ${days}d`}
              </span>
            ) : null}
          </Field>
          <Field label="Spec Document">
            {item.spec_doc_id ? (
              <span className="font-mono text-xs text-accent">{item.spec_doc_id}</span>
            ) : (
              <span className="badge severity-high">missing</span>
            )}
          </Field>
          <Field label="Drawing">
            {item.drawing_id ? (
              <span className="font-mono text-xs text-accent">{item.drawing_id}</span>
            ) : (
              <span className="text-muted">—</span>
            )}
          </Field>
          <Field label="BOM Level">
            <span className="text-ink">L{item.level}</span>
          </Field>
          <Field label="Parent Item">
            <span className="font-mono text-xs text-muted">
              {item.parent_item_id ?? "— (top level)"}
            </span>
          </Field>
          <Field label="Item ID">
            <span className="font-mono text-xs text-muted">{item.bom_item_id}</span>
          </Field>
        </div>

        {/* Actions */}
        <div className="flex flex-wrap gap-2">
          {item.status === "spec_missing" && onRequestSpec ? (
            <button
              className="btn btn-secondary"
              onClick={() => onRequestSpec(item)}
            >
              Request spec
            </button>
          ) : null}
          <button
            className="btn btn-primary"
            onClick={() => onCreatePr(item.bom_item_id)}
            disabled={creatingPr}
          >
            {creatingPr ? "Creating PR..." : "Create PR"}
          </button>
          <button className="btn btn-secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

function ValueTile({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div className="panel-sm">
      <div className="text-[0.62rem] uppercase tracking-[0.12em] text-muted font-bold">
        {label}
      </div>
      <div className={`text-lg font-bold mt-1 ${accent ? "text-accent" : "text-ink"}`}>
        {value}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[0.62rem] uppercase tracking-[0.12em] text-muted font-bold">
        {label}
      </span>
      <div>{children}</div>
    </div>
  );
}
