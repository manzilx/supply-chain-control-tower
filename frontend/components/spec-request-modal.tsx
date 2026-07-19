"use client";

import { useEffect, useState } from "react";

import { fetchSpecRequest } from "@/lib/api";
import { useToast } from "@/lib/toast-context";
import type { SpecRequestReply } from "@/lib/types";

type Props = {
  projectId: string;
  bomItemId: string;
  code: string;
  onClose: () => void;
};

export function SpecRequestModal({ projectId, bomItemId, code, onClose }: Props) {
  const toast = useToast();
  const [draft, setDraft] = useState<SpecRequestReply | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, bomItemId]);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchSpecRequest(projectId, bomItemId);
      setDraft(result);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to draft email";
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }

  function copy() {
    if (!draft) return;
    const full = `To: ${draft.to_placeholder}\nSubject: ${draft.subject}\n\n${draft.body}`;
    navigator.clipboard.writeText(full).then(() => {
      setCopied(true);
      toast.success("Email copied to clipboard");
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
              Spec request · {code}
            </div>
            <h2 className="m-0 text-xl font-bold mt-1">Draft engineering email</h2>
            <div className="text-sm text-muted mt-1">
              Copy and send from your mail client.
              {draft ? (
                <span className="ml-2 capitalize">· source: {draft.source}</span>
              ) : null}
            </div>
          </div>
          <button className="btn btn-secondary text-xs" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="flex flex-wrap gap-2 mb-4">
          <button className="btn btn-primary" onClick={() => void load()} disabled={loading}>
            {loading ? "Drafting..." : "Regenerate"}
          </button>
          <button className="btn btn-secondary" onClick={copy} disabled={!draft}>
            {copied ? "Copied!" : "Copy"}
          </button>
        </div>

        {error ? <div className="panel-sm text-[#ff9d9d] mb-4">{error}</div> : null}

        {draft ? (
          <div className="panel-sm">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3 text-sm">
              <Field label="To">
                <span className="font-mono text-xs">{draft.to_placeholder}</span>
              </Field>
            </div>
            <Field label="Subject">
              <input value={draft.subject} readOnly className="font-mono text-xs" />
            </Field>
            <div className="mt-3">
              <Field label="Body">
                <textarea rows={14} value={draft.body} readOnly />
              </Field>
            </div>
          </div>
        ) : loading ? (
          <div className="panel-sm text-muted">Drafting email...</div>
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
