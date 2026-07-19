"use client";

import { useEffect, useMemo, useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { AnimatedKpiTile, HBar, MotionPanel, CHART_PALETTE } from "@/components/charts";
import { KpiTile } from "@/components/kpi-tile";
import { PageHeader } from "@/components/page-header";
import {
  fetchLogisticsQueue,
  fetchVendorIntel,
  fetchVendorScorecard,
  runSimulation,
} from "@/lib/api";
import { formatDate, formatMoney } from "@/lib/format-date";
import { useAsync } from "@/lib/use-async";
import type {
  SimulationRequest,
  SimulationResult,
  SimulationScenario,
  VendorSummary,
} from "@/lib/types";

const SCENARIO_LABEL: Record<SimulationScenario, string> = {
  vendor_slip_2w: "Vendor slips by 2 weeks",
  customs_hold: "Customs holds shipment",
  alt_vendor: "Switch to alternate vendor",
};

const SCENARIO_HINT: Record<SimulationScenario, string> = {
  vendor_slip_2w: "Apply a 14-day slip (configurable) to every open order from a vendor. Rolls up schedule + cost impact.",
  customs_hold: "Hold a specific shipment in customs for 21 days. Estimates demurrage + project slip.",
  alt_vendor: "Swap one vendor for another in the same category. Shows score / lead / price delta.",
};

const SEV_TONE: Record<string, string> = {
  low: "severity-low",
  medium: "severity-medium",
  high: "severity-high",
  critical: "severity-critical",
};

export default function SimulatePage() {
  const vendors = useAsync<VendorSummary[]>(fetchVendorIntel, []);
  const logistics = useAsync(fetchLogisticsQueue, []);

  const [scenario, setScenario] = useState<SimulationScenario>("vendor_slip_2w");
  const [target, setTarget] = useState<string>("");
  const [alternate, setAlternate] = useState<string>("");
  const [slipDays, setSlipDays] = useState<number>(14);
  const [alternates, setAlternates] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const vendorNames = useMemo(
    () => (vendors.data ?? []).map((v) => v.vendor),
    [vendors.data],
  );
  const poRefs = useMemo(
    () => (logistics.data?.shipments ?? []).map((s) => ({
      po_ref: s.po_ref,
      label: `${s.po_ref} · ${s.vendor} · ${s.code ?? ""}`,
    })),
    [logistics.data],
  );

  useEffect(() => {
    if (scenario === "vendor_slip_2w" && !target && vendorNames.length) setTarget(vendorNames[0]);
    if (scenario === "alt_vendor" && !target && vendorNames.length) setTarget(vendorNames[0]);
    if (scenario === "customs_hold" && !target && poRefs.length) setTarget(poRefs[0].po_ref);
  }, [scenario, target, vendorNames, poRefs]);

  useEffect(() => {
    setResult(null);
    setError(null);
    // Reset target when scenario changes unless it's still valid
    if (scenario === "vendor_slip_2w" || scenario === "alt_vendor") {
      if (!vendorNames.includes(target)) setTarget(vendorNames[0] ?? "");
    } else if (scenario === "customs_hold") {
      if (!poRefs.some((p) => p.po_ref === target)) setTarget(poRefs[0]?.po_ref ?? "");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenario]);

  useEffect(() => {
    setAlternate("");
    setAlternates([]);
    if (scenario !== "alt_vendor" || !target) return;
    void fetchVendorScorecard(target).then((sc) => {
      setAlternates(sc.alternates.map((a) => a.name));
      if (sc.alternates.length) setAlternate(sc.alternates[0].name);
    });
  }, [scenario, target]);

  async function runSim() {
    if (!target) {
      setError("Pick a target.");
      return;
    }
    if (scenario === "alt_vendor" && !alternate) {
      setError("Pick an alternate vendor.");
      return;
    }
    setRunning(true);
    setError(null);
    try {
      const req: SimulationRequest = {
        scenario,
        target,
        alternate_vendor: scenario === "alt_vendor" ? alternate : null,
        custom_slip_days: scenario === "vendor_slip_2w" ? slipDays : null,
      };
      setResult(await runSimulation(req));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Simulation failed");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Simulate"
        title="What-if Simulator"
        description="Run a scenario and see the cost + schedule impact. Useful before committing to an expedite, award, or vendor swap."
      />

      <section className="panel space-y-4">
        <div>
          <div className="text-[0.68rem] uppercase tracking-[0.14em] text-muted font-bold mb-2">Scenario</div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
            {(Object.keys(SCENARIO_LABEL) as SimulationScenario[]).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setScenario(s)}
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
              {scenario === "customs_hold" ? "Shipment" : "Vendor"}
            </span>
            {scenario === "customs_hold" ? (
              <select value={target} onChange={(e) => setTarget(e.target.value)}>
                <option value="">— pick —</option>
                {poRefs.map((p) => (
                  <option key={p.po_ref} value={p.po_ref}>{p.label}</option>
                ))}
              </select>
            ) : (
              <select value={target} onChange={(e) => setTarget(e.target.value)}>
                <option value="">— pick —</option>
                {vendorNames.map((v) => (
                  <option key={v} value={v}>{v}</option>
                ))}
              </select>
            )}
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

          {scenario === "vendor_slip_2w" ? (
            <label className="flex flex-col gap-1">
              <span className="text-[0.65rem] uppercase tracking-[0.12em] text-muted font-bold">Slip days</span>
              <input
                type="number"
                min={1}
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

      {result ? (
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
          </div>

          {result.narrative ? (
            <section className="rounded-2xl border border-accent/30 bg-accent/[0.05] p-5">
              <div className="flex items-baseline justify-between gap-3 mb-2">
                <div className="text-[0.65rem] uppercase tracking-[0.14em] text-accent font-bold">
                  AI executive narrative
                </div>
                <span className="text-[0.6rem] uppercase tracking-[0.14em] text-muted">via grok</span>
              </div>
              <div className="text-sm text-ink/90 whitespace-pre-wrap leading-relaxed">
                {result.narrative}
              </div>
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
                        <td className="font-mono text-xs">{a.ref_id}</td>
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
    </div>
  );
}
