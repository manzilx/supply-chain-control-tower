"use client";

import { useEffect, useRef, useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { SkeletonCard } from "@/components/skeleton";
import { createEnrolment, createStore, fetchFieldDevices, fetchStores, revokeDevice } from "@/lib/api";
import { formatTimestamp } from "@/lib/format";
import { useToast } from "@/lib/toast-context";
import { useAsync } from "@/lib/use-async";
import type { CaptureDeviceOut, EnrolmentInviteOut, StorePersonRole } from "@/lib/types";

const ROLE_LABEL: Record<StorePersonRole, string> = {
  storekeeper: "Storekeeper",
  foreman: "Foreman",
};

export default function FieldDevicesPage() {
  const query = useAsync(fetchFieldDevices, []);
  const toast = useToast();
  const [enrolOpen, setEnrolOpen] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const devices = query.data ?? [];

  async function handleRevoke(d: CaptureDeviceOut) {
    if (!confirm(`Revoke ${d.person_name}'s device? They will need to re-enrol to resume capturing.`)) {
      return;
    }
    setBusyId(d.device_id);
    try {
      await revokeDevice(d.device_id);
      toast.warn(`${d.person_name}'s device revoked`);
      query.reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not revoke device");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Site Store"
        title="Field Devices"
        description="Phones enrolled to capture GRNs from site. Each device tracks its own sequence watermark for gap detection."
        right={
          <div className="flex gap-2">
            <button className="btn btn-secondary" onClick={() => query.reload()}>
              Refresh
            </button>
            <button className="btn btn-primary" onClick={() => setEnrolOpen(true)}>
              Enrol device
            </button>
          </div>
        }
      />

      <div className="panel overflow-x-auto p-0">
        {query.loading ? (
          <div className="p-6 space-y-3">
            <SkeletonCard />
            <SkeletonCard />
          </div>
        ) : query.error ? (
          <div className="p-6 text-[#ff9d9d]">{query.error}</div>
        ) : devices.length === 0 ? (
          <div className="p-6">
            <EmptyState
              title="No devices enrolled"
              hint="Enrol a storekeeper or foreman's phone to start capturing GRNs."
            />
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Person</th>
                <th>Role</th>
                <th>Store</th>
                <th>Last Seen</th>
                <th>Seq Watermark</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {devices.map((d) => (
                <tr key={d.device_id}>
                  <td className="font-semibold text-ink">{d.person_name}</td>
                  <td className="text-muted">{ROLE_LABEL[d.person_role]}</td>
                  <td className="font-mono text-xs text-muted">{d.store_id ?? "—"}</td>
                  <td className="text-muted text-xs">
                    {d.last_seen_at ? formatTimestamp(d.last_seen_at) : "Never"}
                  </td>
                  <td>{d.last_sequence_no}</td>
                  <td>
                    {d.revoked_at ? (
                      <span className="badge text-muted">revoked</span>
                    ) : (
                      <span className="badge severity-low">active</span>
                    )}
                  </td>
                  <td>
                    {d.revoked_at ? null : (
                      <button
                        className="btn btn-secondary text-xs"
                        disabled={busyId === d.device_id}
                        onClick={() => void handleRevoke(d)}
                      >
                        {busyId === d.device_id ? "…" : "Revoke"}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {enrolOpen ? (
        <EnrolDeviceModal onClose={() => setEnrolOpen(false)} onEnrolled={() => query.reload()} />
      ) : null}
    </div>
  );
}

function EnrolDeviceModal({ onClose, onEnrolled }: { onClose: () => void; onEnrolled: () => void }) {
  const stores = useAsync(fetchStores, []);
  const toast = useToast();
  const [storeId, setStoreId] = useState("");
  const [personName, setPersonName] = useState("");
  const [role, setRole] = useState<StorePersonRole>("storekeeper");
  const [newStoreOpen, setNewStoreOpen] = useState(false);
  const [newProjectId, setNewProjectId] = useState("");
  const [newStoreName, setNewStoreName] = useState("");
  const [creatingStore, setCreatingStore] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [invite, setInvite] = useState<EnrolmentInviteOut | null>(null);
  const firstInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setTimeout(() => firstInput.current?.focus(), 30);
  }, []);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Default to the first store once the list loads.
  useEffect(() => {
    if (!storeId && stores.data?.length) setStoreId(stores.data[0].store_id);
  }, [stores.data, storeId]);

  async function handleCreateStore() {
    if (!newProjectId.trim() || !newStoreName.trim()) return;
    setCreatingStore(true);
    setError(null);
    try {
      const store = await createStore({ project_id: newProjectId.trim(), name: newStoreName.trim() });
      setStoreId(store.store_id);
      setNewStoreOpen(false);
      setNewProjectId("");
      setNewStoreName("");
      toast.success(`Store ${store.name} created`);
      stores.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create store");
    } finally {
      setCreatingStore(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!storeId || !personName.trim()) {
      setError("Store and person name are required.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const reply = await createEnrolment({
        store_id: storeId,
        person_name: personName.trim(),
        person_role: role,
      });
      setInvite(reply);
      onEnrolled();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create enrolment");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-[90] flex items-start justify-center pt-[6vh] pb-8 px-4 bg-black/60 backdrop-blur-sm overflow-y-auto"
      onClick={onClose}
    >
      <div className="panel w-[min(560px,100%)]" onClick={(e) => e.stopPropagation()}>
        {invite ? (
          <>
            <div className="text-[0.65rem] uppercase tracking-[0.14em] text-accent font-bold mb-1">
              Field Devices
            </div>
            <h2 className="m-0 text-xl font-bold mb-4">Enrolment code</h2>
            <div className="panel-sm text-center py-8 mb-3">
              <div className="text-4xl font-mono font-extrabold tracking-[0.3em] text-accent">
                {invite.code}
              </div>
            </div>
            <div className="text-sm text-muted text-center mb-1">
              For {invite.person_name} · {ROLE_LABEL[invite.person_role]}
            </div>
            <div className="text-sm text-muted text-center mb-4">
              Expires {formatTimestamp(invite.expires_at)}
            </div>
            <div className="panel-sm text-xs text-warning text-center mb-4">
              This code is shown once. Hand it to {invite.person_name} now — it won't be retrievable again.
            </div>
            <div className="flex justify-end">
              <button className="btn btn-primary" onClick={onClose}>
                Done
              </button>
            </div>
          </>
        ) : (
          <form onSubmit={handleSubmit}>
            <div className="flex items-center justify-between mb-4">
              <div>
                <div className="text-[0.65rem] uppercase tracking-[0.14em] text-accent font-bold">
                  Field Devices
                </div>
                <h2 className="m-0 text-xl font-bold">Enrol device</h2>
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

            <div className="space-y-4">
              <label className="flex flex-col gap-1">
                <span className="text-[0.65rem] uppercase tracking-[0.12em] text-muted font-bold">Store</span>
                <select
                  value={storeId}
                  onChange={(e) => setStoreId(e.target.value)}
                  disabled={stores.loading}
                  required
                >
                  {stores.loading ? <option value="">Loading stores…</option> : null}
                  {(stores.data ?? []).map((s) => (
                    <option key={s.store_id} value={s.store_id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </label>

              {newStoreOpen ? (
                <div className="panel-sm space-y-2">
                  <label className="flex flex-col gap-1">
                    <span className="text-[0.62rem] uppercase tracking-[0.1em] text-muted font-bold">
                      Project ID
                    </span>
                    <input
                      value={newProjectId}
                      onChange={(e) => setNewProjectId(e.target.value)}
                      placeholder="e.g. PRJ-001"
                    />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-[0.62rem] uppercase tracking-[0.1em] text-muted font-bold">Name</span>
                    <input
                      value={newStoreName}
                      onChange={(e) => setNewStoreName(e.target.value)}
                      placeholder="e.g. Site store A"
                    />
                  </label>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      className="btn btn-primary text-xs"
                      onClick={() => void handleCreateStore()}
                      disabled={creatingStore}
                    >
                      {creatingStore ? "Creating…" : "Create store"}
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary text-xs"
                      onClick={() => setNewStoreOpen(false)}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  type="button"
                  className="text-xs text-accent hover:underline"
                  onClick={() => setNewStoreOpen(true)}
                >
                  + New store
                </button>
              )}

              <label className="flex flex-col gap-1">
                <span className="text-[0.65rem] uppercase tracking-[0.12em] text-muted font-bold">
                  Person name
                </span>
                <input
                  ref={firstInput}
                  value={personName}
                  onChange={(e) => setPersonName(e.target.value)}
                  placeholder="e.g. Ramesh Kumar"
                  required
                />
              </label>

              <label className="flex flex-col gap-1">
                <span className="text-[0.65rem] uppercase tracking-[0.12em] text-muted font-bold">Role</span>
                <select value={role} onChange={(e) => setRole(e.target.value as StorePersonRole)}>
                  <option value="storekeeper">Storekeeper</option>
                  <option value="foreman">Foreman</option>
                </select>
              </label>
            </div>

            {error ? (
              <div className="mt-3 panel-sm border-[rgba(255,117,117,0.3)] text-[#ff9d9d] text-sm">{error}</div>
            ) : null}

            <div className="flex justify-end gap-2 mt-5">
              <button type="button" className="btn btn-secondary" onClick={onClose} disabled={submitting}>
                Cancel
              </button>
              <button type="submit" className="btn btn-primary" disabled={submitting || !storeId}>
                {submitting ? "Enrolling…" : "Generate code"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
