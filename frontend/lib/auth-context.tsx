"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { LoginReply, MeReply, Tenant, User } from "@/lib/types";
import {
  getTenantOverride,
  getToken,
  setTenantOverride as setStoredTenantOverride,
  setToken as setStoredToken,
  subscribe,
} from "@/lib/token-store";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8010";

type AuthValue = {
  token: string | null;
  user: User | null;
  tenant: Tenant | null;
  permissions: string[];
  status: "bootstrapping" | "anonymous" | "authed" | "error";
  error: string | null;
  tenantOverride: string | null;
  canSwitchTenant: boolean;
  login: (userId: string, password?: string) => Promise<void>;
  logout: () => void;
  setTenantOverride: (tenantId: string | null) => Promise<void>;
  hasPerm: (resource: string, action: string) => boolean;
};

const AuthContext = createContext<AuthValue | null>(null);

function hasPermImpl(perms: string[], resource: string, action: string): boolean {
  if (perms.includes("*")) return true;
  return (
    perms.includes(`${resource}:${action}`) ||
    perms.includes(`${resource}:*`) ||
    perms.includes(`*:${action}`)
  );
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [tenantOverride, setTenantOverrideState] = useState<string | null>(null);
  const [canSwitchTenant, setCanSwitchTenant] = useState(false);
  const [status, setStatus] = useState<AuthValue["status"]>("bootstrapping");
  const [error, setError] = useState<string | null>(null);

  // Sync React state to token-store changes (e.g. logout from another tab).
  useEffect(() => {
    setTokenState(getToken());
    setTenantOverrideState(getTenantOverride());
    return subscribe(() => {
      setTokenState(getToken());
      setTenantOverrideState(getTenantOverride());
    });
  }, []);

  // Bootstrap: if a token exists in sessionStorage, call /api/auth/me to
  // hydrate user+tenant+permissions. If it fails, clear and land on anonymous.
  useEffect(() => {
    const t = getToken();
    if (!t) {
      setStatus("anonymous");
      return;
    }
    const override = getTenantOverride();
    const headers: Record<string, string> = { Authorization: `Bearer ${t}` };
    if (override) headers["X-Tenant-Override"] = override;
    fetch(`${API_BASE}/api/auth/me`, { headers, cache: "no-store" })
      .then(async (res) => {
        if (!res.ok) throw new Error(`me failed: ${res.status}`);
        return res.json();
      })
      .then((me: MeReply) => {
        setUser(me.user);
        setTenant(me.tenant);
        setPermissions(me.permissions);
        setCanSwitchTenant(me.can_switch_tenant);
        setStatus("authed");
      })
      .catch(() => {
        setStoredToken(null);
        setStoredTenantOverride(null);
        setStatus("anonymous");
      });
  }, []);

  const login = useCallback(async (userId: string, password?: string) => {
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(password === undefined ? { user_id: userId } : { user_id: userId, password }),
      });
      if (!res.ok) {
        const msg = await res.text();
        let detail = msg;
        try {
          detail = (JSON.parse(msg) as { detail?: string }).detail ?? msg;
        } catch {
          // plain-text error body
        }
        throw new Error(detail || "Login failed");
      }
      const reply: LoginReply = await res.json();
      setStoredToken(reply.token);
      setStoredTenantOverride(null);
      setUser(reply.user);
      setTenant(reply.tenant);
      setPermissions(reply.permissions);
      setCanSwitchTenant(reply.can_switch_tenant);
      setStatus("authed");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Login failed");
      setStatus("error");
      throw e;
    }
  }, []);

  const logout = useCallback(() => {
    setStoredToken(null);
    setStoredTenantOverride(null);
    setUser(null);
    setTenant(null);
    setPermissions([]);
    setCanSwitchTenant(false);
    setStatus("anonymous");
    // Also clear any scenario cache from prior session.
    if (typeof window !== "undefined") {
      try {
        window.sessionStorage.removeItem("sct.scenario.v1");
        window.sessionStorage.removeItem("sct.analysis.v1");
      } catch {
        // ignore
      }
    }
  }, []);

  const setTenantOverride = useCallback(
    async (tenantId: string | null) => {
      setStoredTenantOverride(tenantId);
      // Re-hydrate user/tenant to reflect override via /me.
      const t = getToken();
      if (!t) return;
      const headers: Record<string, string> = { Authorization: `Bearer ${t}` };
      if (tenantId) headers["X-Tenant-Override"] = tenantId;
      const res = await fetch(`${API_BASE}/api/auth/me`, { headers, cache: "no-store" });
      if (res.ok) {
        const me: MeReply = await res.json();
        setUser(me.user);
        setTenant(me.tenant);
        setPermissions(me.permissions);
        setCanSwitchTenant(me.can_switch_tenant);
      }
    },
    [],
  );

  const hasPerm = useCallback(
    (resource: string, action: string) => hasPermImpl(permissions, resource, action),
    [permissions],
  );

  const value = useMemo<AuthValue>(
    () => ({
      token,
      user,
      tenant,
      permissions,
      status,
      error,
      tenantOverride,
      canSwitchTenant,
      login,
      logout,
      setTenantOverride,
      hasPerm,
    }),
    [token, user, tenant, permissions, status, error, tenantOverride, canSwitchTenant, login, logout, setTenantOverride, hasPerm],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const v = useContext(AuthContext);
  if (!v) throw new Error("useAuth must be used within AuthProvider");
  return v;
}
