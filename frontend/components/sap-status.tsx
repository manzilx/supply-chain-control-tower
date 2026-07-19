"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";

import { submitPoToSap, submitPrToSap } from "@/lib/api";
import type { SapStatus, SapSubmitReply } from "@/lib/types";

// ---------------------------------------------------------------- badge ----

const SAP_TONE: Record<SapStatus, string> = {
  draft:       "bg-zinc-500/15 text-zinc-300 border-zinc-500/40",
  submitting:  "bg-amber-500/15 text-amber-300 border-amber-500/40 animate-pulse",
  synced:      "bg-emerald-500/15 text-emerald-300 border-emerald-500/40",
  failed:      "bg-rose-500/15 text-rose-300 border-rose-500/40",
};

const SAP_LABEL: Record<SapStatus, string> = {
  draft: "Draft (CT only)",
  submitting: "Submitting to SAP…",
  synced: "Live in SAP",
  failed: "SAP failed",
};

export function SapStatusBadge({
  status,
  sapDocNo,
}: {
  status?: SapStatus;
  sapDocNo?: string | null;
}) {
  const s: SapStatus = status ?? "draft";
  return (
    <AnimatePresence mode="wait">
      <motion.span
        key={s + (sapDocNo ?? "")}
        initial={{ scale: 0.92, opacity: 0.4 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.92, opacity: 0 }}
        transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
        className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-[0.65rem] font-bold uppercase tracking-[0.08em] ${SAP_TONE[s]}`}
        title={sapDocNo ? `SAP doc: ${sapDocNo}` : undefined}
      >
        <span>SAP</span>
        <span className="opacity-50">·</span>
        <span>{SAP_LABEL[s]}</span>
        {sapDocNo ? <span className="opacity-70 font-mono">· {sapDocNo}</span> : null}
      </motion.span>
    </AnimatePresence>
  );
}

// ---------------------------------------------------------------- button ----

type SubmitProps = {
  kind: "pr" | "po";
  refNo: string;
  currentStatus?: SapStatus;
  sapDocNo?: string | null;
  onResult?: (reply: SapSubmitReply) => void;
};

export function SubmitToSapButton({ kind, refNo, currentStatus, sapDocNo, onResult }: SubmitProps) {
  const [busy, setBusy] = useState(false);
  const [latest, setLatest] = useState<SapSubmitReply | null>(null);

  const status: SapStatus = latest?.sap_status ?? currentStatus ?? "draft";

  async function submit() {
    setBusy(true);
    try {
      const reply = kind === "pr" ? await submitPrToSap(refNo) : await submitPoToSap(refNo);
      setLatest(reply);
      onResult?.(reply);
    } finally {
      setBusy(false);
    }
  }

  const disabled = busy || status === "synced" || status === "submitting";
  const label =
    status === "synced"
      ? "Already in SAP"
      : status === "submitting" || busy
      ? "Submitting…"
      : status === "failed"
      ? "Retry submit to SAP"
      : "Submit to SAP";

  return (
    <div className="flex flex-col gap-1.5 items-start">
      <motion.button
        type="button"
        onClick={() => void submit()}
        disabled={disabled}
        whileTap={{ scale: 0.96 }}
        whileHover={!disabled ? { scale: 1.03 } : undefined}
        animate={busy ? { boxShadow: ["0 0 0 0 rgba(87,212,192,0)", "0 0 0 8px rgba(87,212,192,0.15)", "0 0 0 0 rgba(87,212,192,0)"] } : { boxShadow: "0 0 0 0 rgba(87,212,192,0)" }}
        transition={{ duration: busy ? 1.2 : 0.2, repeat: busy ? Infinity : 0, ease: "easeInOut" }}
        className={`btn ${status === "failed" ? "btn-danger" : "btn-primary"} text-xs disabled:opacity-50 disabled:cursor-not-allowed`}
      >
        {label}
      </motion.button>
      <SapStatusBadge status={status} sapDocNo={latest?.sap_pr_no ?? latest?.sap_po_no ?? sapDocNo} />
      {(latest?.sap_error || status === "failed") && (
        <div className="text-[0.7rem] text-rose-300 max-w-md leading-snug">
          {latest?.sap_error ?? "Submission failed — see Settings → Integrations for details."}
        </div>
      )}
    </div>
  );
}
