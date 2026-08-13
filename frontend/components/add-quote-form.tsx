"use client";

import { useState } from "react";

import { addQuote, fetchQuotes, fetchRfq } from "@/lib/api";
import { useAsync } from "@/lib/use-async";
import type { CreateQuoteRequest, GatedQuoteReply, Incoterm } from "@/lib/types";

const INCOTERMS: Incoterm[] = ["EXW", "FCA", "FOB", "CIF", "CIP", "DAP", "DDP"];

export function AddQuoteForm({
  rfqNo,
  vendors,
  onSaved,
}: {
  rfqNo: string;
  vendors: string[];
  onSaved: (reply: GatedQuoteReply) => void;
}) {
  const [draft, setDraft] = useState<Partial<CreateQuoteRequest>>({
    incoterm: "CIP",
    validity_days: 30,
  });
  const [selectedVendor, setSelectedVendor] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const vendor = draft.vendor || selectedVendor;
    if (!vendor) {
      setError("Pick a vendor.");
      return;
    }
    if (!draft.unit_price_usd || !draft.lead_time_days) {
      setError("Unit price and lead time are required.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const reply = await addQuote(rfqNo, {
        vendor,
        unit_price_usd: Number(draft.unit_price_usd),
        lead_time_days: Number(draft.lead_time_days),
        incoterm: draft.incoterm ?? "CIP",
        validity_days: Number(draft.validity_days ?? 30),
        notes: draft.notes ?? null,
      });
      setDraft({ incoterm: "CIP", validity_days: 30 });
      setSelectedVendor("");
      onSaved(reply);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save quote");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={(e) => void handleSubmit(e)} className="grid grid-cols-1 md:grid-cols-3 gap-3">
      <Field label="Vendor">
        <select
          value={selectedVendor || draft.vendor || ""}
          onChange={(e) => {
            const v = e.target.value;
            setSelectedVendor(v);
            setDraft((d) => ({ ...d, vendor: v }));
          }}
        >
          <option value="">Select vendor...</option>
          {vendors.map((v) => (
            <option key={v} value={v}>{v}</option>
          ))}
        </select>
      </Field>
      <Field label="Unit Price (USD)">
        <input
          type="number"
          step="0.01"
          value={draft.unit_price_usd ?? ""}
          onChange={(e) => setDraft((d) => ({ ...d, unit_price_usd: Number(e.target.value) }))}
        />
      </Field>
      <Field label="Lead Time (days)">
        <input
          type="number"
          min={1}
          value={draft.lead_time_days ?? ""}
          onChange={(e) => setDraft((d) => ({ ...d, lead_time_days: Number(e.target.value) }))}
        />
      </Field>
      <Field label="Incoterm">
        <select
          value={draft.incoterm ?? "CIP"}
          onChange={(e) => setDraft((d) => ({ ...d, incoterm: e.target.value as Incoterm }))}
        >
          {INCOTERMS.map((i) => (
            <option key={i} value={i}>{i}</option>
          ))}
        </select>
      </Field>
      <Field label="Validity (days)">
        <input
          type="number"
          min={1}
          value={draft.validity_days ?? 30}
          onChange={(e) => setDraft((d) => ({ ...d, validity_days: Number(e.target.value) }))}
        />
      </Field>
      <Field label="Notes">
        <input
          value={draft.notes ?? ""}
          onChange={(e) => setDraft((d) => ({ ...d, notes: e.target.value }))}
          placeholder="Optional"
        />
      </Field>
      <div className="md:col-span-3 flex items-center gap-3">
        <button type="submit" className="btn btn-primary" disabled={saving}>
          {saving ? "Saving..." : "Add Quote"}
        </button>
        {error ? <span className="text-[#ff9d9d] text-sm">{error}</span> : null}
      </div>
    </form>
  );
}

export function AddQuoteModal({
  rfqNo,
  code,
  onClose,
  onSaved,
}: {
  rfqNo: string;
  code: string;
  onClose: () => void;
  onSaved: (reply: GatedQuoteReply) => void;
}) {
  const rfq = useAsync(() => fetchRfq(rfqNo), [rfqNo]);
  const quotes = useAsync(() => fetchQuotes(rfqNo), [rfqNo]);
  const quoted = new Set((quotes.data ?? []).map((q) => q.vendor));

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="panel w-full max-w-3xl max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-4 gap-3">
          <div>
            <div className="text-[0.68rem] uppercase tracking-[0.14em] text-muted font-bold">
              Add quote · {code}
            </div>
            <h2 className="m-0 text-xl font-bold mt-1">{rfqNo}</h2>
          </div>
          <button type="button" className="btn btn-secondary text-xs" onClick={onClose}>
            Close
          </button>
        </div>
        {rfq.loading ? (
          <div className="text-sm text-muted">Loading RFQ…</div>
        ) : rfq.error || !rfq.data ? (
          <div className="text-sm text-[#ff9d9d]">{rfq.error ?? "RFQ not found"}</div>
        ) : (
          <>
            <div className="flex flex-wrap gap-2 mb-4">
              {rfq.data.vendors.map((v) => (
                <span
                  key={v}
                  className={[
                    "inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold",
                    quoted.has(v) ? "bg-accent/15 text-accent" : "bg-white/5 text-muted",
                  ].join(" ")}
                >
                  {v} {quoted.has(v) ? "· quoted" : "· pending"}
                </span>
              ))}
            </div>
            <AddQuoteForm rfqNo={rfqNo} vendors={rfq.data.vendors} onSaved={onSaved} />
          </>
        )}
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
