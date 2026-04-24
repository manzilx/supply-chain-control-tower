"use client";

import { useEffect, useState } from "react";

import { draftFollowupEmail } from "@/lib/api";
import type { EmailTone, ExpediteItem, FollowupEmail } from "@/lib/types";

type Props = {
  item: ExpediteItem;
  onClose: () => void;
};

const TONE_HINT: Record<EmailTone, string> = {
  standard: "Friendly check-in.",
  firm: "Request a written recovery plan.",
  urgent: "48-hour response + daily updates.",
};

export function FollowupModal({ item, onClose }: Props) {
  const [tone, setTone] = useState<EmailTone>(
    item.urgency === "escalate" ? "urgent" : item.urgency === "nudge" ? "firm" : "standard",
  );
  const [requestDocs, setRequestDocs] = useState(true);
  const [extraNotes, setExtraNotes] = useState("");
  const [email, setEmail] = useState<FollowupEmail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    void regenerate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tone, requestDocs]);

  async function regenerate() {
    setLoading(true);
    setError(null);
    try {
      const draft = await draftFollowupEmail(item.po_number, {
        tone,
        request_documents: requestDocs,
        extra_notes: extraNotes || null,
      });
      setEmail(draft);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to draft email");
    } finally {
      setLoading(false);
    }
  }

  function copy() {
    if (!email) return;
    const full = `To: ${email.to_placeholder}\nSubject: ${email.subject}\n\n${email.body}`;
    navigator.clipboard.writeText(full).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

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
              Follow-up draft · {item.po_number}
            </div>
            <h2 className="m-0 text-xl font-bold mt-1">{item.supplier_name}</h2>
            <div className="text-sm text-muted mt-1">
              {item.description || item.sku} · due in {item.due_in_days}d · slip prob {item.slip_probability_pct}%
            </div>
          </div>
          <button className="btn btn-secondary text-xs" onClick={onClose}>Close</button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
          <label className="flex flex-col gap-1">
            <span className="text-[0.65rem] uppercase tracking-[0.12em] text-muted font-bold">Tone</span>
            <select value={tone} onChange={(e) => setTone(e.target.value as EmailTone)}>
              <option value="standard">Standard</option>
              <option value="firm">Firm</option>
              <option value="urgent">Urgent</option>
            </select>
            <span className="text-xs text-muted">{TONE_HINT[tone]}</span>
          </label>
          <label className="flex items-center gap-2 text-sm pt-6 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={requestDocs}
              onChange={(e) => setRequestDocs(e.target.checked)}
              style={{ width: "1rem" }}
            />
            <span className="text-muted">Request supporting documents</span>
          </label>
          <label className="flex flex-col gap-1 md:col-span-3">
            <span className="text-[0.65rem] uppercase tracking-[0.12em] text-muted font-bold">Extra context (optional)</span>
            <input
              value={extraNotes}
              onChange={(e) => setExtraNotes(e.target.value)}
              placeholder="Anything specific to mention..."
            />
          </label>
        </div>

        <div className="flex gap-2 mb-4">
          <button className="btn btn-primary" onClick={() => void regenerate()} disabled={loading}>
            {loading ? "Drafting..." : "Regenerate"}
          </button>
          <button className="btn btn-secondary" onClick={copy} disabled={!email}>
            {copied ? "Copied!" : "Copy"}
          </button>
        </div>

        {error ? <div className="panel-sm text-[#ff9d9d] mb-4">{error}</div> : null}

        {email ? (
          <div className="panel-sm">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3 text-sm">
              <Field label="To">
                <span className="font-mono text-xs">{email.to_placeholder}</span>
              </Field>
              <Field label="Tone">
                <span className="capitalize">{email.tone}</span>
              </Field>
            </div>
            <Field label="Subject">
              <input value={email.subject} readOnly className="font-mono text-xs" />
            </Field>
            <div className="mt-3">
              <Field label="Body">
                <textarea
                  rows={16}
                  value={email.body}
                  readOnly
                />
              </Field>
            </div>
            {email.requested_documents.length ? (
              <div className="mt-3">
                <div className="text-[0.65rem] uppercase tracking-[0.12em] text-muted font-bold mb-2">
                  Requested documents
                </div>
                <div className="flex flex-wrap gap-2">
                  {email.requested_documents.map((d) => (
                    <span key={d} className="inline-flex rounded-full px-2.5 py-1 text-xs font-semibold bg-white/5 text-muted">
                      {d}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[0.65rem] uppercase tracking-[0.12em] text-muted font-bold">{label}</span>
      {children}
    </label>
  );
}
