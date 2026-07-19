"use client";

import { useRef, useState } from "react";

import { PageHeader } from "@/components/page-header";
import { fetchProjects, ingestCommit, ingestPreview } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useToast } from "@/lib/toast-context";
import { useAsync } from "@/lib/use-async";
import type { IngestCommitReply, IngestPreviewReply, IngestSheetPreview } from "@/lib/types";

const ENTITY_TONE: Record<string, string> = {
  project: "severity-low",
  bom: "severity-medium",
  supplier: "severity-low",
};

export default function IngestPage() {
  const { hasPerm } = useAuth();
  const toast = useToast();
  const projects = useAsync(fetchProjects, []);
  const [dragOver, setDragOver] = useState(false);
  const [parsing, setParsing] = useState(false);
  const [preview, setPreview] = useState<IngestPreviewReply | null>(null);
  const [defaultProject, setDefaultProject] = useState("");
  const [committing, setCommitting] = useState(false);
  const [result, setResult] = useState<IngestCommitReply | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const canPreview = hasPerm("ingest", "preview");
  const canCommit = hasPerm("ingest", "commit");

  async function handleFile(file: File) {
    if (!canPreview) return;
    setParsing(true);
    setPreview(null);
    setResult(null);
    try {
      const reply = await ingestPreview(file);
      setPreview(reply);
      if (reply.total_valid === 0) {
        toast.warn("No valid rows found — check the sheet errors below");
      } else {
        toast.info(`${reply.total_valid} of ${reply.total_rows} rows ready to import`);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not parse file");
    } finally {
      setParsing(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  const needsDefaultProject =
    preview?.sheets.some(
      (s) => s.entity === "bom" && s.sample.some((r) => !r.project_id),
    ) ?? false;

  async function handleCommit() {
    if (!preview || !canCommit) return;
    setCommitting(true);
    try {
      const reply = await ingestCommit(preview.staging_id, defaultProject || null);
      setResult(reply);
      setPreview(null);
      const c = reply.created;
      toast.success(
        `Imported ${c.projects} project(s), ${c.bom_items} BOM line(s), ${c.suppliers} supplier(s)`,
        { label: "View projects", href: "/projects" },
      );
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Commit failed");
    } finally {
      setCommitting(false);
    }
  }

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Plan"
        title="Ingest Data"
        description="Drop any Excel workbook or CSV — projects, BOM, suppliers. Columns are auto-mapped (fuzzy + AI-assisted), validated row-by-row, and staged for review before anything is written."
      />

      {/* Drop zone */}
      {canPreview ? (
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
        <input
          ref={fileInput}
          type="file"
          accept=".xlsx,.xlsm,.csv"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void handleFile(f);
          }}
        />
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="min-w-0 flex-1">
            <h3 className="m-0 text-base font-bold text-ink">
              {parsing ? "Parsing…" : "Drop a workbook or CSV here"}
            </h3>
            <p className="text-sm text-muted m-0 mt-1">
              Multi-sheet Excel supported — sheets are classified as Projects / BOM / Suppliers
              automatically. Headers like “Part No”, “Qty”, “Vendor”, “OTD %” are fuzzy-mapped to
              the schema; leftovers go through one AI mapping pass when Grok is enabled.
            </p>
          </div>
          <button
            className="btn btn-primary"
            onClick={() => fileInput.current?.click()}
            disabled={parsing}
          >
            {parsing ? "Parsing…" : "Choose file"}
          </button>
        </div>
      </section>
      ) : (
        <section className="panel text-sm text-muted">
          You have read-only access. Sign in as a buyer or procurement head to upload and import data.
        </section>
      )}

      {/* Preview */}
      {preview ? (
        <section className="panel animate-fade-up space-y-4">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div>
              <div className="text-[0.65rem] uppercase tracking-[0.14em] text-muted font-bold">
                Staged · {preview.filename}
              </div>
              <h3 className="m-0 text-lg font-bold">
                {preview.total_valid} of {preview.total_rows} rows ready
              </h3>
            </div>
            <div className="flex items-center gap-3">
              {needsDefaultProject ? (
                <label className="flex flex-col gap-1">
                  <span className="text-[0.6rem] uppercase tracking-[0.1em] text-muted font-bold">
                    Default project for BOM rows
                  </span>
                  <select
                    value={defaultProject}
                    onChange={(e) => setDefaultProject(e.target.value)}
                  >
                    <option value="">— pick a project —</option>
                    {(projects.data ?? []).map((p) => (
                      <option key={p.project_id} value={p.project_id}>
                        {p.project_id} · {p.name}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
              <button
                className="btn btn-primary"
                disabled={committing || preview.total_valid === 0 || (needsDefaultProject && !defaultProject) || !canCommit}
                onClick={() => void handleCommit()}
              >
                {committing ? "Importing…" : `Import ${preview.total_valid} rows`}
              </button>
            </div>
          </div>

          {preview.sheets.map((s) => (
            <SheetCard key={s.sheet} sheet={s} />
          ))}
        </section>
      ) : null}

      {/* Result */}
      {result ? (
        <section className="panel animate-fade-up">
          <h3 className="m-0 text-lg font-bold mb-3">Import complete</h3>
          <div className="flex gap-6 text-sm">
            <Stat label="Projects" value={result.created.projects} />
            <Stat label="BOM lines" value={result.created.bom_items} />
            <Stat label="Suppliers" value={result.created.suppliers} />
          </div>
          {result.errors.length ? (
            <ul className="mt-4 space-y-1 text-xs">
              {result.errors.map((e, i) => (
                <li key={i} className="text-muted">
                  <span className="text-warning">·</span> {e}
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}

function SheetCard({ sheet }: { sheet: IngestSheetPreview }) {
  const sampleKeys = sheet.sample.length ? Object.keys(sheet.sample[0]).slice(0, 7) : [];
  return (
    <article className="panel-sm space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="font-bold text-ink">{sheet.sheet}</span>
        {sheet.entity ? (
          <span className={`badge ${ENTITY_TONE[sheet.entity]}`}>{sheet.entity}</span>
        ) : (
          <span className="badge severity-critical">unclassified</span>
        )}
        <span className="text-xs text-muted">
          {sheet.rows_valid}/{sheet.rows_total} rows valid
        </span>
      </div>

      {Object.keys(sheet.mapped).length ? (
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(sheet.mapped).map(([canon, src]) => (
            <span key={canon} className="chip text-[0.65rem]">
              {src} → <strong>{canon}</strong>
            </span>
          ))}
          {sheet.unmapped.map((h) => (
            <span key={h} className="text-[0.65rem] px-2 py-0.5 rounded-full border border-line text-muted" title="Column ignored">
              {h} → ∅
            </span>
          ))}
        </div>
      ) : null}

      {sheet.errors.length ? (
        <ul className="space-y-0.5 text-xs">
          {sheet.errors.slice(0, 6).map((e, i) => (
            <li key={i} className="text-muted">
              <span className="text-danger">·</span> {e}
            </li>
          ))}
          {sheet.errors.length > 6 ? (
            <li className="text-muted italic">… {sheet.errors.length - 6} more</li>
          ) : null}
        </ul>
      ) : null}

      {sheet.sample.length ? (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr>
                {sampleKeys.map((k) => (
                  <th key={k} className="text-left text-muted font-bold uppercase tracking-[0.08em] text-[0.6rem] pb-1 pr-4">
                    {k}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sheet.sample.map((row, i) => (
                <tr key={i} className="border-t border-line/50">
                  {sampleKeys.map((k) => (
                    <td key={k} className="py-1 pr-4 text-ink/85 whitespace-nowrap max-w-[220px] overflow-hidden text-ellipsis">
                      {row[k] === null || row[k] === undefined ? "—" : String(row[k])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </article>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="text-[0.65rem] uppercase tracking-[0.12em] text-muted font-bold">{label}</div>
      <div className="text-2xl font-bold text-accent">{value}</div>
    </div>
  );
}
