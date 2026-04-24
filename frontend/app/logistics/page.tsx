"use client";

import { useMemo, useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { KpiTile } from "@/components/kpi-tile";
import { PageHeader } from "@/components/page-header";
import { fetchLogisticsQueue, fetchModeRecommendation } from "@/lib/api";
import { formatDate, formatMoney } from "@/lib/format-date";
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
            <KpiTile label="Total" value={String(summary.total)} />
            <KpiTile label="In Motion" value={String(summary.in_motion)} />
            <KpiTile
              label="Bottleneck"
              value={String(summary.at_bottleneck)}
              tone={summary.at_bottleneck ? "bad" : "good"}
            />
            <KpiTile label="Value in Motion" value={formatMoney(summary.value_in_motion_usd)} />
          </section>

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
