"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  ResponsiveContainer,
} from "recharts";

import { CHART_PALETTE, MotionPanel } from "@/components/charts";
import {
  autoEvaluate,
  fetchTbe,
  setTbeWeights,
  setTechnicalEvaluation,
} from "@/lib/api";
import type {
  ComplianceLevel,
  CriterionScore,
  Quote,
  TBE,
  TechnicalCriterion,
  TechnicalEvaluation,
} from "@/lib/types";

const COMPLIANCE_TONE: Record<ComplianceLevel, string> = {
  full:           "bg-emerald-500/15 text-emerald-300 border-emerald-500/40",
  partial:        "bg-sky-500/15 text-sky-300 border-sky-500/40",
  deviation:      "bg-amber-500/15 text-amber-300 border-amber-500/40",
  non_compliant:  "bg-rose-500/15 text-rose-300 border-rose-500/40",
  not_assessed:   "bg-zinc-500/15 text-zinc-400 border-zinc-500/40",
};

const COMPLIANCE_LABEL: Record<ComplianceLevel, string> = {
  full:          "Full",
  partial:       "Partial",
  deviation:     "Deviation",
  non_compliant: "Non-comp",
  not_assessed:  "—",
};

const GRADE_TONE: Record<string, string> = {
  A: "text-emerald-300",
  B: "text-sky-300",
  C: "text-amber-300",
  D: "text-orange-300",
  F: "text-rose-300",
};

const COLORS = [
  CHART_PALETTE.accent,
  CHART_PALETTE.gold,
  CHART_PALETTE.sky,
  CHART_PALETTE.rose,
  CHART_PALETTE.violet,
];

type Props = {
  rfqNo: string;
  quotes: Quote[];
  onUpdated?: () => void;
};

export function TbePanel({ rfqNo, quotes, onUpdated }: Props) {
  const [tbe, setTbe] = useState<TBE | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetchTbe(rfqNo);
      setTbe(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load TBE");
    } finally {
      setLoading(false);
    }
  }, [rfqNo]);

  useEffect(() => { void load(); }, [load]);

  async function refreshTbe() {
    await load();
    onUpdated?.();
  }

  async function runAutoEval() {
    setBusy("auto");
    setError(null);
    try {
      await autoEvaluate(rfqNo);
      await refreshTbe();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Auto-evaluate failed");
    } finally {
      setBusy(null);
    }
  }

  async function saveEvaluation(quoteId: string, scores: CriterionScore[]) {
    setBusy(quoteId);
    try {
      await setTechnicalEvaluation(rfqNo, quoteId, { criteria_scores: scores });
      await refreshTbe();
    } finally {
      setBusy(null);
    }
  }

  async function setWeights(c: number, t: number) {
    setBusy("weights");
    try {
      await setTbeWeights(rfqNo, c, t);
      await refreshTbe();
    } finally {
      setBusy(null);
    }
  }

  if (loading) {
    return <div className="panel text-muted text-sm">Loading technical evaluation…</div>;
  }
  if (error || !tbe) {
    return <div className="panel-sm border-[rgba(255,117,117,0.3)] text-[#ff9d9d]">{error ?? "No TBE"}</div>;
  }

  return (
    <MotionPanel>
      <section id="tbe-panel" className="space-y-4">
        <div className="flex items-baseline justify-between gap-3 flex-wrap">
          <div>
            <div className="text-[0.65rem] uppercase tracking-[0.14em] text-accent font-bold">
              Technical Bid Evaluation
            </div>
            <h2 className="text-lg font-bold m-0 mt-1">
              {tbe.criteria.length} criteria · {quotes.length} vendors
            </h2>
          </div>
          <div className="flex items-center gap-2">
            <WeightSlider
              commercial={tbe.commercial_weight}
              technical={tbe.technical_weight}
              onChange={(c, t) => void setWeights(c, t)}
              disabled={busy !== null}
            />
            <motion.button
              type="button"
              onClick={() => void runAutoEval()}
              disabled={busy !== null}
              whileTap={{ scale: 0.96 }}
              whileHover={busy === null ? { scale: 1.03 } : undefined}
              animate={busy === "auto" ? { boxShadow: ["0 0 0 0 rgba(87,212,192,0)", "0 0 0 8px rgba(87,212,192,0.15)", "0 0 0 0 rgba(87,212,192,0)"] } : { boxShadow: "0 0 0 0 rgba(87,212,192,0)" }}
              transition={{ duration: busy === "auto" ? 1.2 : 0.2, repeat: busy === "auto" ? Infinity : 0, ease: "easeInOut" }}
              className="btn btn-primary text-xs disabled:opacity-50"
            >
              {busy === "auto" ? "AI scoring…" : "AI evaluate all"}
            </motion.button>
          </div>
        </div>

        {/* Combined ranking */}
        <CombinedRankingTable tbe={tbe} />

        {/* Radar comparison */}
        {tbe.technical_evaluations.length > 0 ? (
          <TbeRadar tbe={tbe} quotes={quotes} />
        ) : null}

        {/* Per-vendor criteria grid */}
        <CriteriaScoreMatrix
          tbe={tbe}
          quotes={quotes}
          busy={busy}
          onSave={(qid, scores) => void saveEvaluation(qid, scores)}
        />

        {/* Deviation list */}
        <DeviationList tbe={tbe} />
      </section>
    </MotionPanel>
  );
}

// --------------------------------------------------------- weight slider ----

function WeightSlider({
  commercial,
  technical,
  onChange,
  disabled,
}: {
  commercial: number;
  technical: number;
  onChange: (c: number, t: number) => void;
  disabled?: boolean;
}) {
  const [v, setV] = useState(Math.round(commercial * 100));
  useEffect(() => { setV(Math.round(commercial * 100)); }, [commercial]);
  return (
    <div className="panel-sm flex flex-col gap-1 min-w-[220px]">
      <div className="flex justify-between text-[0.6rem] uppercase tracking-[0.12em] text-muted font-bold">
        <span>Commercial {v}%</span>
        <span>Technical {100 - v}%</span>
      </div>
      <input
        type="range"
        min={0}
        max={100}
        value={v}
        disabled={disabled}
        onChange={(e) => setV(Number(e.target.value))}
        onMouseUp={(e) => onChange(Number((e.target as HTMLInputElement).value) / 100, 1 - Number((e.target as HTMLInputElement).value) / 100)}
        onTouchEnd={(e) => onChange(Number((e.target as HTMLInputElement).value) / 100, 1 - Number((e.target as HTMLInputElement).value) / 100)}
        className="w-full accent-accent"
      />
    </div>
  );
}

// ---------------------------------------------------- combined ranking ----

function CombinedRankingTable({ tbe }: { tbe: TBE }) {
  if (tbe.combined.length === 0) {
    return <div className="panel-sm text-muted text-sm">No quotes to rank yet.</div>;
  }
  return (
    <div className="panel overflow-x-auto p-0">
      <div className="flex items-baseline justify-between p-4 pb-2">
        <div className="text-[0.65rem] uppercase tracking-[0.12em] text-accent font-bold">
          Combined ranking
        </div>
        {tbe.recommended_vendor ? (
          <div className="text-xs text-muted">
            Recommended: <span className="text-ink font-semibold">{tbe.recommended_vendor}</span>
          </div>
        ) : null}
      </div>
      <table className="data-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Vendor</th>
            <th>Commercial</th>
            <th>Technical</th>
            <th>Combined</th>
            <th>Deviations</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {tbe.combined.map((c) => (
            <motion.tr
              key={c.quote_id}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: (c.combined_rank - 1) * 0.05 }}
              className={c.combined_rank === 1 && !c.disqualified ? "bg-accent/[0.06]" : ""}
            >
              <td>
                <span className={c.combined_rank === 1 && !c.disqualified ? "text-accent font-bold text-base" : "text-muted"}>
                  #{c.combined_rank}
                </span>
              </td>
              <td>
                <div className="font-semibold text-ink">{c.vendor}</div>
                <div className="text-xs text-muted font-mono">{c.quote_id}</div>
              </td>
              <td>
                <ScoreBar value={c.commercial_score} color={CHART_PALETTE.sky} />
                <div className="text-xs text-muted mt-0.5">rank #{c.commercial_rank}</div>
              </td>
              <td>
                <ScoreBar value={c.technical_score} color={CHART_PALETTE.accent} />
                <div className="text-xs text-muted mt-0.5">rank #{c.technical_rank}</div>
              </td>
              <td>
                <div className={`text-lg font-bold ${c.disqualified ? "text-rose-300" : "text-ink"}`}>
                  {c.disqualified ? "—" : c.combined_score.toFixed(1)}
                </div>
              </td>
              <td>
                <span className={c.deviations_count > 0 ? "text-amber-300 font-bold" : "text-muted"}>
                  {c.deviations_count}
                </span>
              </td>
              <td>
                {c.disqualified ? (
                  <span className="inline-block rounded border border-rose-500/40 bg-rose-500/15 text-rose-300 px-2 py-0.5 text-[0.6rem] font-bold uppercase">
                    Disqualified
                  </span>
                ) : c.combined_rank === 1 ? (
                  <span className="inline-block rounded border border-emerald-500/40 bg-emerald-500/15 text-emerald-300 px-2 py-0.5 text-[0.6rem] font-bold uppercase">
                    Lead
                  </span>
                ) : null}
                {c.notes.length > 0 ? (
                  <div className="text-[0.65rem] text-muted mt-0.5">{c.notes.join("; ")}</div>
                ) : null}
              </td>
            </motion.tr>
          ))}
        </tbody>
      </table>
      {tbe.recommendation_rationale ? (
        <div className="p-3 text-xs text-muted italic border-t border-line bg-white/[0.02]">
          {tbe.recommendation_rationale}
        </div>
      ) : null}
    </div>
  );
}

function ScoreBar({ value, color }: { value: number; color: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="font-bold text-ink min-w-[2.5rem]">{Math.round(value)}</span>
      <div className="flex-1 h-1.5 rounded-full bg-white/[0.06] overflow-hidden min-w-[80px] max-w-[120px]">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${Math.min(100, value)}%` }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
          className="h-full"
          style={{ backgroundColor: color }}
        />
      </div>
    </div>
  );
}

// ----------------------------------------------- per-vendor radar compare ---

function TbeRadar({ tbe, quotes }: { tbe: TBE; quotes: Quote[] }) {
  // Build chart data — one row per criterion, one series per vendor.
  const data = tbe.criteria.map((c) => {
    const row: Record<string, string | number> = { criterion: c.name.split(" ").slice(0, 3).join(" ") };
    quotes.forEach((q) => {
      const ev = tbe.technical_evaluations.find((e) => e.quote_id === q.quote_id);
      const score = ev?.criteria_scores.find((s) => s.criterion_id === c.criterion_id)?.score ?? 0;
      row[q.vendor] = score;
    });
    return row;
  });
  return (
    <div className="panel">
      <div className="text-[0.65rem] uppercase tracking-[0.12em] text-accent font-bold mb-2">
        Technical comparison
      </div>
      <div style={{ height: 320 }}>
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart data={data} outerRadius="78%">
            <PolarGrid stroke={CHART_PALETTE.grid} />
            <PolarAngleAxis dataKey="criterion" tick={{ fill: CHART_PALETTE.text, fontSize: 10 }} />
            {quotes.map((q, i) => (
              <Radar
                key={q.quote_id}
                name={q.vendor}
                dataKey={q.vendor}
                stroke={COLORS[i % COLORS.length]}
                fill={COLORS[i % COLORS.length]}
                fillOpacity={0.18}
                isAnimationActive
                animationDuration={800}
              />
            ))}
          </RadarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// ---------------------------- per-criterion score matrix (editable) ----

function CriteriaScoreMatrix({
  tbe,
  quotes,
  busy,
  onSave,
}: {
  tbe: TBE;
  quotes: Quote[];
  busy: string | null;
  onSave: (quoteId: string, scores: CriterionScore[]) => void;
}) {
  // Local working state per vendor, seeded from tbe
  const [drafts, setDrafts] = useState<Record<string, CriterionScore[]>>({});

  useEffect(() => {
    const seed: Record<string, CriterionScore[]> = {};
    quotes.forEach((q) => {
      const ev = tbe.technical_evaluations.find((e) => e.quote_id === q.quote_id);
      seed[q.quote_id] = ev
        ? ev.criteria_scores.map((s) => ({ ...s }))
        : tbe.criteria.map((c) => ({
            criterion_id: c.criterion_id,
            score: 0,
            compliance: "not_assessed",
            note: "",
          }));
    });
    setDrafts(seed);
  }, [tbe, quotes]);

  function update(quoteId: string, criterionId: string, patch: Partial<CriterionScore>) {
    setDrafts((d) => ({
      ...d,
      [quoteId]: (d[quoteId] || []).map((s) => (s.criterion_id === criterionId ? { ...s, ...patch } : s)),
    }));
  }

  return (
    <div className="panel overflow-x-auto p-0">
      <div className="p-4 pb-2">
        <div className="text-[0.65rem] uppercase tracking-[0.12em] text-accent font-bold">
          Criteria × vendors
        </div>
      </div>
      <table className="data-table">
        <thead>
          <tr>
            <th className="min-w-[260px]">Criterion</th>
            <th className="min-w-[60px]">Wt</th>
            {quotes.map((q) => (
              <th key={q.quote_id} className="min-w-[200px]">{q.vendor}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {tbe.criteria.map((c) => (
            <tr key={c.criterion_id}>
              <td>
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-ink">{c.name}</span>
                  {c.mandatory ? (
                    <span className="rounded border border-rose-500/40 bg-rose-500/10 text-rose-300 text-[0.55rem] uppercase tracking-wider px-1 py-0.5 font-bold">
                      Mand
                    </span>
                  ) : null}
                </div>
                <div className="text-xs text-muted mt-0.5 max-w-md">{c.description}</div>
                <div className="text-[0.6rem] uppercase tracking-[0.1em] text-muted mt-0.5">{c.category.replace(/_/g, " ")}</div>
              </td>
              <td className="text-muted font-mono">{(c.weight * 100).toFixed(0)}%</td>
              {quotes.map((q) => {
                const s = drafts[q.quote_id]?.find((d) => d.criterion_id === c.criterion_id);
                if (!s) return <td key={q.quote_id}>—</td>;
                return (
                  <td key={q.quote_id}>
                    <div className="flex flex-col gap-1">
                      <div className="flex items-center gap-1.5">
                        <input
                          type="number"
                          min={0}
                          max={100}
                          value={s.score}
                          onChange={(e) => update(q.quote_id, c.criterion_id, { score: Math.max(0, Math.min(100, Number(e.target.value))) })}
                          className="w-14 text-sm rounded border border-line bg-black/30 px-1.5 py-0.5"
                        />
                        <select
                          value={s.compliance}
                          onChange={(e) => update(q.quote_id, c.criterion_id, { compliance: e.target.value as ComplianceLevel })}
                          className={`text-[0.65rem] font-bold rounded border px-1.5 py-0.5 ${COMPLIANCE_TONE[s.compliance]}`}
                        >
                          {(["full","partial","deviation","non_compliant","not_assessed"] as ComplianceLevel[]).map((lvl) => (
                            <option key={lvl} value={lvl}>{COMPLIANCE_LABEL[lvl]}</option>
                          ))}
                        </select>
                      </div>
                      <input
                        type="text"
                        placeholder="Note (optional)"
                        value={s.note}
                        onChange={(e) => update(q.quote_id, c.criterion_id, { note: e.target.value })}
                        className="text-[0.7rem] text-muted rounded border border-line bg-black/20 px-1.5 py-0.5 w-full"
                      />
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
          <tr className="bg-white/[0.03] font-bold">
            <td>Technical score</td>
            <td>—</td>
            {quotes.map((q) => {
              const ev = tbe.technical_evaluations.find((e) => e.quote_id === q.quote_id);
              const grade = ev?.technical_grade ?? "F";
              return (
                <td key={q.quote_id}>
                  <div className="flex items-center gap-2">
                    <span className="text-lg">{ev?.technical_score ?? "—"}</span>
                    <span className={`font-mono text-sm ${GRADE_TONE[grade]}`}>{grade}</span>
                    {ev?.source ? (
                      <span className="text-[0.6rem] uppercase tracking-wider text-muted">via {ev.source}</span>
                    ) : null}
                    <button
                      type="button"
                      onClick={() => onSave(q.quote_id, drafts[q.quote_id] || [])}
                      disabled={busy !== null}
                      className="btn btn-secondary text-[0.65rem] ml-auto disabled:opacity-50"
                    >
                      {busy === q.quote_id ? "Saving…" : "Save"}
                    </button>
                  </div>
                </td>
              );
            })}
          </tr>
        </tbody>
      </table>
    </div>
  );
}

// ----------------------------------------- aggregated deviation list ----

function DeviationList({ tbe }: { tbe: TBE }) {
  type Dev = { vendor: string; criterion: string; compliance: ComplianceLevel; note: string };
  const devs: Dev[] = [];
  tbe.technical_evaluations.forEach((ev) => {
    ev.criteria_scores.forEach((s) => {
      if (s.compliance === "deviation" || s.compliance === "non_compliant") {
        const cName = tbe.criteria.find((c) => c.criterion_id === s.criterion_id)?.name ?? s.criterion_id;
        devs.push({ vendor: ev.vendor, criterion: cName, compliance: s.compliance, note: s.deviation_text || s.note });
      }
    });
  });
  if (devs.length === 0) return null;
  return (
    <div className="panel">
      <div className="text-[0.65rem] uppercase tracking-[0.12em] text-accent font-bold mb-2">
        Deviations register ({devs.length})
      </div>
      <ul className="space-y-1.5">
        <AnimatePresence>
          {devs.map((d, i) => (
            <motion.li
              key={`${d.vendor}-${d.criterion}-${i}`}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.3, delay: i * 0.04 }}
              className="text-sm flex items-start gap-2"
            >
              <span className={`inline-block shrink-0 rounded border px-1.5 py-0.5 text-[0.6rem] font-bold uppercase tracking-wider ${COMPLIANCE_TONE[d.compliance]}`}>
                {COMPLIANCE_LABEL[d.compliance]}
              </span>
              <span className="text-ink font-semibold">{d.vendor}</span>
              <span className="text-muted">·</span>
              <span className="text-ink">{d.criterion}</span>
              {d.note ? <span className="text-muted">— {d.note}</span> : null}
            </motion.li>
          ))}
        </AnimatePresence>
      </ul>
    </div>
  );
}
