"use client";

import { useEffect, useState } from "react";

import { fetchBomAutofill, updateBomItem } from "@/lib/api";
import { useToast } from "@/lib/toast-context";
import type { BOMAutofillReply, BOMAutofillSuggestion } from "@/lib/types";

type Props = {
  projectId: string;
  onClose: () => void;
  onApplied: () => void;
};

export function BomAutofillModal({ projectId, onClose, onApplied }: Props) {
  const toast = useToast();
  const [reply, setReply] = useState<BOMAutofillReply | null>(null);
  const [suggestions, setSuggestions] = useState<BOMAutofillSuggestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [applyingId, setApplyingId] = useState<string | null>(null);
  const [applyingAll, setApplyingAll] = useState(false);

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchBomAutofill(projectId);
      setReply(result);
      setSuggestions(result.suggestions);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load suggestions");
    } finally {
      setLoading(false);
    }
  }

  function patchFor(s: BOMAutofillSuggestion): { category?: string; supplier_name?: string } {
    const patch: { category?: string; supplier_name?: string } = {};
    if (s.suggested_category) patch.category = s.suggested_category;
    if (s.suggested_supplier) patch.supplier_name = s.suggested_supplier;
    return patch;
  }

  async function applyOne(s: BOMAutofillSuggestion) {
    const patch = patchFor(s);
    if (!patch.category && !patch.supplier_name) return;
    setApplyingId(s.bom_item_id);
    setError(null);
    try {
      await updateBomItem(projectId, s.bom_item_id, patch);
      setSuggestions((prev) => prev.filter((x) => x.bom_item_id !== s.bom_item_id));
      toast.success(`Applied suggestions for ${s.code}`);
      onApplied();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to apply";
      setError(msg);
      toast.error(msg);
    } finally {
      setApplyingId(null);
    }
  }

  async function applyAll() {
    if (!suggestions.length) return;
    setApplyingAll(true);
    setError(null);
    let applied = 0;
    try {
      for (const s of suggestions) {
        const patch = patchFor(s);
        if (!patch.category && !patch.supplier_name) continue;
        await updateBomItem(projectId, s.bom_item_id, patch);
        applied += 1;
      }
      setSuggestions([]);
      toast.success(`Applied ${applied} BOM suggestion${applied === 1 ? "" : "s"}`);
      onApplied();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to apply all";
      setError(msg);
      toast.error(msg);
      void load();
    } finally {
      setApplyingAll(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="panel w-full max-w-4xl max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-4 gap-3">
          <div>
            <div className="text-[0.68rem] uppercase tracking-[0.14em] text-muted font-bold">
              Fix gaps · Autofill
            </div>
            <h2 className="m-0 text-xl font-bold mt-1">Review BOM suggestions</h2>
            <div className="text-sm text-muted mt-1">
              Proposed category and supplier for incomplete lines.
              {reply ? (
                <span className="ml-2 capitalize">· source: {reply.source}</span>
              ) : null}
            </div>
          </div>
          <button className="btn btn-secondary text-xs" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="flex flex-wrap gap-2 mb-4">
          <button
            className="btn btn-primary"
            onClick={() => void applyAll()}
            disabled={loading || applyingAll || !suggestions.length}
          >
            {applyingAll ? "Applying..." : `Apply all (${suggestions.length})`}
          </button>
          <button className="btn btn-secondary" onClick={() => void load()} disabled={loading}>
            {loading ? "Loading..." : "Refresh"}
          </button>
        </div>

        {error ? <div className="panel-sm text-[#ff9d9d] mb-4">{error}</div> : null}

        {loading ? (
          <div className="panel-sm text-muted">Loading suggestions...</div>
        ) : suggestions.length === 0 ? (
          <div className="panel-sm text-muted">
            {reply?.suggestions.length
              ? "All suggestions applied."
              : "No gaps found — every line already has category and supplier."}
          </div>
        ) : (
          <div className="space-y-3">
            {suggestions.map((s) => (
              <div key={s.bom_item_id} className="panel-sm">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="font-mono text-xs font-semibold text-ink">{s.code}</div>
                    <div className="text-sm text-ink mt-0.5">{s.description}</div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3 text-sm">
                      <SuggestionField
                        label="Category"
                        current={s.current_category}
                        proposed={s.suggested_category}
                      />
                      <SuggestionField
                        label="Supplier"
                        current={s.current_supplier}
                        proposed={s.suggested_supplier}
                      />
                    </div>
                    <div className="text-xs text-muted mt-2">{s.reason}</div>
                  </div>
                  <button
                    className="btn btn-secondary text-xs shrink-0"
                    onClick={() => void applyOne(s)}
                    disabled={applyingId === s.bom_item_id || applyingAll}
                  >
                    {applyingId === s.bom_item_id ? "..." : "Apply"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function SuggestionField({
  label,
  current,
  proposed,
}: {
  label: string;
  current?: string | null;
  proposed?: string | null;
}) {
  const changed = proposed && proposed !== current;
  return (
    <div>
      <div className="text-[0.62rem] uppercase tracking-[0.12em] text-muted font-bold">
        {label}
      </div>
      <div className="text-muted text-xs mt-0.5">
        Current: {current ?? "—"}
      </div>
      <div className={`text-sm mt-0.5 ${changed ? "text-accent font-semibold" : "text-ink"}`}>
        Proposed: {proposed ?? "—"}
      </div>
    </div>
  );
}
