"use client";

import { useEffect, useRef, useState } from "react";

import { createVendor } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useToast } from "@/lib/toast-context";
import type { SupplierRecord, VendorScorecard } from "@/lib/types";

const DEFAULT: SupplierRecord = {
  name: "",
  category: "",
  country: "",
  lead_time_days: 60,
  on_time_delivery_pct: 90,
  quality_ppm: 500,
  annual_spend_usd: 0,
  approved_alternatives: 1,
  risk_flags: [],
};

// Sector/category hints shown as datalist autocomplete.
const COMMON_CATEGORIES = [
  "Forged valves",
  "Rotating equipment",
  "Electrical",
  "Subsea cables",
  "Offshore structural",
  "Marine epoxy",
  "ROV connectors",
  "Hydro turbines",
  "Generators",
  "Penstock fabrication",
  "Alloy plate",
  "Automation",
  "Instrumentation",
  "Cables",
  "Piping",
  "Heavy machinery",
];

const COMMON_FLAGS = [
  "single source",
  "new supplier",
  "capacity constrained",
  "port congestion",
  "trade tariffs",
  "weather window critical",
  "small batch",
  "transport over-dimensional",
  "welder shortage",
  "late NCR closure",
];

export function AddVendorModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (scorecard: VendorScorecard) => void;
}) {
  const [supplier, setSupplier] = useState<SupplierRecord>(DEFAULT);
  const [flagInput, setFlagInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const firstInput = useRef<HTMLInputElement>(null);
  const toast = useToast();
  const { permissions } = useAuth();
  const canSelfApprove =
    permissions.includes("approval:decide") || permissions.includes("*");

  useEffect(() => {
    if (open) {
      setSupplier(DEFAULT);
      setFlagInput("");
      setError(null);
      setTimeout(() => firstInput.current?.focus(), 30);
    }
  }, [open]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && open) onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  function update<K extends keyof SupplierRecord>(key: K, value: SupplierRecord[K]) {
    setSupplier((s) => ({ ...s, [key]: value }));
  }

  function addFlag(flag: string) {
    const trimmed = flag.trim();
    if (!trimmed) return;
    if (supplier.risk_flags.includes(trimmed)) return;
    update("risk_flags", [...supplier.risk_flags, trimmed]);
  }

  function removeFlag(flag: string) {
    update("risk_flags", supplier.risk_flags.filter((f) => f !== flag));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!supplier.name.trim() || !supplier.category.trim() || !supplier.country.trim()) {
      setError("Name, category, and country are required.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const reply = await createVendor(supplier);
      if (reply.status === "pending_approval") {
        toast.warn("Vendor onboarding sent for approval", {
          label: "View approvals",
          href: "/approvals",
        });
        onClose();
      } else if (reply.scorecard) {
        onCreated(reply.scorecard);
        toast.success("Vendor created");
        onClose();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create vendor");
    } finally {
      setSaving(false);
    }
  }

  // Live preview of how the inputs will likely score (rough heuristic — final
  // score is computed server-side).
  const previewDelivery = supplier.on_time_delivery_pct;
  const previewQuality = Math.max(0, 100 - supplier.quality_ppm / 50);
  const previewRisk = Math.max(
    0,
    100 - supplier.risk_flags.length * 18 - (supplier.approved_alternatives === 0 ? 25 : 0),
  );

  return (
    <div
      className="fixed inset-0 z-[90] flex items-start justify-center pt-[6vh] pb-8 px-4 bg-black/60 backdrop-blur-sm animate-fade-up overflow-y-auto"
      onClick={onClose}
    >
      <form
        onSubmit={handleSubmit}
        onClick={(e) => e.stopPropagation()}
        className="panel w-[min(720px,100%)] shadow-glow"
      >
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="text-[0.65rem] uppercase tracking-[0.14em] text-accent font-bold">Vendors</div>
            <h2 className="m-0 text-xl font-bold">Add new vendor</h2>
            <p className="text-sm text-muted mt-1 m-0">
              {canSelfApprove
                ? "Composite scorecard is computed from these inputs when you save."
                : "Saving sends this vendor for procurement-head approval. It will not appear in the master until approved."}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-[0.65rem] uppercase tracking-[0.1em] text-muted hover:text-ink"
            aria-label="Close"
          >
            Esc
          </button>
        </div>

        <datalist id="vendor-categories">
          {COMMON_CATEGORIES.map((c) => (
            <option key={c} value={c} />
          ))}
        </datalist>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Field label="Name *" hint="Used as the vendor key.">
            <input
              ref={firstInput}
              value={supplier.name}
              onChange={(e) => update("name", e.target.value)}
              placeholder="e.g. Polaris Forging"
              required
            />
          </Field>
          <Field label="Category *" hint="Material category — drives concentration.">
            <input
              list="vendor-categories"
              value={supplier.category}
              onChange={(e) => update("category", e.target.value)}
              placeholder="e.g. Forged valves"
              required
            />
          </Field>
          <Field label="Country *">
            <input
              value={supplier.country}
              onChange={(e) => update("country", e.target.value)}
              placeholder="e.g. India"
              required
            />
          </Field>
          <Field label="Lead time (days)" hint="Quoted lead time from PO to ready-to-dispatch.">
            <input
              type="number"
              min={0}
              value={supplier.lead_time_days}
              onChange={(e) => update("lead_time_days", Number(e.target.value || 0))}
            />
          </Field>
          <Field label="On-time delivery %" hint="Drives Delivery axis (≥97 → A grade).">
            <input
              type="number"
              min={0}
              max={100}
              step="0.1"
              value={supplier.on_time_delivery_pct}
              onChange={(e) => update("on_time_delivery_pct", Number(e.target.value || 0))}
            />
          </Field>
          <Field label="Quality PPM" hint="Defects per million. Drives Quality + Claims (lower = better).">
            <input
              type="number"
              min={0}
              value={supplier.quality_ppm}
              onChange={(e) => update("quality_ppm", Number(e.target.value || 0))}
            />
          </Field>
          <Field label="Annual spend (USD)" hint="Used by concentration analysis + Price axis.">
            <input
              type="number"
              min={0}
              value={supplier.annual_spend_usd}
              onChange={(e) => update("annual_spend_usd", Number(e.target.value || 0))}
            />
          </Field>
          <Field label="Approved alternatives" hint="If 0, vendor flags as single-source exposure.">
            <input
              type="number"
              min={0}
              value={supplier.approved_alternatives}
              onChange={(e) => update("approved_alternatives", Number(e.target.value || 0))}
            />
          </Field>
        </div>

        <div className="mt-4">
          <Label label="Risk flags" hint="Each flag drops Risk axis ~18 pts. Add custom or click a chip." />
          <div className="flex flex-wrap gap-2 mb-2">
            {supplier.risk_flags.map((f) => (
              <span
                key={f}
                className="chip cursor-pointer hover:opacity-70"
                onClick={() => removeFlag(f)}
                title="Click to remove"
              >
                {f} <span className="text-muted">×</span>
              </span>
            ))}
          </div>
          <div className="flex gap-2 mb-2">
            <input
              value={flagInput}
              onChange={(e) => setFlagInput(e.target.value)}
              placeholder="Custom flag…"
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addFlag(flagInput);
                  setFlagInput("");
                }
              }}
              className="flex-1"
            />
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => {
                addFlag(flagInput);
                setFlagInput("");
              }}
            >
              Add
            </button>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {COMMON_FLAGS.filter((f) => !supplier.risk_flags.includes(f)).map((f) => (
              <button
                type="button"
                key={f}
                onClick={() => addFlag(f)}
                className="text-[0.7rem] px-2 py-0.5 rounded-full border border-line text-muted hover:text-ink hover:border-accent transition-colors"
              >
                + {f}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-5 pt-4 border-t border-line">
          <div className="text-[0.65rem] uppercase tracking-[0.12em] text-muted font-bold mb-2">
            Live preview (rough)
          </div>
          <div className="grid grid-cols-3 gap-3 text-sm">
            <PreviewMetric label="Delivery" value={previewDelivery} />
            <PreviewMetric label="Quality" value={previewQuality} />
            <PreviewMetric label="Risk" value={previewRisk} />
          </div>
          <div className="text-[0.65rem] text-muted mt-2">
            Final composite blends 25% delivery · 20% quality · 15% price · 15% responsiveness · 10% claims · 15% risk.
          </div>
        </div>

        {error ? (
          <div className="mt-3 panel-sm border-[rgba(255,117,117,0.3)] text-[#ff9d9d] text-sm">{error}</div>
        ) : null}

        <div className="flex justify-end gap-2 mt-5">
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving
              ? canSelfApprove
                ? "Saving…"
                : "Submitting…"
              : canSelfApprove
                ? "Create vendor"
                : "Submit for approval"}
          </button>
        </div>
      </form>
    </div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1">
      <Label label={label} hint={hint} />
      {children}
    </label>
  );
}

function Label({ label, hint }: { label: string; hint?: string }) {
  return (
    <div>
      <div className="text-[0.65rem] uppercase tracking-[0.12em] text-muted font-bold">{label}</div>
      {hint ? <div className="text-[0.65rem] text-muted">{hint}</div> : null}
    </div>
  );
}

function PreviewMetric({ label, value }: { label: string; value: number }) {
  const v = Math.round(Math.max(0, Math.min(100, value)));
  const tone = v >= 90 ? "text-accent" : v >= 75 ? "text-warning" : "text-danger";
  return (
    <div>
      <div className="text-[0.6rem] uppercase tracking-[0.1em] text-muted font-bold">{label}</div>
      <div className={`text-xl font-bold ${tone}`}>{v}</div>
      <div className="h-1 mt-1 rounded-full bg-white/10 overflow-hidden">
        <div className={`h-full ${tone.replace("text", "bg")}`} style={{ width: `${v}%` }} />
      </div>
    </div>
  );
}
