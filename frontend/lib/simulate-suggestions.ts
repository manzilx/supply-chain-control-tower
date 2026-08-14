import type {
  ExpediteItem,
  Milestone,
  Project,
  Shipment,
  SimulationResult,
  SimulationScenario,
} from "@/lib/types";

/** Exposed vendors first (expedite / live POs), then the rest of intel. */
export function orderVendorsByExposure(intel: string[], exposed: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const name of [...exposed, ...intel]) {
    if (!name || seen.has(name)) continue;
    seen.add(name);
    out.push(name);
  }
  return out;
}

export type SuggestedSim = {
  scenario: SimulationScenario;
  target: string;
  title: string;
  hint: string;
};

export function hasSimulationImpact(result: SimulationResult): boolean {
  return result.affected_items.length > 0 || result.milestone_impacts.length > 0;
}

function nearestUpcomingMilestone(
  projects: Project[],
  today: string,
): { project: Project; milestone: Milestone } | null {
  let best: { project: Project; milestone: Milestone; date: string } | null = null;
  for (const project of projects) {
    for (const milestone of project.milestones) {
      if (milestone.required_on_site_date < today) continue;
      if (!best || milestone.required_on_site_date < best.date) {
        best = { project, milestone, date: milestone.required_on_site_date };
      }
    }
  }
  return best;
}

function holdShipment(shipments: Shipment[]): Shipment | null {
  const open = shipments.filter((s) => s.current_stage !== "delivered");
  if (!open.length) return null;
  return [...open].sort((a, b) => {
    const aBot = a.bottleneck ? 0 : 1;
    const bBot = b.bottleneck ? 0 : 1;
    if (aBot !== bBot) return aBot - bBot;
    const aSlack = a.slack_days ?? 999;
    const bSlack = b.slack_days ?? 999;
    return aSlack - bSlack;
  })[0];
}

/** Top live questions: vendor slip, shipment hold, nearest need-by. */
export function buildSuggestedSims(input: {
  expediteItems: ExpediteItem[];
  shipments: Shipment[];
  projects: Project[];
  today?: string;
}): SuggestedSim[] {
  const cards: SuggestedSim[] = [];
  const top = input.expediteItems[0];
  if (top?.supplier_name) {
    cards.push({
      scenario: "vendor_slip_2w",
      target: top.supplier_name,
      title: `${top.supplier_name} slips`,
      hint: `${top.po_number} · ${top.slip_probability_pct}% slip · ${top.urgency}`,
    });
  }

  const hold = holdShipment(input.shipments);
  if (hold) {
    cards.push({
      scenario: "customs_hold",
      target: hold.po_ref,
      title: `${hold.po_ref} held in customs`,
      hint: `${hold.vendor} · ${hold.current_stage}${hold.bottleneck ? " · bottleneck" : ""}`,
    });
  }

  const today = input.today ?? new Date().toISOString().slice(0, 10);
  const next = nearestUpcomingMilestone(input.projects, today);
  if (next) {
    cards.push({
      scenario: "need_by_move",
      target: `${next.project.project_id}:${next.milestone.code}`,
      title: `${next.milestone.code} need-by moves`,
      hint: `${next.project.name} · ${next.milestone.name} · ${next.milestone.required_on_site_date}`,
    });
  }

  return cards.slice(0, 3);
}

export function actionPoNumber(result: SimulationResult): string | null {
  const hit = result.affected_items.find((item) =>
    /^(PO|SPO)-/i.test(item.ref_id),
  );
  return hit?.ref_id ?? (result.scenario === "customs_hold" ? result.target : null);
}

export function actionVendorHref(result: SimulationResult): string | null {
  if (result.scenario === "vendor_slip_2w" || result.scenario === "alt_vendor") {
    return `/vendors/${encodeURIComponent(result.target)}`;
  }
  return null;
}

export function actionProjectHref(result: SimulationResult): string | null {
  const first = result.milestone_impacts[0];
  if (first) return `/projects/${encodeURIComponent(first.project_id)}`;
  if (result.scenario === "need_by_move" && result.target.includes(":")) {
    return `/projects/${encodeURIComponent(result.target.split(":")[0])}`;
  }
  return null;
}
