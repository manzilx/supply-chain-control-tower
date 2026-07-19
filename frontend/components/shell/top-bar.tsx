"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Notifications } from "@/components/notifications";
import { MobileNav } from "@/components/shell/mobile-nav";
import { fetchTenants } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { Tenant } from "@/lib/types";

const ROLE_LABELS: Record<string, string> = {
  admin: "Admin",
  procurement_head: "Procurement Head",
  buyer: "Buyer",
  expeditor: "Expeditor",
  viewer: "Viewer",
};

export function TopBar() {
  const { user, tenant, tenantOverride, setTenantOverride, logout, status: authStatus } = useAuth();
  const router = useRouter();
  const isAdmin = user?.role === "admin";
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [tenantsLoading, setTenantsLoading] = useState(false);
  const [switchingTenant, setSwitchingTenant] = useState(false);

  useEffect(() => {
    if (!isAdmin || authStatus !== "authed") return;
    let cancelled = false;
    setTenantsLoading(true);
    fetchTenants()
      .then((list) => {
        if (!cancelled) setTenants(list);
      })
      .catch(() => {
        if (!cancelled) setTenants([]);
      })
      .finally(() => {
        if (!cancelled) setTenantsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isAdmin, authStatus]);

  const handleSignOut = () => {
    logout();
    router.replace("/login");
  };

  const handleTenantSwitch = async (tenantId: string) => {
    if (!user) return;
    const nextOverride = tenantId === user.tenant_id ? null : tenantId;
    if (nextOverride === tenantOverride) return;
    setSwitchingTenant(true);
    try {
      await setTenantOverride(nextOverride);
      window.dispatchEvent(new Event("sct:tenant-changed"));
      router.refresh();
    } finally {
      setSwitchingTenant(false);
    }
  };

  return (
    <header className="sticky top-0 z-10 border-b border-line bg-[rgba(7,16,24,0.72)] backdrop-blur-xl">
      <div className="flex items-center gap-4 px-6 py-3">
        <MobileNav />
        <div className="min-w-0">
          <div className="text-[0.68rem] uppercase tracking-[0.16em] text-muted font-bold">
            Workspace
          </div>
          <div className="flex items-center gap-3 text-sm">
            <span className="text-ink font-semibold truncate">
              {tenant?.name ?? "Control Tower"}
            </span>
          </div>
        </div>

        <div className="ml-auto flex items-center gap-3">
          <button
            onClick={() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true }))}
            className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-lg border border-line bg-white/[0.02] hover:bg-white/[0.05] transition-colors"
            aria-label="Open command palette"
            title="Search (⌘K)"
          >
            <span className="text-xs text-muted">Search…</span>
            <kbd className="text-[0.6rem] uppercase tracking-[0.1em] text-muted border border-line rounded px-1.5 py-0.5 font-mono">⌘K</kbd>
          </button>

          <Notifications />

          {user && tenant ? (
            <div className="hidden md:flex items-center gap-2 pl-3 ml-1 border-l border-line">
              <div className="text-right">
                <div className="text-xs text-ink font-semibold truncate max-w-[10rem]">
                  {user.display_name}
                </div>
                <div className="flex items-center gap-1.5 text-[0.68rem] uppercase tracking-[0.12em] text-muted">
                  {isAdmin && tenants.length > 0 ? (
                    <select
                      className="!w-auto max-w-[11rem] py-0.5 px-2 text-[0.68rem] uppercase tracking-[0.12em] rounded-lg border border-line bg-white/[0.02] text-ink"
                      value={tenantOverride ?? user.tenant_id}
                      onChange={(e) => void handleTenantSwitch(e.target.value)}
                      disabled={tenantsLoading || switchingTenant}
                      aria-label="Switch tenant"
                      title={tenantOverride ? "Viewing another tenant (override active)" : "Your home tenant"}
                    >
                      {tenants.map((t) => (
                        <option key={t.tenant_id} value={t.tenant_id}>
                          {t.name}
                          {t.tenant_id === user.tenant_id ? " (home)" : ""}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <span className="truncate max-w-[10rem]">{tenant.name}</span>
                  )}
                  <span>·</span>
                  <span>{ROLE_LABELS[user.role] ?? user.role}</span>
                  {tenantOverride ? (
                    <span className="text-accent normal-case tracking-normal font-semibold" title="Tenant override active">
                      · viewing
                    </span>
                  ) : null}
                </div>
              </div>
              <button
                className="btn btn-secondary"
                onClick={handleSignOut}
                aria-label="Sign out"
              >
                Sign out
              </button>
            </div>
          ) : null}
        </div>
      </div>
    </header>
  );
}
