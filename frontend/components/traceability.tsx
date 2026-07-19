"use client";

import { AnimatePresence, motion } from "framer-motion";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { fetchEntityAudit, fetchTraceBom, fetchTracePo, fetchTracePr } from "@/lib/api";
import type { AuditEvent, TraceStage, TraceabilityChain } from "@/lib/types";

const STAGE_COLOR: Record<TraceStage["stage"], string> = {
  bom_item:       "#7dc4ff",
  spec:           "#b29bff",
  pr:             "#57d4c0",
  rfq:            "#57d4c0",
  quotes:         "#57d4c0",
  technical_eval: "#57d4c0",
  award:          "#f0b44c",
  po:             "#f0b44c",
  sap:            "#ff8552",
  shipment:       "#b8e54a",
  delivery:       "#57d4c0",
  invoice:        "#b8e54a",
};

const STAGE_ICON: Record<TraceStage["stage"], string> = {
  bom_item:       "◇",
  spec:           "📄",
  pr:             "📋",
  rfq:            "📨",
  quotes:         "💬",
  technical_eval: "⚙",
  award:          "★",
  po:             "✎",
  sap:            "S",
  shipment:       "🚢",
  delivery:       "✓",
  invoice:        "$",
};

type Props =
  | { kind: "bom"; id: string; }
  | { kind: "pr";  id: string; }
  | { kind: "po";  id: string; };

export function TraceabilityLadder(props: Props) {
  const [chain, setChain] = useState<TraceabilityChain | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r =
        props.kind === "bom" ? await fetchTraceBom(props.id) :
        props.kind === "pr"  ? await fetchTracePr(props.id) :
                               await fetchTracePo(props.id);
      setChain(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load trace");
    } finally {
      setLoading(false);
    }
  }, [props.kind, props.id]);

  useEffect(() => { void load(); }, [load]);

  if (loading) return <div className="panel-sm text-muted text-sm">Building traceability chain…</div>;
  if (error || !chain) return <div className="panel-sm text-muted text-sm">{error ?? "No chain available"}</div>;

  return (
    <section className="panel">
      <div className="flex items-baseline justify-between mb-3 flex-wrap gap-2">
        <div>
          <div className="text-[0.65rem] uppercase tracking-[0.14em] text-accent font-bold">
            Traceability · BOM → Delivery
          </div>
          <div className="text-xs text-muted mt-0.5">
            Root: <span className="font-mono text-ink">{chain.root_id}</span>
            {" · "}{chain.stages.filter(s => s.complete).length}/{chain.stages.length} stages complete
            {" · "}{chain.events_count} audit event(s) on file
          </div>
        </div>
        <Link
          href={`/audit?bom_item_id=${encodeURIComponent(chain.root_id)}`}
          className="text-[0.65rem] uppercase tracking-[0.12em] font-bold text-accent hover:text-accent-soft"
        >
          Full audit trail →
        </Link>
      </div>

      <div className="relative">
        {/* vertical connector */}
        <div className="absolute left-3 top-3 bottom-3 w-px bg-line" aria-hidden />
        <ol className="space-y-3">
          {chain.stages.map((s, idx) => (
            <motion.li
              key={`${s.stage}-${idx}`}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.3, delay: idx * 0.04 }}
              className="relative pl-10"
            >
              <span
                className={`absolute left-0 top-0.5 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold border-2 ${s.complete ? "bg-bg" : "bg-bg opacity-50"}`}
                style={{ borderColor: STAGE_COLOR[s.stage], color: STAGE_COLOR[s.stage] }}
              >
                {STAGE_ICON[s.stage]}
              </span>
              <div className={`panel-sm ${!s.complete ? "opacity-70" : ""}`}>
                <div className="flex items-baseline justify-between gap-3 flex-wrap">
                  <div className="font-semibold text-ink">{s.label}</div>
                  <div className="flex items-center gap-2">
                    {s.status ? (
                      <span
                        className="rounded border px-1.5 py-0.5 text-[0.6rem] font-bold uppercase tracking-wider"
                        style={{ borderColor: STAGE_COLOR[s.stage] + "55", color: STAGE_COLOR[s.stage] }}
                      >
                        {s.status}
                      </span>
                    ) : null}
                    {s.occurred_at ? (
                      <span className="text-[0.65rem] text-muted">
                        {new Date(s.occurred_at).toLocaleString()}
                      </span>
                    ) : null}
                  </div>
                </div>
                {s.detail ? (
                  <div className="text-xs text-muted mt-1">{s.detail}</div>
                ) : null}
                {s.actor ? (
                  <div className="text-[0.65rem] text-muted mt-1">by <span className="text-ink">{s.actor}</span></div>
                ) : null}
                {s.payload && Object.keys(s.payload).length > 0 ? (
                  <details className="mt-2">
                    <summary className="cursor-pointer text-[0.65rem] uppercase tracking-wider text-muted font-bold">
                      Detail
                    </summary>
                    <pre className="mt-1 text-[0.7rem] text-muted whitespace-pre-wrap break-all max-h-32 overflow-auto">
                      {JSON.stringify(s.payload, null, 2)}
                    </pre>
                  </details>
                ) : null}
              </div>
            </motion.li>
          ))}
        </ol>
      </div>
    </section>
  );
}

// ----------------------------------------------- entity audit trail mini ----

/**
 * Compact event timeline for a single entity — drop on any PR/RFQ/PO detail page.
 */
export function EntityTrail({ kind, id }: { kind: string; id: string }) {
  const [events, setEvents] = useState<AuditEvent[] | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchEntityAudit(kind, id)
      .then((r) => { if (!cancelled) setEvents(r); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [kind, id]);

  if (loading) return <div className="panel-sm text-muted text-sm">Loading trail…</div>;
  if (!events || events.length === 0) return null;

  return (
    <section className="panel">
      <div className="text-[0.65rem] uppercase tracking-[0.14em] text-accent font-bold mb-2">
        Audit trail ({events.length} events)
      </div>
      <ol className="space-y-2">
        <AnimatePresence>
          {events.map((e, i) => (
            <motion.li
              key={e.event_id}
              initial={{ opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.25, delay: Math.min(i * 0.02, 0.4) }}
              className="text-sm flex items-start gap-2 border-l-2 border-line pl-3 py-0.5"
              style={{ borderColor: e.source === "ai" ? "#b29bff" : e.source === "sap_webhook" ? "#ff8552" : undefined }}
            >
              <span className="text-[0.6rem] uppercase tracking-wider text-muted font-bold w-16 shrink-0 mt-0.5">
                {e.action.replace(/_/g, " ")}
              </span>
              <div className="flex-1 min-w-0">
                <div className="text-ink truncate">{e.summary}</div>
                <div className="text-[0.65rem] text-muted">
                  {new Date(e.occurred_at).toLocaleString()}
                  {" · "}by {e.actor}
                  {" · via "}{e.source}
                </div>
              </div>
            </motion.li>
          ))}
        </AnimatePresence>
      </ol>
    </section>
  );
}
