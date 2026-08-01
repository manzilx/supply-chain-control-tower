"use client";

import { useEffect, useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { Skeleton, SkeletonCard } from "@/components/skeleton";
import {
  confirmGrn,
  fetchGrnPhotoObjectUrl,
  fetchStoreGrn,
  fetchStoreGrns,
  rejectGrn,
} from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatTimestamp } from "@/lib/format";
import { useToast } from "@/lib/toast-context";
import { useAsync } from "@/lib/use-async";
import type { ConfirmLine, GrnLineOut, GrnMatchStatus, GrnStatus } from "@/lib/types";

const STATUS_TONE: Record<GrnStatus, string> = {
  captured: "severity-medium",
  extracting: "severity-medium",
  matched: "severity-medium",
  suggested: "severity-high",
  triage: "severity-critical",
  confirmed: "severity-low",
  cancelled: "text-muted",
  superseded: "text-muted",
};

const MATCH_TONE: Record<GrnMatchStatus, string> = {
  unmatched: "severity-critical",
  suggested: "severity-high",
  auto: "severity-medium",
  confirmed: "severity-low",
  no_po: "text-muted",
};

// A machine suggestion is only pre-selected at or above this score. Anything
// weaker is shown but left unticked — the storekeeper has to choose it.
const SUGGEST_PRESELECT_SCORE = 0.6;

type LineEdit = {
  line_no: number;
  po_no: string | null;
  no_po: boolean;
  qty_received: number;
  qty_damaged: number;
  qty_rejected: number;
  batch_no: string;
};

function initLineEdits(lines: GrnLineOut[]): Record<number, LineEdit> {
  const out: Record<number, LineEdit> = {};
  for (const line of lines) {
    const top = (line.match_candidates ?? [])[0];
    // Unmatched lines start with nothing selected — neither a candidate nor
    // "No PO" — so a sub-threshold guess can never be one click from posting
    // stock against the wrong PO.
    let poNo: string | null = null;
    if (line.match_status === "auto" || line.match_status === "confirmed") {
      poNo = line.po_no;
    } else if (line.match_status === "suggested" && top && top.score >= SUGGEST_PRESELECT_SCORE) {
      poNo = top.po_no;
    }
    out[line.line_no] = {
      line_no: line.line_no,
      po_no: line.match_status === "no_po" ? null : poNo,
      no_po: line.match_status === "no_po",
      qty_received: line.qty_received,
      qty_damaged: line.qty_damaged,
      qty_rejected: line.qty_rejected,
      batch_no: line.batch_no ?? "",
    };
  }
  return out;
}

/** A line is only confirmable once a human has picked a PO or said "No PO". */
function isLineResolved(edit: LineEdit | undefined): boolean {
  return Boolean(edit && (edit.no_po || edit.po_no));
}

export default function GrnTriagePage() {
  const list = useAsync(() => fetchStoreGrns({ triage: true }), []);
  const { permissions } = useAuth();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const canConfirm =
    permissions.includes("grn:confirm") || permissions.includes("grn:*") || permissions.includes("*");

  const grns = list.data ?? [];

  // Drop the selection once its GRN has left the triage queue (confirmed/rejected).
  useEffect(() => {
    if (selectedId && grns.length && !grns.some((g) => g.grn_id === selectedId)) {
      setSelectedId(null);
    }
  }, [grns, selectedId]);

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Site Store"
        title="GRN Triage"
        description="Photo-captured goods receipts waiting on a human match against open POs before they post to stock."
        right={
          <button className="btn btn-secondary" onClick={() => list.reload()}>
            Refresh
          </button>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-[340px_minmax(0,1fr)] gap-4 items-start">
        <div className="panel-sm p-0 overflow-hidden">
          <div className="px-4 py-3 border-b border-line text-xs text-muted">
            {list.loading ? "Loading…" : `${grns.length} in triage`}
          </div>
          {list.loading ? (
            <div className="p-4 space-y-3">
              <SkeletonCard />
              <SkeletonCard />
            </div>
          ) : list.error ? (
            <div className="p-4 text-[#ff9d9d] text-sm">{list.error}</div>
          ) : grns.length === 0 ? (
            <div className="p-4">
              <EmptyState
                title="Nothing in triage"
                hint="Captured GRNs needing a manual PO match will show up here."
              />
            </div>
          ) : (
            <div className="max-h-[70vh] overflow-y-auto divide-y divide-line">
              {grns.map((g) => (
                <button
                  key={g.grn_id}
                  onClick={() => setSelectedId(g.grn_id)}
                  className={`w-full text-left px-4 py-3 transition-colors ${
                    selectedId === g.grn_id ? "bg-white/[0.06]" : "hover:bg-white/[0.03]"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-ink truncate">
                      {g.vendor_name ?? "Unknown vendor"}
                    </span>
                    <span className={`badge ${STATUS_TONE[g.status]}`}>{g.status}</span>
                  </div>
                  <div className="text-xs text-muted mt-1">
                    {g.challan_no ? `Challan ${g.challan_no}` : "No challan #"} · {g.line_count} line
                    {g.line_count === 1 ? "" : "s"}
                  </div>
                  <div className="text-xs text-muted mt-0.5">{formatTimestamp(g.observed_at)}</div>
                </button>
              ))}
            </div>
          )}
        </div>

        <div>
          {!selectedId ? (
            <EmptyState
              title="Select a GRN"
              hint="Pick a captured receipt on the left to review its photo and lines."
            />
          ) : (
            <GrnDetailPanel
              grnId={selectedId}
              canConfirm={canConfirm}
              onDone={() => {
                setSelectedId(null);
                list.reload();
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function GrnDetailPanel({
  grnId,
  canConfirm,
  onDone,
}: {
  grnId: string;
  canConfirm: boolean;
  onDone: () => void;
}) {
  const { data: grn, loading, error } = useAsync(() => fetchStoreGrn(grnId), [grnId]);
  const toast = useToast();
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [photoError, setPhotoError] = useState<string | null>(null);
  const [zoomed, setZoomed] = useState(false);
  const [lineEdits, setLineEdits] = useState<Record<number, LineEdit>>({});
  const [confirming, setConfirming] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("");

  useEffect(() => {
    if (grn) setLineEdits(initLineEdits(grn.lines));
    setZoomed(false);
    setRejectOpen(false);
    setRejectReason("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [grn?.grn_id]);

  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;
    setPhotoUrl(null);
    setPhotoError(null);
    fetchGrnPhotoObjectUrl(grnId)
      .then((url) => {
        if (cancelled) {
          URL.revokeObjectURL(url);
          return;
        }
        objectUrl = url;
        setPhotoUrl(url);
      })
      .catch((err) => {
        if (!cancelled) setPhotoError(err instanceof Error ? err.message : "Could not load photo");
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [grnId]);

  function updateLine(lineNo: number, patch: Partial<LineEdit>) {
    setLineEdits((prev) => ({ ...prev, [lineNo]: { ...prev[lineNo], ...patch } }));
  }

  async function handleConfirm() {
    if (!grn) return;
    setConfirming(true);
    try {
      const lines: ConfirmLine[] = grn.lines.map((line) => {
        const edit = lineEdits[line.line_no];
        return {
          line_no: line.line_no,
          po_no: edit.no_po ? null : edit.po_no,
          no_po: edit.no_po,
          qty_received: edit.qty_received,
          qty_damaged: edit.qty_damaged,
          qty_rejected: edit.qty_rejected,
          batch_no: edit.batch_no || null,
        };
      });
      const reply = await confirmGrn(grn.grn_id, { lines });
      toast.success(
        `${reply.grn_no ?? reply.grn_id} confirmed — ${reply.pos_delivered.length} PO(s) delivered, ${reply.ledger_entries} ledger entries posted`,
      );
      onDone();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not confirm GRN");
    } finally {
      setConfirming(false);
    }
  }

  async function handleReject() {
    if (!grn || !rejectReason.trim()) return;
    setRejecting(true);
    try {
      await rejectGrn(grn.grn_id, rejectReason.trim());
      toast.warn(`${grn.grn_no ?? grn.grn_id} rejected`);
      onDone();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not reject GRN");
    } finally {
      setRejecting(false);
    }
  }

  if (loading) {
    return (
      <div className="space-y-3">
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }
  if (error || !grn) {
    return (
      <div className="panel-sm border-[rgba(255,117,117,0.3)] text-[#ff9d9d]">
        {error ?? "GRN not found"}
      </div>
    );
  }

  const unresolved = grn.lines.filter((line) => !isLineResolved(lineEdits[line.line_no])).length;

  return (
    <div className="space-y-4">
      <div className="panel-sm flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="text-[0.68rem] uppercase tracking-[0.14em] text-muted font-bold">
            {grn.grn_no ?? grn.grn_id}
          </div>
          <h2 className="m-0 text-lg font-bold mt-1">
            {grn.vendor_name ?? grn.vendor_name_raw ?? "Unknown vendor"}
          </h2>
          <div className="text-xs text-muted mt-1">
            {grn.challan_no ? `Challan ${grn.challan_no}` : "No challan #"} ·{" "}
            {grn.source_kind.replace(/_/g, " ")} · {formatTimestamp(grn.observed_at)}
          </div>
        </div>
        <span className={`badge ${STATUS_TONE[grn.status]}`}>{grn.status}</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[280px_minmax(0,1fr)] gap-4 items-start">
        <div className="overflow-auto rounded-lg border border-line bg-black/20 max-h-[480px]">
          {photoUrl ? (
            <img
              src={photoUrl}
              alt="GRN challan photo"
              onClick={() => setZoomed((z) => !z)}
              className={`w-full ${zoomed ? "cursor-zoom-out" : "cursor-zoom-in"}`}
              style={zoomed ? { transform: "scale(1.8)", transformOrigin: "top left" } : undefined}
            />
          ) : photoError ? (
            <div className="p-4 text-xs text-[#ff9d9d]">{photoError}</div>
          ) : (
            <div className="p-4">
              <Skeleton height={280} />
            </div>
          )}
        </div>

        <div className="space-y-3">
          {grn.lines.map((line) => {
            const edit = lineEdits[line.line_no];
            if (!edit) return null;
            const candidates = line.match_candidates ?? [];
            return (
              <div key={line.line_no} className="panel-sm">
                <div className="flex items-start justify-between gap-3 flex-wrap mb-2">
                  <div>
                    <div className="text-xs text-muted">Line {line.line_no}</div>
                    <div className="font-semibold text-ink">{line.description_raw}</div>
                    <div className="text-xs text-muted mt-0.5">
                      Extracted {line.qty_challan ?? "—"} {line.uom_raw ?? line.uom ?? ""}
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {line.over_receipt ? <span className="badge severity-high">over receipt</span> : null}
                    <span className={`badge ${MATCH_TONE[line.match_status]}`}>
                      {line.match_status.replace(/_/g, " ")}
                    </span>
                  </div>
                </div>

                <div className="space-y-1.5 mb-3">
                  {candidates.map((c, idx) => (
                    <label key={c.po_no} className="flex flex-wrap items-center gap-2 text-sm cursor-pointer">
                      <input
                        type="radio"
                        name={`po-${line.line_no}`}
                        checked={!edit.no_po && edit.po_no === c.po_no}
                        onChange={() => updateLine(line.line_no, { po_no: c.po_no, no_po: false })}
                        style={{ width: "auto" }}
                      />
                      {idx === 0 && line.match_status === "suggested" ? (
                        <span className="text-[0.58rem] uppercase tracking-[0.1em] text-accent font-bold border border-line rounded px-1.5 py-0.5">
                          suggested
                        </span>
                      ) : null}
                      <span className="font-mono text-xs text-ink">{c.po_no}</span>
                      <span className="text-muted">{c.vendor}</span>
                      <span className="text-muted">{c.code}</span>
                      <span className="text-xs text-accent">{Math.round(c.score * 100)}%</span>
                      <span className="text-xs text-muted">
                        {c.remaining_qty} {c.uom} left
                      </span>
                    </label>
                  ))}
                  <label className="flex items-center gap-2 text-sm cursor-pointer">
                    <input
                      type="radio"
                      name={`po-${line.line_no}`}
                      checked={edit.no_po}
                      onChange={() => updateLine(line.line_no, { po_no: null, no_po: true })}
                      style={{ width: "auto" }}
                    />
                    <span className="text-muted">No PO (free-issue / non-PO receipt)</span>
                  </label>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  <label className="flex flex-col gap-1">
                    <span className="text-[0.62rem] uppercase tracking-[0.1em] text-muted font-bold">
                      Qty received
                    </span>
                    <input
                      type="number"
                      min={0}
                      value={edit.qty_received}
                      onChange={(e) =>
                        updateLine(line.line_no, { qty_received: Number(e.target.value || 0) })
                      }
                    />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-[0.62rem] uppercase tracking-[0.1em] text-muted font-bold">
                      Qty damaged
                    </span>
                    <input
                      type="number"
                      min={0}
                      value={edit.qty_damaged}
                      onChange={(e) =>
                        updateLine(line.line_no, { qty_damaged: Number(e.target.value || 0) })
                      }
                    />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-[0.62rem] uppercase tracking-[0.1em] text-muted font-bold">
                      Qty rejected
                    </span>
                    <input
                      type="number"
                      min={0}
                      value={edit.qty_rejected}
                      onChange={(e) =>
                        updateLine(line.line_no, { qty_rejected: Number(e.target.value || 0) })
                      }
                    />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-[0.62rem] uppercase tracking-[0.1em] text-muted font-bold">
                      Batch #
                    </span>
                    <input
                      value={edit.batch_no}
                      onChange={(e) => updateLine(line.line_no, { batch_no: e.target.value })}
                    />
                  </label>
                </div>

                <div className="text-xs text-muted mt-2">
                  Damaged and rejected quantities are recorded against the GRN but never added to
                  stock figures.
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="panel-sm">
        {rejectOpen ? (
          <div className="flex flex-wrap gap-2 items-end">
            <label className="flex-1 min-w-[240px] flex flex-col gap-1">
              <span className="text-[0.65rem] uppercase tracking-[0.12em] text-muted font-bold">
                Rejection reason (required)
              </span>
              <input
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                placeholder="Why is this GRN being rejected?"
              />
            </label>
            <button
              className="btn btn-secondary"
              onClick={() => void handleReject()}
              disabled={rejecting || !rejectReason.trim()}
            >
              {rejecting ? "Rejecting…" : "Confirm reject"}
            </button>
            <button className="btn btn-secondary" onClick={() => setRejectOpen(false)} disabled={rejecting}>
              Cancel
            </button>
          </div>
        ) : (
          <div className="flex flex-wrap gap-2 items-center">
            <button
              className="btn btn-primary"
              onClick={() => void handleConfirm()}
              disabled={!canConfirm || confirming || unresolved > 0}
              title={
                !canConfirm
                  ? "Requires grn:confirm permission"
                  : unresolved > 0
                    ? "Every line needs a PO or “No PO” before this GRN can post to stock"
                    : undefined
              }
            >
              {confirming ? "Confirming…" : "Confirm"}
            </button>
            <button className="btn btn-secondary" onClick={() => setRejectOpen(true)}>
              Reject
            </button>
            {unresolved > 0 ? (
              <span className="text-xs text-muted">
                {unresolved} line{unresolved === 1 ? "" : "s"} still need a PO selection
              </span>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}
