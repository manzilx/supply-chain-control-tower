"use client";

import { useMemo, useState } from "react";

import { AnimatedKpiTile, Donut, MotionPanel, StageFunnel } from "@/components/charts";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { addShipmentEvent, fetchLogisticsQueue, fetchModeRecommendation } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatDate, formatMoney } from "@/lib/format-date";
import { useToast } from "@/lib/toast-context";
import { useAsync } from "@/lib/use-async";
import type {
  FreightMode,
  ModeRecommendation,
  Shipment,
  ShipmentStage,
} from "@/lib/types";

const STAGE_TONE: Record<ShipmentStage, string> = {
  manufacturing: "severity-medium",
  ready_to_dispatch: "severity-medium",
  dispatched: "severity-low",
  in_transit: "severity-low",
  at_port: "severity-high",
  at_customs: "severity-high",
  last_mile: "severity-low",
  delivered: "severity-low",
};

const MODE_LABEL: Record<FreightMode, string> = {
  sea: "Sea",
  air: "Air",
  road: "Road",
  rail: "Rail",
  local: "Local",
};

export default function LogisticsPage() {
  const queue = useAsync(fetchLogisticsQueue, []);
  const [stage, setStage] = useState<ShipmentStage | "all">("all");
  const [bottleneckOnly, setBottleneckOnly] = useState(false);
  const [modeReco, setModeReco] = useState<ModeRecommendation | null>(null);
  const [loadingReco, setLoadingReco] = useState<string | null>(null);

  const rows = useMemo(() => {
    const items = queue.data?.shipments ?? [];
    return items
      .filter((s) => stage === "all" || s.current_stage === stage)
      .filter((s) => !bottleneckOnly || !!s.bottleneck);
  }, [queue.data, stage, bottleneckOnly]);

  async function showReco(s: Shipment) {
    setLoadingReco(s.po_ref);
    setModeReco(null);
    try {
      const reco = await fetchModeRecommendation(s.po_ref);
      setModeReco(reco);
    } finally {
      setLoadingReco(null);
    }
  }

  const summary = queue.data?.summary;

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Logistics"
        title="Delivery Control Tower"
        description="Live shipment stages across every open order. Bottlenecks surface at the top; the mode recommender suggests when to switch freight modes."
        right={
          <button className="btn btn-secondary" onClick={() => queue.reload()}>
            Refresh
          </button>
        }
      />

      {queue.loading ? (
        <EmptyState title="Loading shipments..." />
      ) : queue.error ? (
        <div className="panel-sm border-[rgba(255,117,117,0.3)] text-[#ff9d9d]">{queue.error}</div>
      ) : !summary ? (
        <EmptyState title="No shipments" />
      ) : (
        <>
          <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <AnimatedKpiTile label="Total" value={summary.total} delay={0.00} />
            <AnimatedKpiTile label="In Motion" value={summary.in_motion} delay={0.05} tone="neutral" />
            <AnimatedKpiTile label="Bottleneck" value={summary.at_bottleneck} delay={0.10} tone={summary.at_bottleneck ? "bad" : "good"} />
            <AnimatedKpiTile label="Value in Motion" value={summary.value_in_motion_usd} prefix="$" delay={0.15} />
          </section>

          <MotionPanel delay={0.2}>
            <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="md:col-span-2">
                <StageFunnel
                  title="Shipments by stage"
                  data={(() => {
                    const counts: Record<string, number> = {};
                    (queue.data?.shipments || []).forEach((s) => {
                      counts[s.current_stage] = (counts[s.current_stage] || 0) + 1;
                    });
                    const order: ShipmentStage[] = [
                      "manufacturing", "ready_to_dispatch", "dispatched",
                      "in_transit", "at_port", "at_customs", "last_mile", "delivered",
                    ];
                    return order
                      .map((s) => ({ name: s.replace(/_/g, " "), value: counts[s] || 0 }))
                      .filter((d) => d.value > 0);
                  })()}
                  height={280}
                />
              </div>
              <Donut
                title="Mode mix"
                data={(() => {
                  const counts: Record<string, number> = {};
                  (queue.data?.shipments || []).forEach((s) => {
                    counts[s.mode] = (counts[s.mode] || 0) + 1;
                  });
                  return Object.entries(counts).map(([name, value]) => ({ name, value }));
                })()}
                centerLabel="modes"
                centerValue={summary.total}
                height={280}
              />
            </section>
          </MotionPanel>

          <div className="panel-sm flex flex-wrap gap-3 items-end">
            <label className="min-w-[180px] flex flex-col gap-1">
              <span className="text-[0.68rem] uppercase tracking-[0.12em] text-muted font-bold">Stage</span>
              <select value={stage} onChange={(e) => setStage(e.target.value as ShipmentStage | "all")}>
                <option value="all">All stages</option>
                <option value="manufacturing">manufacturing</option>
                <option value="ready_to_dispatch">ready to dispatch</option>
                <option value="dispatched">dispatched</option>
                <option value="in_transit">in transit</option>
                <option value="at_port">at port</option>
                <option value="at_customs">at customs</option>
                <option value="last_mile">last mile</option>
                <option value="delivered">delivered</option>
              </select>
            </label>
            <label className="flex items-center gap-2 text-sm pb-2 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={bottleneckOnly}
                onChange={(e) => setBottleneckOnly(e.target.checked)}
                style={{ width: "1rem" }}
              />
              <span className="text-muted">Only bottlenecks</span>
            </label>
            <div className="text-xs text-muted pb-2">
              {rows.length} of {queue.data?.shipments.length ?? 0}
            </div>
          </div>

          <div className="space-y-3">
            {rows.length === 0 ? (
              <EmptyState title="No shipments match filters" />
            ) : (
              rows.map((s) => (
                <article key={`${s.source}-${s.po_ref}`} className="panel space-y-3">
                  <div className="flex items-start justify-between gap-4 flex-wrap">
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-mono text-xs text-ink font-semibold">{s.po_ref}</span>
                        <span className={`badge ${STAGE_TONE[s.current_stage]}`}>
                          {s.current_stage.replace(/_/g, " ")}
                        </span>
                        <span className="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold bg-white/5 text-muted">
                          {MODE_LABEL[s.mode]}
                        </span>
                        <span className="text-[0.65rem] uppercase tracking-wider text-muted">{s.source}</span>
                      </div>
                      <div className="text-ink font-bold mt-1">{s.vendor}</div>
                      <div className="text-sm text-muted">
                        {s.description || s.code} · {s.quantity}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-bold text-ink">{formatMoney(s.value_usd)}</div>
                      <div className="text-xs text-muted">
                        {s.origin_country ?? "—"} → {s.destination_site ?? "—"}
                      </div>
                    </div>
                  </div>

                  <StageTrack current={s.current_stage} />

                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                    <Stat label="Required on site" value={formatDate(s.required_on_site)} />
                    <Stat label="Estimated arrival" value={formatDate(s.estimated_arrival)} />
                    <Stat
                      label="Slack"
                      value={s.slack_days != null ? `${s.slack_days}d` : "—"}
                      tone={s.slack_days != null && s.slack_days < 0 ? "bad" : "neutral"}
                    />
                    <Stat label="Events" value={String(s.events.length)} />
                  </div>

                  {s.bottleneck ? (
                    <div className="panel-sm border-[rgba(255,117,117,0.3)] text-sm">
                      <span className="section-title mr-2">Bottleneck</span>
                      <span className="text-ink">{s.bottleneck}</span>
                    </div>
                  ) : null}

                  <ShipmentAdvanceControls shipment={s} onAdvanced={() => queue.reload()} />

                  {s.events.length > 0 ? (
                    <details className="panel-sm">
                      <summary className="cursor-pointer text-sm text-muted select-none">
                        Event log ({s.events.length})
                      </summary>
                      <ol className="mt-3 space-y-2">
                        {s.events.map((e) => (
                          <li key={e.event_id} className="text-xs">
                            <span className="font-mono text-muted">{formatDate(e.at)}</span>
                            <span className="mx-2 text-ink font-semibold capitalize">
                              {e.stage.replace(/_/g, " ")}
                            </span>
                            {e.location ? <span className="text-muted">· {e.location}</span> : null}
                            {e.note ? <div className="text-muted mt-0.5">{e.note}</div> : null}
                          </li>
                        ))}
                      </ol>
                    </details>
                  ) : null}

                  <div className="flex items-center gap-3">
                    <button
                      className="btn btn-secondary text-xs"
                      onClick={() => void showReco(s)}
                      disabled={loadingReco === s.po_ref}
                    >
                      {loadingReco === s.po_ref ? "..." : "Recommend mode"}
                    </button>
                    {modeReco && modeReco.po_ref === s.po_ref ? (
                      <div className="text-xs">
                        <span className="text-[0.68rem] uppercase tracking-[0.12em] text-muted font-bold mr-2">
                          {modeReco.current_mode} → {modeReco.recommended_mode}
                        </span>
                        <span className="text-muted">
                          ~{modeReco.transit_days_estimate}d · ×{modeReco.cost_multiplier.toFixed(1)} cost ·{" "}
                        </span>
                        <span className="text-ink">{modeReco.rationale}</span>
                      </div>
                    ) : null}
                  </div>
                </article>
              ))
            )}
          </div>
        </>
      )}
    </div>
  );
}

const STAGE_ORDER: ShipmentStage[] = [
  "manufacturing",
  "ready_to_dispatch",
  "dispatched",
  "in_transit",
  "at_port",
  "at_customs",
  "last_mile",
  "delivered",
];

function formatStage(stage: ShipmentStage): string {
  return stage.replace(/_/g, " ");
}

function nextStage(current: ShipmentStage): ShipmentStage | null {
  const idx = STAGE_ORDER.indexOf(current);
  if (idx < 0 || idx >= STAGE_ORDER.length - 1) return null;
  return STAGE_ORDER[idx + 1];
}

function ShipmentAdvanceControls({
  shipment,
  onAdvanced,
}: {
  shipment: Shipment;
  onAdvanced: () => void;
}) {
  const { hasPerm } = useAuth();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [location, setLocation] = useState("");
  const [note, setNote] = useState("");

  const canAdvance =
    hasPerm("shipment_event", "create") && shipment.current_stage !== "delivered";
  if (!canAdvance) return null;

  const next = nextStage(shipment.current_stage);
  if (!next) return null;

  const showClearBottleneck =
    !!shipment.bottleneck &&
    (shipment.current_stage === "at_port" || shipment.current_stage === "at_customs");

  async function advance(stage: ShipmentStage, defaultNote?: string) {
    setBusy(true);
    try {
      await addShipmentEvent(shipment.po_ref, {
        stage,
        location: location.trim() || null,
        note: note.trim() || defaultNote || null,
      });
      toast.success(`Advanced to ${formatStage(stage)}`);
      setLocation("");
      setNote("");
      onAdvanced();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not advance stage");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel-sm space-y-2">
      <div className="text-[0.68rem] uppercase tracking-[0.12em] text-muted font-bold">
        Advance shipment
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <input
          placeholder="Location (optional)…"
          value={location}
          onChange={(e) => setLocation(e.target.value)}
          className="text-sm"
          disabled={busy}
        />
        <input
          placeholder="Note (optional)…"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          className="text-sm"
          disabled={busy}
        />
      </div>
      <div className="flex flex-wrap gap-2">
        <button
          className="btn btn-primary text-xs"
          disabled={busy}
          onClick={() => void advance(next)}
        >
          {busy ? "…" : `Advance to ${formatStage(next)}`}
        </button>
        {showClearBottleneck ? (
          <button
            className="btn btn-secondary text-xs"
            disabled={busy}
            onClick={() => void advance(next, "Bottleneck cleared")}
          >
            Clear bottleneck
          </button>
        ) : null}
      </div>
    </div>
  );
}

function StageTrack({ current }: { current: ShipmentStage }) {
  const idx = STAGE_ORDER.indexOf(current);
  return (
    <div className="flex items-center gap-1">
      {STAGE_ORDER.map((s, i) => {
        const active = i <= idx;
        const isCurrent = i === idx;
        return (
          <div key={s} className="flex-1 flex flex-col items-center gap-1 min-w-0">
            <div
              className={[
                "w-full h-1 rounded-full",
                active ? (isCurrent ? "bg-accent" : "bg-accent/50") : "bg-white/10",
              ].join(" ")}
            />
            <div
              className={[
                "text-[0.6rem] uppercase tracking-wider truncate w-full text-center",
                isCurrent ? "text-accent font-bold" : active ? "text-ink/70" : "text-muted",
              ].join(" ")}
            >
              {s.replace(/_/g, " ")}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Stat({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: "neutral" | "bad" | "good";
}) {
  const color = tone === "bad" ? "text-danger" : tone === "good" ? "text-accent" : "text-ink";
  return (
    <div>
      <div className="text-[0.6rem] uppercase tracking-[0.14em] text-muted font-bold">{label}</div>
      <div className={`font-semibold ${color}`}>{value}</div>
    </div>
  );
}
