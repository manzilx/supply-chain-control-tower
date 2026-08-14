"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { FollowupModal } from "@/components/followup-modal";
import { AnimatedKpiTile, HBar, MotionPanel, CHART_PALETTE } from "@/components/charts";
import { PageHeader } from "@/components/page-header";
import {
  fetchExpediteQueue,
  fetchLogisticsQueue,
  fetchProjects,
  fetchPrs,
  fetchSimulationBrief,
  fetchVendorIntel,
  fetchVendorScorecard,
  parseSimulationAsk,
  runSimulation,
} from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatDate } from "@/lib/format-date";
import {
  actionPoNumber,
  actionProjectHref,
  actionVendorHref,
  buildSuggestedSims,
  hasSimulationImpact,
  orderVendorsByExposure,
} from "@/lib/simulate-suggestions";
import { useAsync } from "@/lib/use-async";
import type {
  Project,
  PurchaseRequisition,
  SimulationBrief,
  SimulationRequest,
  SimulationResult,
  SimulationScenario,
  VendorSummary,
} from "@/lib/types";

const SCENARIO_LABEL: Record<SimulationScenario, string> = {
  vendor_slip_2w: "Vendor slips by 2 weeks",
  customs_hold: "Customs holds shipment",
  need_by_move: "Need-by / milestone moves",
  alt_vendor: "Switch to alternate vendor",
};

const SCENARIO_HINT: Record<SimulationScenario, string> = {
  vendor_slip_2w: "Apply a 14-day slip (configurable) to every open order from a vendor. Rolls up schedule + cost impact.",
  customs_hold: "Hold a specific shipment in customs for 21 days. Estimates demurrage + project slip.",
  need_by_move: "Move a milestone, PR, or BOM need-by by ±N days and see what rides with it.",
  alt_vendor: "Swap one vendor for another in the same category. Shows score / lead / price delta.",
};

const SEV_TONE: Record<string, string> = {
  low: "severity-low",
  medium: "severity-medium",
  high: "severity-high",
  critical: "severity-critical",
};

export default function SimulatePage() {
  const { hasPerm } = useAuth();
  const canFollowup = hasPerm("followup", "create");
  const vendors = useAsync<VendorSummary[]>(fetchVendorIntel, []);
  const logistics = useAsync(fetchLogisticsQueue, []);
  const expedite = useAsync(fetchExpediteQueue, []);
  const projects = useAsync<Project[]>(fetchProjects, []);
  const prs = useAsync<PurchaseRequisition[]>(fetchPrs, []);

  const [scenario, setScenario] = useState<SimulationScenario>("vendor_slip_2w");
  const [target, setTarget] = useState<string>("");
  const [alternate, setAlternate] = useState<string>("");
  const [slipDays, setSlipDays] = useState<number>(14);
  const [alternates, setAlternates] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [targetTouched, setTargetTouched] = useState(false);
  const [followupPo, setFollowupPo] = useState<string | null>(null);
  const [brief, setBrief] = useState<SimulationBrief | null>(null);
  const [briefLoading, setBriefLoading] = useState(false);
  const [ask, setAsk] = useState("");
  const [asking, setAsking] = useState(false);
  const autoRan = useRef(false);

  const exposedVendors = useMemo(() => {
    const seen = new Set<string>();
    const ordered: string[] = [];
    for (const item of expedite.data?.items ?? []) {
      if (item.supplier_name && !seen.has(item.supplier_name)) {
        seen.add(item.supplier_name);
        ordered.push(item.supplier_name);
      }
    }
    for (const shipment of logistics.data?.shipments ?? []) {
      if (shipment.current_stage === "delivered") continue;
      if (shipment.vendor && !seen.has(shipment.vendor)) {
        seen.add(shipment.vendor);
        ordered.push(shipment.vendor);
      }
    }
    return ordered;
  }, [expedite.data, logistics.data]);

  const vendorNames = useMemo(
    () => orderVendorsByExposure(
      (vendors.data ?? []).map((v) => v.vendor),
      exposedVendors,
    ),
    [vendors.data, exposedVendors],
  );
  const exposedSet = useMemo(() => new Set(exposedVendors), [exposedVendors]);
  const defaultVendor = vendorNames[0] ?? "";
  const poRefs = useMemo(
    () => (logistics.data?.shipments ?? [])
      .filter((s) => s.current_stage !== "delivered")
      .map((s) => ({
        po_ref: s.po_ref,
        label: `${s.po_ref} · ${s.vendor} · ${s.code ?? ""}`,
      })),
    [logistics.data],
  );
  const defaultPo = poRefs[0]?.po_ref ?? "";

  const needByOptions = useMemo(() => {
    const today = new Date().toISOString().slice(0, 10);
    const options: { value: string; label: string }[] = [];
    for (const project of projects.data ?? []) {
      for (const milestone of project.milestones) {
        if (milestone.required_on_site_date < today) continue;
        options.push({
          value: `${project.project_id}:${milestone.code}`,
          label: `${milestone.code} · ${project.name} · ${milestone.required_on_site_date}`,
        });
      }
    }
    options.sort((a, b) => a.label.localeCompare(b.label));
    for (const pr of prs.data ?? []) {
      if (!pr.need_by) continue;
      options.push({
        value: pr.pr_no,
        label: `${pr.pr_no} · ${pr.code} · need-by ${pr.need_by}`,
      });
    }
    return options;
  }, [projects.data, prs.data]);
  const defaultNeedBy = needByOptions[0]?.value ?? "";

  const suggestions = useMemo(
    () => buildSuggestedSims({
      expediteItems: expedite.data?.items ?? [],
      shipments: logistics.data?.shipments ?? [],
      projects: projects.data ?? [],
    }),
    [expedite.data, logistics.data, projects.data],
  );
  const suggestionsReady = !expedite.loading && !logistics.loading && !projects.loading;

  useEffect(() => {
    if (scenario === "customs_hold") {
      if (!target || !poRefs.some((p) => p.po_ref === target)) {
        if (defaultPo) setTarget(defaultPo);
      }
      return;
    }
    if (scenario === "need_by_move") {
      if (!targetTouched && defaultNeedBy && target !== defaultNeedBy) {
        setTarget(defaultNeedBy);
      }
      return;
    }
    if (!targetTouched) {
      if (defaultVendor && target !== defaultVendor) setTarget(defaultVendor);
      return;
    }
    if (target && !vendorNames.includes(target) && defaultVendor) {
      setTarget(defaultVendor);
    }
  }, [scenario, target, targetTouched, defaultVendor, defaultPo, defaultNeedBy, vendorNames, poRefs]);

  useEffect(() => {
    setAlternate("");
    setAlternates([]);
    if (scenario !== "alt_vendor" || !target) return;
    void fetchVendorScorecard(target).then((sc) => {
      setAlternates(sc.alternates.map((a) => a.name));
      if (sc.alternates.length) setAlternate(sc.alternates[0].name);
    });
  }, [scenario, target]);

  async function runSim(override?: {
    scenario?: SimulationScenario;
    target?: string;
    alternate?: string;
    slipDays?: number;
  }) {
    const sc = override?.scenario ?? scenario;
    const tgt = (override?.target ?? target).trim();
    const alt = override?.alternate ?? alternate;
    const days = override?.slipDays ?? slipDays;
    if (!tgt) {
      setError("Pick a target.");
      return;
    }
    if (sc === "alt_vendor" && !alt) {
      setError("Pick an alternate vendor.");
      return;
    }
    setRunning(true);
    setError(null);
    setBrief(null);
    try {
      const req: SimulationRequest = {
        scenario: sc,
        target: tgt,
        alternate_vendor: sc === "alt_vendor" ? alt : null,
        custom_slip_days: sc === "vendor_slip_2w" || sc === "need_by_move" ? days : null,
      };
      setResult(await runSimulation(req));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Simulation failed");
    } finally {
      setRunning(false);
    }
  }

  async function submitAsk() {
    const text = ask.trim();
    if (!text) return;
    setAsking(true);
    setError(null);
    try {
      const parsed = await parseSimulationAsk(text);
      if (!parsed.ok || !parsed.scenario || !parsed.target) {
        setError(parsed.reason || "Could not parse — use the cards.");
        return;
      }
      setScenario(parsed.scenario);
      setTarget(parsed.target);
      setTargetTouched(true);
      if (parsed.custom_slip_days != null) setSlipDays(parsed.custom_slip_days);
      if (parsed.alternate_vendor) setAlternate(parsed.alternate_vendor);
      await runSim({
        scenario: parsed.scenario,
        target: parsed.target,
        alternate: parsed.alternate_vendor ?? undefined,
        slipDays: parsed.custom_slip_days ?? undefined,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not parse question");
    } finally {
      setAsking(false);
    }
  }

  useEffect(() => {
    if (autoRan.current || !suggestionsReady || !suggestions[0]) return;
    autoRan.current = true;
    const card = suggestions[0];
    setScenario(card.scenario);
    setTarget(card.target);
    setTargetTouched(true);
    void runSim({ scenario: card.scenario, target: card.target });
    // runSim is stable enough for a one-shot first visit
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [suggestionsReady, suggestions]);

  const suggestedVendor = useMemo(() => {
    if (!result || hasSimulationImpact(result)) return null;
    return exposedVendors.find((name) => name !== result.target) ?? null;
  }, [result, exposedVendors]);

  const followupItem = useMemo(() => {
    if (!followupPo) return null;
    return (expedite.data?.items ?? []).find((item) => item.po_number === followupPo) ?? null;
  }, [followupPo, expedite.data]);

  useEffect(() => {
    if (!result || !hasSimulationImpact(result)) {
      setBrief(null);
      setBriefLoading(false);
      return;
    }
    let cancelled = false;
    setBriefLoading(true);
    fetchSimulationBrief(result)
      .then((next) => {
        if (!cancelled) setBrief(next);
      })
      .catch(() => {
        if (!cancelled) setBrief(null);
      })
      .finally(() => {
        if (!cancelled) setBriefLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [result]);

  const followupNotes = useMemo(() => {
    if (!result) return "";
    const bits = [
      `Simulation: ${SCENARIO_LABEL[result.scenario]} · ${result.target}.`,
      result.headline,
      `Cost ${result.cost_delta_usd >= 0 ? "+" : ""}$${Math.round(result.cost_delta_usd).toLocaleString()}, schedule ${result.schedule_delta_days >= 0 ? "+" : ""}${result.schedule_delta_days}d.`,
    ];
    if (brief?.why) bits.push(brief.why);
    return bits.join(" ");
  }, [result, brief]);

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Simulate"
        title="What-if Simulator"
        description="The most material live what-if for this tenant, already run. Ask in English or click a card."
      />

      <form
        className="panel flex flex-col md:flex-row gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void submitAsk();
        }}
      >
        <input
          value={ask}
          onChange={(e) => setAsk(e.target.value)}
          placeholder="Ask a what-if — e.g. Helios slips 21 days"
          className="flex-1"
        />
        <button type="submit" className="btn btn-primary" disabled={asking || !ask.trim()}>
          {asking ? "Reading…" : "Ask"}
        </button>
      </form>

      {suggestions.length ? (
        <section className="grid grid-cols-1 md:grid-cols-3 gap-2">
          {suggestions.map((card) => {
            const active = scenario === card.scenario && target === card.target;
            return (
              <button
                key={`${card.scenario}:${card.target}`}
                type="button"
                onClick={() => {
                  setScenario(card.scenario);
                  setTarget(card.target);
                  setTargetTouched(true);
                  setError(null);
                  void runSim({ scenario: card.scenario, target: card.target });
                }}
                className={[
                  "panel-sm text-left cursor-pointer transition-colors",
                  active ? "border-accent/60 bg-accent/5" : "hover:border-accent/30",
                ].join(" ")}
              >
                <div className="text-[0.62rem] uppercase tracking-[0.12em] text-muted font-bold">
                  {SCENARIO_LABEL[card.scenario]}
                </div>
                <div className="font-semibold text-ink mt-1">{card.title}</div>
                <div className="text-xs text-muted mt-1 leading-relaxed">{card.hint}</div>
              </button>
            );
          })}
        </section>
      ) : null}

      <section className="panel space-y-4">
        <div>
          <div className="text-[0.68rem] uppercase tracking-[0.14em] text-muted font-bold mb-2">Scenario</div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
            {(Object.keys(SCENARIO_LABEL) as SimulationScenario[]).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => {
                  setScenario(s);
                  setTargetTouched(false);
                  setResult(null);
                  setError(null);
                }}
                className={[
                  "panel-sm text-left cursor-pointer transition-colors",
                  scenario === s
                    ? "border-accent/60 bg-accent/5"
                    : "hover:border-accent/30",
                ].join(" ")}
              >
                <div className="font-semibold text-ink">{SCENARIO_LABEL[s]}</div>
                <div className="text-xs text-muted mt-1 leading-relaxed">{SCENARIO_HINT[s]}</div>
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <label className="flex flex-col gap-1">
            <span className="text-[0.65rem] uppercase tracking-[0.12em] text-muted font-bold">
              {scenario === "customs_hold" ? "Shipment" : scenario === "need_by_move" ? "Need-by" : "Vendor"}
            </span>
            {scenario === "customs_hold" ? (
              <select
                value={target}
                onChange={(e) => {
                  setTargetTouched(true);
                  setTarget(e.target.value);
                }}
              >
                <option value="">— pick —</option>
                {poRefs.map((p) => (
                  <option key={p.po_ref} value={p.po_ref}>{p.label}</option>
                ))}
              </select>
            ) : scenario === "need_by_move" ? (
              <select
                value={target}
                onChange={(e) => {
                  setTargetTouched(true);
                  setTarget(e.target.value);
                }}
              >
                <option value="">— pick —</option>
                {needByOptions.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            ) : (
              <select
                value={target}
                onChange={(e) => {
                  setTargetTouched(true);
                  setTarget(e.target.value);
                }}
              >
                <option value="">— pick —</option>
                {vendorNames.map((v) => (
                  <option key={v} value={v}>
                    {v}{exposedSet.has(v) ? " · open orders" : ""}
                  </option>
                ))}
              </select>
            )}
            {scenario !== "customs_hold" && scenario !== "need_by_move" && target && !exposedSet.has(target) ? (
              <span className="text-xs text-muted">
                No open orders on file for {target} — the run will show zero impact.
              </span>
            ) : null}
          </label>

          {scenario === "alt_vendor" ? (
            <label className="flex flex-col gap-1">
              <span className="text-[0.65rem] uppercase tracking-[0.12em] text-muted font-bold">Alternate</span>
              <select value={alternate} onChange={(e) => setAlternate(e.target.value)}>
                <option value="">— pick —</option>
                {alternates.map((a) => (
                  <option key={a} value={a}>{a}</option>
                ))}
              </select>
              {alternates.length === 0 ? (
                <span className="text-xs text-muted">No approved alternates on file for {target}.</span>
              ) : null}
            </label>
          ) : null}

          {scenario === "vendor_slip_2w" || scenario === "need_by_move" ? (
            <label className="flex flex-col gap-1">
              <span className="text-[0.65rem] uppercase tracking-[0.12em] text-muted font-bold">
                {scenario === "need_by_move" ? "Move days" : "Slip days"}
              </span>
              <input
                type="number"
                min={scenario === "need_by_move" ? -90 : 1}
                value={slipDays}
                onChange={(e) => setSlipDays(Number(e.target.value) || 14)}
              />
            </label>
          ) : null}
        </div>

        {error ? <div className="text-[#ff9d9d] text-sm">{error}</div> : null}

        <div>
          <button className="btn btn-primary" onClick={() => void runSim()} disabled={running || !target}>
            {running ? "Running..." : "Run Simulation"}
          </button>
        </div>
      </section>

      {result && !hasSimulationImpact(result) ? (
        <section className="panel space-y-3">
          <EmptyState
            title={result.headline}
            hint="Nothing in the current book moves under this target. Pick a vendor with live open orders."
          />
          {suggestedVendor ? (
            <div className="text-center">
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => {
                  setTargetTouched(true);
                  setScenario("vendor_slip_2w");
                  setTarget(suggestedVendor);
                  void runSim({ scenario: "vendor_slip_2w", target: suggestedVendor });
                }}
              >
                Try {suggestedVendor}
              </button>
            </div>
          ) : null}
        </section>
      ) : null}

      {result && hasSimulationImpact(result) ? (
        <section className="space-y-4">
          <div className="panel">
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div>
                <div className="text-[0.68rem] uppercase tracking-[0.14em] text-muted font-bold">
                  Result · {SCENARIO_LABEL[result.scenario]} · {result.target}
                </div>
                <h2 className="m-0 text-xl font-bold mt-1">{result.headline}</h2>
              </div>
              <span className={`badge ${SEV_TONE[result.severity]}`}>{result.severity}</span>
            </div>
            <ResultActions
              result={result}
              brief={brief}
              canFollowup={canFollowup}
              expediteItems={expedite.data?.items ?? []}
              onFollowup={setFollowupPo}
            />
          </div>

          {briefLoading && !brief ? (
            <section className="rounded-2xl border border-accent/20 bg-accent/[0.03] p-5 text-sm text-muted">
              Writing decision brief…
            </section>
          ) : null}

          {brief ? (
            <section className="rounded-2xl border border-accent/30 bg-accent/[0.05] p-5">
              <div className="flex items-baseline justify-between gap-3 mb-2">
                <div className="text-[0.65rem] uppercase tracking-[0.14em] text-accent font-bold">
                  Decision brief
                </div>
                <span className="text-[0.6rem] uppercase tracking-[0.14em] text-muted">
                  {brief.source === "deepseek" ? "via deepseek" : "deterministic"}
                </span>
              </div>
              <div className="text-sm text-ink/90 leading-relaxed">{brief.why}</div>
              {brief.watch.length ? (
                <ul className="mt-3 mb-0 pl-5 text-sm text-muted space-y-1">
                  {brief.watch.map((w) => (
                    <li key={w}>{w}</li>
                  ))}
                </ul>
              ) : null}
            </section>
          ) : null}

          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <AnimatedKpiTile
              label="Cost Delta"
              value={result.cost_delta_usd}
              prefix={result.cost_delta_usd >= 0 ? "+$" : "-$"}
              format={(v) => Math.abs(Math.round(v)).toLocaleString()}
              tone={result.cost_delta_usd > 0 ? "bad" : result.cost_delta_usd < 0 ? "good" : "neutral"}
              delay={0.0}
            />
            <AnimatedKpiTile
              label="Schedule Delta"
              value={result.schedule_delta_days}
              prefix={result.schedule_delta_days >= 0 ? "+" : ""}
              suffix=" days"
              tone={result.schedule_delta_days > 0 ? "bad" : "neutral"}
              delay={0.05}
            />
            <AnimatedKpiTile
              label="Affected Items"
              value={result.affected_items.length}
              delay={0.10}
            />
          </div>

          {result.milestone_impacts.length > 0 ? (
            <MotionPanel delay={0.15}>
              <HBar
                title="Milestone slip (days)"
                color={CHART_PALETTE.rose}
                data={result.milestone_impacts.map((m) => ({
                  name: `${m.milestone_code} · ${m.milestone_name}`.slice(0, 40),
                  value: m.slip_days,
                }))}
                valueFormat={(v) => `${v}d`}
                height={Math.max(150, result.milestone_impacts.length * 40)}
              />
            </MotionPanel>
          ) : null}

          {result.affected_items.length > 0 ? (
            <section className="panel">
              <h2 className="m-0 text-lg font-bold mb-3">Affected Items</h2>
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Ref</th>
                      <th>Code</th>
                      <th>Description</th>
                      <th>Original Need</th>
                      <th>New Expected</th>
                      <th>Impact</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.affected_items.map((a) => (
                      <tr key={a.ref_id}>
                        <td className="font-mono text-xs">
                          {/^(PO|SPO)-/i.test(a.ref_id) ? (
                            <Link href="/pos" className="text-accent hover:underline">{a.ref_id}</Link>
                          ) : a.ref_id.includes(":") ? (
                            <Link
                              href={`/projects/${encodeURIComponent(a.ref_id.split(":")[0])}`}
                              className="text-accent hover:underline"
                            >
                              {a.ref_id}
                            </Link>
                          ) : (
                            a.ref_id
                          )}
                        </td>
                        <td className="font-mono text-xs">{a.code}</td>
                        <td className="text-ink">{a.description}</td>
                        <td className="text-muted">{formatDate(a.original_need_date)}</td>
                        <td className="text-warning font-semibold">{formatDate(a.new_expected_date)}</td>
                        <td className="text-sm text-muted">{a.impact}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : null}

          {result.milestone_impacts.length > 0 ? (
            <section className="panel">
              <h2 className="m-0 text-lg font-bold mb-3">Milestone Impacts</h2>
              <div className="space-y-2">
                {result.milestone_impacts.map((m) => (
                  <article key={`${m.project_id}-${m.milestone_code}`} className="panel-sm">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="font-semibold text-ink">
                          {m.project_name} · {m.milestone_code}
                        </div>
                        <div className="text-sm text-muted">{m.milestone_name}</div>
                        <div className="text-xs text-muted mt-1">
                          {formatDate(m.original_date)} → <span className="text-warning">{formatDate(m.new_date)}</span>
                        </div>
                      </div>
                      <span className="badge severity-high">+{m.slip_days}d</span>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          ) : null}

          {result.mitigations.length > 0 ? (
            <section className="panel">
              <div className="section-title mb-2">Mitigations</div>
              <ul className="space-y-2 text-sm text-ink m-0 pl-5 list-disc">
                {result.mitigations.map((m, i) => <li key={i}>{m}</li>)}
              </ul>
            </section>
          ) : null}

          {result.assumptions.length > 0 ? (
            <section className="panel">
              <div className="section-title mb-2">Assumptions</div>
              <ul className="space-y-2 text-sm text-muted m-0 pl-5 list-disc">
                {result.assumptions.map((a, i) => <li key={i}>{a}</li>)}
              </ul>
            </section>
          ) : null}
        </section>
      ) : null}

      {followupItem ? (
        <FollowupModal
          item={followupItem}
          initialNotes={followupNotes}
          onClose={() => setFollowupPo(null)}
        />
      ) : null}
    </div>
  );
}

function ResultActions({
  result,
  brief,
  canFollowup,
  expediteItems,
  onFollowup,
}: {
  result: SimulationResult;
  brief: SimulationBrief | null;
  canFollowup: boolean;
  expediteItems: { po_number: string }[];
  onFollowup: (po: string) => void;
}) {
  const preferred = brief?.action_ref && /^(PO|SPO)-/i.test(brief.action_ref)
    ? brief.action_ref
    : null;
  const po = preferred ?? actionPoNumber(result);
  const inQueue = po ? expediteItems.some((item) => item.po_number === po) : false;
  const vendorHref = actionVendorHref(result);
  const projectHref = actionProjectHref(result);
  const primary = brief?.primary_action;

  function cls(kind: string) {
    return primary === kind ? "btn btn-primary" : "btn btn-secondary";
  }

  return (
    <div className="flex flex-wrap gap-2 mt-4">
      {canFollowup && po && inQueue ? (
        <button type="button" className={cls("followup")} onClick={() => onFollowup(po)}>
          Draft follow-up · {po}
        </button>
      ) : null}
      {po ? (
        <Link href="/expediting" className={cls("expedite")}>
          Open expedite queue
        </Link>
      ) : null}
      {po ? (
        <Link href="/pos" className={cls("open_po")}>
          Open {po}
        </Link>
      ) : null}
      {vendorHref ? (
        <Link href={vendorHref} className={cls("open_vendor")}>
          Open vendor
        </Link>
      ) : null}
      {projectHref ? (
        <Link href={projectHref} className={cls("open_project")}>
          Open project
        </Link>
      ) : null}
    </div>
  );
}
