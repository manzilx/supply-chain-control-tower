"use client";

import { useRouter } from "next/navigation";
import { useMemo, useRef, useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { ProjectTabs } from "@/components/project-tabs";
import { createPr, fetchBom, fetchProject, uploadBomCsv } from "@/lib/api";
import { daysFromNow, formatDate, formatMoney } from "@/lib/format-date";
import { useAsync } from "@/lib/use-async";
import type { BomStatus } from "@/lib/types";

const STATUS_TONE: Record<BomStatus, string> = {
  spec_missing: "severity-high",
  planned: "severity-low",
  requisitioned: "severity-medium",
  ordered: "severity-medium",
  delivered: "severity-low",
};

export default function BomPage({ params }: { params: { id: string } }) {
  const router = useRouter();
  const project = useAsync(() => fetchProject(params.id), [params.id]);
  const bom = useAsync(() => fetchBom(params.id), [params.id]);
  const [status, setStatus] = useState<BomStatus | "all">("all");
  const [query, setQuery] = useState("");
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [creatingPrFor, setCreatingPrFor] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  async function handleCreatePr(bomItemId: string) {
    setCreatingPrFor(bomItemId);
    try {
      const pr = await createPr({ project_id: params.id, bom_item_id: bomItemId });
      router.push(`/sourcing/prs/${pr.pr_no}`);
    } catch (err) {
      setCreatingPrFor(null);
      alert(err instanceof Error ? err.message : "Could not create PR");
    }
  }

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const items = bom.data ?? [];
    return items
      .filter((i) => status === "all" || i.status === status)
      .filter((i) => !q || i.code.toLowerCase().includes(q) || i.description.toLowerCase().includes(q))
      .sort((a, b) => {
        const ad = a.planned_need_date ? new Date(a.planned_need_date).getTime() : Infinity;
        const bd = b.planned_need_date ? new Date(b.planned_need_date).getTime() : Infinity;
        return ad - bd;
      });
  }, [bom.data, status, query]);

  async function handleFile(file: File) {
    setUploading(true);
    setUploadMsg(null);
    try {
      const result = await uploadBomCsv(params.id, file);
      const parts = [
        `${result.rows_accepted} added`,
        result.rows_rejected ? `${result.rows_rejected} rejected` : null,
      ].filter(Boolean);
      setUploadMsg(parts.join(" · "));
      bom.reload();
    } catch (err) {
      setUploadMsg(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={params.id}
        title={project.data?.name ?? "BOM"}
        description="Bill of materials. Missing specs and long-lead items propagate to the procurement plan."
        right={
          <div className="flex items-center gap-2">
            <input
              ref={fileInput}
              type="file"
              accept=".csv,text/csv"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void handleFile(f);
              }}
              style={{ width: "auto" }}
            />
            <button
              className="btn btn-secondary"
              onClick={() => fileInput.current?.click()}
              disabled={uploading}
            >
              {uploading ? "Uploading..." : "Upload CSV"}
            </button>
          </div>
        }
      />
      <ProjectTabs projectId={params.id} />

      {uploadMsg ? (
        <div className="panel-sm text-sm">
          <span className="text-accent font-semibold">Upload result:</span>{" "}
          <span className="text-ink">{uploadMsg}</span>
        </div>
      ) : null}

      <details className="panel-sm">
        <summary className="cursor-pointer text-sm text-muted select-none">
          CSV format (expand)
        </summary>
        <div className="mt-3 text-xs text-muted space-y-2">
          <div>
            <strong className="text-ink">Required columns:</strong> <code>code</code>,{" "}
            <code>description</code>, <code>quantity</code>
          </div>
          <div>
            <strong className="text-ink">Optional columns:</strong>{" "}
            <code>bom_item_id</code>, <code>category</code>, <code>uom</code>,{" "}
            <code>unit_cost_usd</code>, <code>supplier_name</code>, <code>spec_doc_id</code>,{" "}
            <code>drawing_id</code>, <code>long_lead_days</code>,{" "}
            <code>planned_need_date</code> (YYYY-MM-DD), <code>milestone_code</code>
          </div>
        </div>
      </details>

      <div className="panel-sm flex flex-wrap gap-3 items-end">
        <label className="flex-1 min-w-[200px] flex flex-col gap-1">
          <span className="text-[0.68rem] uppercase tracking-[0.12em] text-muted font-bold">Search</span>
          <input
            placeholder="Code or description..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <label className="min-w-[160px] flex flex-col gap-1">
          <span className="text-[0.68rem] uppercase tracking-[0.12em] text-muted font-bold">Status</span>
          <select value={status} onChange={(e) => setStatus(e.target.value as BomStatus | "all")}>
            <option value="all">All</option>
            <option value="spec_missing">spec missing</option>
            <option value="planned">planned</option>
            <option value="requisitioned">requisitioned</option>
            <option value="ordered">ordered</option>
            <option value="delivered">delivered</option>
          </select>
        </label>
        <div className="text-xs text-muted pb-2">
          {rows.length} of {bom.data?.length ?? 0}
        </div>
      </div>

      <div className="panel overflow-x-auto p-0">
        {bom.loading ? (
          <div className="p-6"><EmptyState title="Loading BOM..." /></div>
        ) : bom.error ? (
          <div className="p-6 text-[#ff9d9d]">{bom.error}</div>
        ) : rows.length === 0 ? (
          <div className="p-6">
            <EmptyState
              title={bom.data?.length ? "No items match filters" : "No BOM items"}
              hint={bom.data?.length ? "Clear filters or search." : "Upload a BOM CSV to get started."}
            />
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Code</th>
                <th>Description</th>
                <th>Qty</th>
                <th>Unit Cost</th>
                <th>Supplier</th>
                <th>Lead Time</th>
                <th>Need By</th>
                <th>Milestone</th>
                <th>Spec</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((i) => {
                const days = daysFromNow(i.planned_need_date);
                const tight = days !== null && (i.long_lead_days ?? 0) > days;
                return (
                  <tr key={i.bom_item_id}>
                    <td className="font-semibold text-ink font-mono text-xs">{i.code}</td>
                    <td>
                      <div className="text-ink">{i.description}</div>
                      {i.category ? <div className="text-xs text-muted mt-0.5">{i.category}</div> : null}
                    </td>
                    <td>{i.quantity} {i.uom}</td>
                    <td>{formatMoney(i.unit_cost_usd)}</td>
                    <td className="text-muted">{i.supplier_name ?? "—"}</td>
                    <td className={tight ? "text-warning font-bold" : ""}>
                      {i.long_lead_days ? `${i.long_lead_days}d` : "—"}
                    </td>
                    <td>
                      {formatDate(i.planned_need_date)}
                      {days !== null ? (
                        <div className={`text-xs ${days < 0 ? "text-danger" : days <= 30 ? "text-warning" : "text-muted"}`}>
                          {days < 0 ? `${Math.abs(days)}d ago` : `in ${days}d`}
                        </div>
                      ) : null}
                    </td>
                    <td className="text-muted">{i.milestone_code ?? "—"}</td>
                    <td>
                      {i.spec_doc_id ? (
                        <span className="text-xs text-accent font-mono">{i.spec_doc_id}</span>
                      ) : (
                        <span className="badge severity-high">missing</span>
                      )}
                    </td>
                    <td>
                      <span className={`badge ${STATUS_TONE[i.status]}`}>
                        {i.status.replace(/_/g, " ")}
                      </span>
                    </td>
                    <td>
                      <button
                        className="btn btn-secondary text-xs"
                        onClick={() => void handleCreatePr(i.bom_item_id)}
                        disabled={creatingPrFor === i.bom_item_id}
                      >
                        {creatingPrFor === i.bom_item_id ? "..." : "Create PR"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
