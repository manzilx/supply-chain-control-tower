"use client";

import { useEffect, useMemo, useState } from "react";

import { fetchSuggestedVendors, issueRfq } from "@/lib/api";
import { useAsync } from "@/lib/use-async";

export function IssueRfqForm({
  prNo,
  onIssued,
}: {
  prNo: string;
  onIssued: (rfqNo: string) => void;
}) {
  const suggestions = useAsync(() => fetchSuggestedVendors(prNo), [prNo]);
  const [vendors, setVendors] = useState<string[]>([]);
  const [newVendor, setNewVendor] = useState("");
  const [dueInDays, setDueInDays] = useState(10);
  const [notes, setNotes] = useState("");
  const [issuing, setIssuing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (vendors.length === 0 && suggestions.data && suggestions.data.length > 0) {
      setVendors(suggestions.data.slice(0, 3));
    }
  }, [suggestions.data, vendors.length]);

  const canIssue = useMemo(
    () => vendors.length > 0 && !issuing,
    [vendors.length, issuing],
  );

  function toggleVendor(name: string) {
    setVendors((v) => (v.includes(name) ? v.filter((n) => n !== name) : [...v, name]));
  }

  function addVendor() {
    const name = newVendor.trim();
    if (!name || vendors.includes(name)) return;
    setVendors((v) => [...v, name]);
    setNewVendor("");
  }

  async function handleIssue() {
    if (!canIssue) return;
    setIssuing(true);
    setError(null);
    try {
      const rfq = await issueRfq({
        pr_no: prNo,
        vendors,
        due_in_days: dueInDays,
        notes: notes || null,
      });
      onIssued(rfq.rfq_no);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to issue RFQ");
      setIssuing(false);
    }
  }

  return (
    <div className="space-y-4">
      <Field label="Vendors">
        <div className="space-y-2">
          <div className="flex flex-wrap gap-2">
            {vendors.length === 0 ? (
              <span className="text-sm text-muted">No vendors selected.</span>
            ) : (
              vendors.map((v) => (
                <button
                  key={v}
                  type="button"
                  onClick={() => toggleVendor(v)}
                  className="badge severity-low hover:opacity-75 cursor-pointer"
                >
                  {v} ·×
                </button>
              ))
            )}
          </div>
          {suggestions.data && suggestions.data.length > 0 ? (
            <div className="text-xs text-muted">
              Suggestions:
              <div className="flex flex-wrap gap-2 mt-1">
                {suggestions.data
                  .filter((s) => !vendors.includes(s))
                  .map((s) => (
                    <button
                      key={s}
                      type="button"
                      onClick={() => toggleVendor(s)}
                      className="text-xs px-2 py-1 rounded-full bg-white/5 text-ink hover:bg-white/10"
                    >
                      + {s}
                    </button>
                  ))}
              </div>
            </div>
          ) : null}
          <div className="flex gap-2">
            <input
              placeholder="Add vendor by name..."
              value={newVendor}
              onChange={(e) => setNewVendor(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addVendor()}
            />
            <button type="button" className="btn btn-secondary" onClick={addVendor}>
              Add
            </button>
          </div>
        </div>
      </Field>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Field label="Due in (days)">
          <input
            type="number"
            min={1}
            value={dueInDays}
            onChange={(e) => setDueInDays(Number(e.target.value) || 10)}
          />
        </Field>
      </div>
      <Field label="Notes to vendors">
        <textarea
          rows={3}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Spec references, delivery terms, inspection requirements..."
        />
      </Field>

      {error ? <div className="text-[#ff9d9d] text-sm">{error}</div> : null}

      <div>
        <button type="button" className="btn btn-primary" onClick={() => void handleIssue()} disabled={!canIssue}>
          {issuing ? "Issuing..." : `Issue RFQ to ${vendors.length} vendor${vendors.length === 1 ? "" : "s"}`}
        </button>
      </div>
    </div>
  );
}

export function IssueRfqModal({
  prNo,
  code,
  onClose,
  onIssued,
}: {
  prNo: string;
  code: string;
  onClose: () => void;
  onIssued: (rfqNo: string) => void;
}) {
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
        <div className="flex items-start justify-between mb-4 gap-3">
          <div>
            <div className="text-[0.68rem] uppercase tracking-[0.14em] text-muted font-bold">
              Issue RFQ · {code}
            </div>
            <h2 className="m-0 text-xl font-bold mt-1">{prNo}</h2>
            <p className="text-sm text-muted mt-1 m-0">
              Pick vendors to invite. Suggestions come from the approved vendor list and the BOM item&apos;s preferred supplier.
            </p>
          </div>
          <button type="button" className="btn btn-secondary text-xs" onClick={onClose}>
            Close
          </button>
        </div>
        <IssueRfqForm prNo={prNo} onIssued={onIssued} />
      </div>
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
