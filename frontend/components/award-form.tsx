"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { awardRfq, fetchQuoteComparison, fetchTbe } from "@/lib/api";
import { useAsync } from "@/lib/use-async";
import type { CombinedEvaluation, GatedAwardReply, TBE } from "@/lib/types";

type TbeAwardState =
  | { mode: "tbe"; target: CombinedEvaluation; rationale: string | null }
  | { mode: "blocked"; reason: string; target?: CombinedEvaluation }
  | { mode: "not_run" }
  | { mode: "no_data" };

function resolveTbeAward(tbe: TBE | null | undefined): TbeAwardState {
  if (!tbe || tbe.combined.length === 0) return { mode: "no_data" };
  if (tbe.technical_evaluations.length === 0) return { mode: "not_run" };

  const leader =
    tbe.combined.find((c) => c.combined_rank === 1) ??
    [...tbe.combined].sort((a, b) => a.combined_rank - b.combined_rank)[0];

  if (leader.disqualified) {
    return {
      mode: "blocked",
      target: leader,
      reason: `Combined #1 (${leader.vendor}) is disqualified on mandatory technical criteria. Resolve the evaluation before awarding.`,
    };
  }

  return {
    mode: "tbe",
    target: leader,
    rationale: tbe.recommendation_rationale ?? null,
  };
}

export function AwardForm({
  rfqNo,
  onAwarded,
  tbeHref = "#tbe-panel",
  reloadKey = 0,
}: {
  rfqNo: string;
  onAwarded: (reply: GatedAwardReply) => void;
  tbeHref?: string;
  reloadKey?: number;
}) {
  const comparison = useAsync(() => fetchQuoteComparison(rfqNo), [rfqNo, reloadKey]);
  const tbe = useAsync(() => fetchTbe(rfqNo), [rfqNo, reloadKey]);
  const tbeAward = useMemo(() => resolveTbeAward(tbe.data), [tbe.data]);
  const commercialWinner = comparison.data?.evaluations[0] ?? null;

  const [awardRationale, setAwardRationale] = useState("");
  const [awarding, setAwarding] = useState(false);
  const [awardErr, setAwardErr] = useState<string | null>(null);

  async function handleAward(
    quoteId: string,
    opts?: { confirmMessage?: string; rationale?: string },
  ) {
    const message = opts?.confirmMessage ?? "Award this quote and auto-draft a PO?";
    if (!confirm(message)) return;
    setAwarding(true);
    setAwardErr(null);
    try {
      const reply = await awardRfq(rfqNo, {
        quote_id: quoteId,
        rationale: (opts?.rationale ?? awardRationale) || null,
      });
      onAwarded(reply);
      if (reply.status === "pending_approval") {
        setAwarding(false);
      }
    } catch (err) {
      setAwardErr(err instanceof Error ? err.message : "Failed to award RFQ");
      setAwarding(false);
    }
  }

  function buildTbeConfirmMessage(target: CombinedEvaluation, rationale: string | null): string {
    const lines = [
      `Award to ${target.vendor} (TBE combined #1, score ${target.combined_score.toFixed(1)})?`,
      `Commercial ${target.commercial_score.toFixed(0)} · Technical ${target.technical_score} · ${target.deviations_count} deviation(s).`,
    ];
    if (rationale) lines.push("", rationale);
    lines.push("", "Proceed and auto-draft a PO?");
    return lines.join("\n");
  }

  function handleAwardRecommended() {
    if (tbeAward.mode !== "tbe") return;
    void handleAward(tbeAward.target.quote_id, {
      confirmMessage: buildTbeConfirmMessage(tbeAward.target, tbeAward.rationale),
    });
  }

  function handleCommercialOverride() {
    if (!commercialWinner) return;
    void handleAward(commercialWinner.quote_id, {
      confirmMessage: [
        `Commercial-only override: award to ${commercialWinner.vendor} (commercial #1)?`,
        "",
        "This bypasses technical bid evaluation. Use only when TBE has not been completed.",
        "",
        "Proceed and auto-draft a PO?",
      ].join("\n"),
    });
  }

  if (comparison.loading && !comparison.data) {
    return <EmptyState title="Loading commercial ranking..." />;
  }
  if (!comparison.data || comparison.data.evaluations.length === 0) {
    return <EmptyState title="Award needs quotes" />;
  }

  return (
    <div className="space-y-4">
      {tbe.loading ? (
        <EmptyState title="Loading TBE recommendation..." />
      ) : tbeAward.mode === "tbe" ? (
        <div className="panel-sm space-y-3 border border-emerald-500/30 bg-emerald-500/[0.04]">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div>
              <div className="text-[0.65rem] uppercase tracking-[0.12em] text-emerald-300 font-bold">
                TBE recommended
              </div>
              <div className="text-lg font-bold text-ink mt-1">
                {tbeAward.target.vendor}
                <span className="text-sm text-muted font-normal ml-2">
                  combined {tbeAward.target.combined_score.toFixed(1)}
                </span>
              </div>
              <div className="text-xs text-muted mt-1">
                Commercial {tbeAward.target.commercial_score.toFixed(0)} · Technical {tbeAward.target.technical_score}
                · rank #{tbeAward.target.combined_rank}
                {tbeAward.target.deviations_count > 0
                  ? ` · ${tbeAward.target.deviations_count} deviation(s)`
                  : ""}
              </div>
            </div>
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleAwardRecommended}
              disabled={awarding}
            >
              {awarding ? "Awarding..." : `Award recommended (${tbeAward.target.vendor})`}
            </button>
          </div>
          {tbeAward.rationale ? (
            <p className="text-sm text-ink leading-relaxed m-0">{tbeAward.rationale}</p>
          ) : null}
        </div>
      ) : tbeAward.mode === "blocked" ? (
        <div className="panel-sm border border-rose-500/30 bg-rose-500/[0.04] text-sm">
          <div className="font-bold text-rose-300 mb-1">Award blocked</div>
          <p className="text-ink m-0">{tbeAward.reason}</p>
          <Link href={tbeHref} className="inline-block mt-2 text-accent text-xs hover:underline">
            Review TBE panel →
          </Link>
        </div>
      ) : tbeAward.mode === "not_run" ? (
        <div className="panel-sm space-y-3">
          <div>
            <div className="font-bold text-ink">Run TBE before awarding</div>
            <p className="text-sm text-muted mt-1 m-0">
              Technical bid evaluation has not been completed. Score vendors in the TBE panel, then award the combined #1.
            </p>
            <Link href={tbeHref} className="inline-block mt-2 text-accent text-sm hover:underline">
              Go to Technical Bid Evaluation →
            </Link>
          </div>
          {commercialWinner ? (
            <div className="pt-3 border-t border-line">
              <p className="text-xs text-muted m-0 mb-2">
                Emergency override — awards commercial #1 without technical evaluation.
              </p>
              <button
                type="button"
                className="btn btn-secondary text-xs"
                onClick={handleCommercialOverride}
                disabled={awarding}
              >
                {awarding ? "Awarding..." : `Commercial-only override (${commercialWinner.vendor})`}
              </button>
            </div>
          ) : null}
        </div>
      ) : (
        <EmptyState title="Award needs quotes and TBE data" />
      )}

      <div className="space-y-2">
        <div className="text-[0.65rem] uppercase tracking-[0.12em] text-muted font-bold">
          Custom rationale (optional)
        </div>
        <textarea
          rows={3}
          value={awardRationale}
          onChange={(e) => setAwardRationale(e.target.value)}
          placeholder="Why this vendor? Any commercial or technical notes worth recording..."
        />
        {awardErr ? <div className="text-[#ff9d9d] text-sm">{awardErr}</div> : null}
      </div>
    </div>
  );
}

export function AwardModal({
  rfqNo,
  code,
  onClose,
  onAwarded,
}: {
  rfqNo: string;
  code: string;
  onClose: () => void;
  onAwarded: (reply: GatedAwardReply) => void;
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
              Award RFQ · {code}
            </div>
            <h2 className="m-0 text-xl font-bold mt-1">{rfqNo}</h2>
            <p className="text-sm text-muted mt-1 m-0">
              Awards follow the TBE combined ranking. Complete TBE on the RFQ, or use a commercial-only override.
            </p>
          </div>
          <button type="button" className="btn btn-secondary text-xs" onClick={onClose}>
            Close
          </button>
        </div>
        <AwardForm
          rfqNo={rfqNo}
          tbeHref={`/sourcing/rfqs/${encodeURIComponent(rfqNo)}#tbe-panel`}
          onAwarded={onAwarded}
        />
      </div>
    </div>
  );
}
