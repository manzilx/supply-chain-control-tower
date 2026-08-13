"use client";

import { useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { addShipmentEvent, fetchShipment } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useAsync } from "@/lib/use-async";
import type { Shipment, ShipmentStage } from "@/lib/types";

export const SHIPMENT_STAGE_ORDER: ShipmentStage[] = [
  "manufacturing",
  "ready_to_dispatch",
  "dispatched",
  "in_transit",
  "at_port",
  "at_customs",
  "last_mile",
  "delivered",
];

export function formatShipmentStage(stage: ShipmentStage): string {
  return stage.replace(/_/g, " ");
}

export function nextShipmentStage(current: ShipmentStage): ShipmentStage | null {
  const idx = SHIPMENT_STAGE_ORDER.indexOf(current);
  if (idx < 0 || idx >= SHIPMENT_STAGE_ORDER.length - 1) return null;
  return SHIPMENT_STAGE_ORDER[idx + 1];
}

export function AdvanceShipmentForm({
  shipment,
  onAdvanced,
}: {
  shipment: Shipment;
  onAdvanced: (stage: ShipmentStage) => void;
}) {
  const { hasPerm } = useAuth();
  const [busy, setBusy] = useState(false);
  const [location, setLocation] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const canAdvance =
    hasPerm("shipment_event", "create") && shipment.current_stage !== "delivered";
  if (!canAdvance) return null;

  const next = nextShipmentStage(shipment.current_stage);
  if (!next) return null;

  const showClearBottleneck =
    !!shipment.bottleneck &&
    (shipment.current_stage === "at_port" || shipment.current_stage === "at_customs");

  async function advance(stage: ShipmentStage, defaultNote?: string) {
    setBusy(true);
    setError(null);
    try {
      await addShipmentEvent(shipment.po_ref, {
        stage,
        location: location.trim() || null,
        note: note.trim() || defaultNote || null,
      });
      setLocation("");
      setNote("");
      onAdvanced(stage);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not advance stage");
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
          type="button"
          className="btn btn-primary text-xs"
          disabled={busy}
          onClick={() => void advance(next)}
        >
          {busy ? "…" : `Advance to ${formatShipmentStage(next)}`}
        </button>
        {showClearBottleneck ? (
          <button
            type="button"
            className="btn btn-secondary text-xs"
            disabled={busy}
            onClick={() => void advance(next, "Bottleneck cleared")}
          >
            Clear bottleneck
          </button>
        ) : null}
      </div>
      {error ? <div className="text-[#ff9d9d] text-sm">{error}</div> : null}
    </div>
  );
}

export function AdvanceShipmentModal({
  poRef,
  code,
  onClose,
  onAdvanced,
}: {
  poRef: string;
  code: string;
  onClose: () => void;
  onAdvanced: (stage: ShipmentStage) => void;
}) {
  const shipment = useAsync(() => fetchShipment(poRef), [poRef]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="panel w-full max-w-xl max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-4 gap-3">
          <div>
            <div className="text-[0.68rem] uppercase tracking-[0.14em] text-muted font-bold">
              Advance shipment · {code}
            </div>
            <h2 className="m-0 text-xl font-bold mt-1">{poRef}</h2>
            <p className="text-sm text-muted mt-1 m-0">
              Record the next logistics stage. TBE and award stay on the RFQ; goods receipt is captured on site.
            </p>
          </div>
          <button type="button" className="btn btn-secondary text-xs" onClick={onClose}>
            Close
          </button>
        </div>
        {shipment.loading ? (
          <EmptyState title="Loading shipment…" />
        ) : shipment.error || !shipment.data ? (
          <div className="text-sm text-[#ff9d9d]">{shipment.error ?? "Shipment not found"}</div>
        ) : (
          <div className="space-y-3">
            <div className="text-sm">
              <span className="text-muted">Current stage · </span>
              <span className="font-semibold text-ink">
                {formatShipmentStage(shipment.data.current_stage)}
              </span>
            </div>
            <AdvanceShipmentForm
              shipment={shipment.data}
              onAdvanced={(stage) => {
                onAdvanced(stage);
              }}
            />
          </div>
        )}
      </div>
    </div>
  );
}
