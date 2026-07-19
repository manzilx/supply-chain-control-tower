"use client";

import { useRouter } from "next/navigation";
import { useMemo, useRef, useState } from "react";

import { BomAutofillModal } from "@/components/bom-autofill-modal";
import { BomDetailModal } from "@/components/bom-detail-modal";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { ProjectTabs } from "@/components/project-tabs";
import { SpecRequestModal } from "@/components/spec-request-modal";
import { createPr, fetchBom, fetchProject, uploadBomCsv } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { daysFromNow, formatDate, formatMoney } from "@/lib/format-date";
import { useAsync } from "@/lib/use-async";
import type { BOMItem, BomStatus, BomUploadResult } from "@/lib/types";

const STATUS_TONE: Record<BomStatus, string> = {
  spec_missing: "severity-high",
  planned: "severity-low",
  requisitioned: "severity-medium",
  ordered: "severity-medium",
  delivered: "severity-low",
};

export default function BomPage({ params }: { params: { id: string } }) {
  const router = useRouter();
  const { hasPerm } = useAuth();
  const canEditBom = hasPerm("bom", "create");
  const project = useAsync(() => fetchProject(params.id), [params.id]);
  const bom = useAsync(() => fetchBom(params.id), [params.id]);
  const [status, setStatus] = useState<BomStatus | "all">("all");
  const [query, setQuery] = useState("");
  const [uploadResult, setUploadResult] = useState<BomUploadResult | null>(null);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [creatingPrFor, setCreatingPrFor] = useState<string | null>(null);
  const [selected, setSelected] = useState<BOMItem | null>(null);
  const [autofillOpen, setAutofillOpen] = useState(false);
  const [specRequestFor, setSpecRequestFor] = useState<BOMItem | null>(null);
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
    setUploadResult(null);
    try {
      const result = await uploadBomCsv(params.id, file);
      setUploadResult(result);
      bom.reload();
    } catch (err) {
      setUploadResult({
        project_id: params.id,
        rows_parsed: 0,
        rows_accepted: 0,
        rows_rejected: 0,
        errors: [err instanceof Error ? err.message : "Upload failed"],
        bom_items: [],
      });
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
            {canEditBom ? (
              <button
                className="btn btn-secondary"
                onClick={() => setAutofillOpen(true)}
              >
                Fix gaps / Autofill
              </button>
            ) : null}
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

      {/* Prominent upload zone — drag-and-drop or click. Lives directly under
          the tabs so it's always discoverable. */}
      <section
        className={`panel border-2 border-dashed transition-all ${
          dragOver ? "border-accent shadow-glow bg-accent/[0.04]" : "border-line/40"
        }`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          const f = e.dataTransfer.files?.[0];
          if (f) void handleFile(f);
        }}
      >
        <div className="flex flex-wrap items-center gap-4 justify-between">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1.5 flex-wrap">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-accent">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
              </svg>
              <h3 className="m-0 text-base font-bold text-ink">Upload BOM CSV</h3>
              <span className="badge severity-low">supports delivered / ordered / planned / requisitioned / spec_missing</span>
            </div>
            <p className="text-sm text-muted m-0">
              Drag a file here or{" "}
              <button
                onClick={() => fileInput.current?.click()}
                className="text-accent underline hover:text-accent-strong"
              >
                choose one
              </button>
              . Required: <code>code, description, quantity</code>. Optional:{" "}
              <code>status, parent_item_id, category, uom, unit_cost_usd, supplier_name, spec_doc_id, drawing_id, long_lead_days, planned_need_date</code> (YYYY-MM-DD),{" "}
              <code>milestone_code, bom_item_id</code>.
            </p>
          </div>
          <button
            className="btn btn-primary"
            onClick={() => fileInput.current?.click()}
            disabled={uploading}
          >
            {uploading ? "Uploading…" : "Choose CSV"}
          </button>
        </div>

        {uploadResult ? (
          <div className="mt-4 pt-4 border-t border-line">
            <div className="flex items-baseline gap-4 flex-wrap text-sm">
              <span>
                <span className="text-accent font-bold text-base">{uploadResult.rows_accepted}</span>{" "}
                <span className="text-muted">added</span>
              </span>
              {uploadResult.rows_rejected > 0 ? (
                <span>
                  <span className="text-danger font-bold text-base">{uploadResult.rows_rejected}</span>{" "}
                  <span className="text-muted">rejected</span>
                </span>
              ) : null}
              {uploadResult.rows_parsed > 0 ? (
                <span className="text-muted">· {uploadResult.rows_parsed} parsed</span>
              ) : null}
            </div>
            {uploadResult.errors.length > 0 ? (
              <ul className="mt-3 space-y-1 text-xs">
                {uploadResult.errors.slice(0, 8).map((e, i) => (
                  <li key={i} className="text-muted">
                    <span className="text-danger">·</span> {e}
                  </li>
                ))}
                {uploadResult.errors.length > 8 ? (
                  <li className="text-muted italic">… {uploadResult.errors.length - 8} more</li>
                ) : null}
              </ul>
            ) : null}
          </div>
        ) : null}
      </section>

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
          <span className="ml-2 text-muted/70">· click a row for details</span>
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
                  <tr
                    key={i.bom_item_id}
                    onClick={() => setSelected(i)}
                    className="cursor-pointer hover:bg-white/5 transition-colors"
                  >
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
                      <div className="flex flex-wrap gap-1 justify-end">
                        {i.status === "spec_missing" ? (
                          <button
                            className="btn btn-secondary text-xs"
                            onClick={(e) => {
                              e.stopPropagation();
                              setSpecRequestFor(i);
                            }}
                          >
                            Request spec
                          </button>
                        ) : null}
                        <button
                          className="btn btn-secondary text-xs"
                          onClick={(e) => {
                            e.stopPropagation();
                            void handleCreatePr(i.bom_item_id);
                          }}
                          disabled={creatingPrFor === i.bom_item_id}
                        >
                          {creatingPrFor === i.bom_item_id ? "..." : "Create PR"}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {selected ? (
        <BomDetailModal
          item={selected}
          creatingPr={creatingPrFor === selected.bom_item_id}
          onClose={() => setSelected(null)}
          onCreatePr={(id) => void handleCreatePr(id)}
          onRequestSpec={(item) => setSpecRequestFor(item)}
        />
      ) : null}

      {autofillOpen ? (
        <BomAutofillModal
          projectId={params.id}
          onClose={() => setAutofillOpen(false)}
          onApplied={() => bom.reload()}
        />
      ) : null}

      {specRequestFor ? (
        <SpecRequestModal
          projectId={params.id}
          bomItemId={specRequestFor.bom_item_id}
          code={specRequestFor.code}
          onClose={() => setSpecRequestFor(null)}
        />
      ) : null}
    </div>
  );
}
