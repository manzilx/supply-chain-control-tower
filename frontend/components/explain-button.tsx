"use client";

import { useState } from "react";

import { fetchExplain } from "@/lib/api";
import type { ExplainKind, ExplainReply } from "@/lib/types";

type Props = {
  kind: ExplainKind;
  id: string;
  label?: string;
  size?: "xs" | "sm";
};

/**
 * Drop-in "Explain this" button. Calls /api/explain and shows the LLM-generated
 * (or deterministic-fallback) brief inline below the button.
 *
 * Usage:
 *   <ExplainButton kind="po" id="SPO-00001" />
 *   <ExplainButton kind="vendor" id="Andritz Hydro" />
 *   <ExplainButton kind="project" id="HYD-MAHADEV-220" />
 */
export function ExplainButton({ kind, id, label = "Explain this", size = "xs" }: Props) {
  const [open, setOpen] = useState(false);
  const [reply, setReply] = useState<ExplainReply | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    if (open && reply) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (reply) return;
    setLoading(true);
    setError(null);
    try {
      const r = await fetchExplain(kind, id);
      setReply(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load brief");
    } finally {
      setLoading(false);
    }
  }

  const btnCls =
    size === "sm"
      ? "btn btn-secondary text-xs"
      : "text-[0.65rem] uppercase tracking-[0.12em] font-bold text-accent hover:text-accent-soft transition";

  return (
    <div className="inline-block">
      <button type="button" className={btnCls} onClick={() => void load()}>
        {open ? "Hide" : label}
      </button>

      {open ? (
        <div className="mt-2 rounded-xl border border-accent/30 bg-accent/[0.04] p-3 text-sm max-w-2xl">
          {loading ? (
            <div className="text-muted">Generating…</div>
          ) : error ? (
            <div className="text-[#ff9d9d]">{error}</div>
          ) : reply ? (
            <div className="space-y-2">
              <div className="flex items-baseline justify-between gap-3">
                <div className="font-semibold text-ink">{reply.headline}</div>
                <span className="text-[0.6rem] uppercase tracking-[0.14em] text-muted">
                  via {reply.source}
                </span>
              </div>
              <div className="text-ink/90 whitespace-pre-wrap text-sm leading-relaxed">
                {reply.body}
              </div>
              {reply.bullets && reply.bullets.length > 0 ? (
                <ul className="list-disc pl-5 space-y-0.5 text-xs text-muted">
                  {reply.bullets.map((b, i) => (
                    <li key={i}>{b}</li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
