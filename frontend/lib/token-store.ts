/**
 * Module-level token + tenant-override store.
 *
 * - Persisted in sessionStorage (matches the existing StoreProvider pattern).
 * - Read by `request()` in api.ts on every API call.
 * - Written by AuthProvider on login / logout / tenant switch.
 *
 * Keeping this separate from auth-context so server-imported api functions
 * don't need to traverse React context on every call.
 */

const TOKEN_KEY = "sct.auth.token.v1";
const TENANT_OVERRIDE_KEY = "sct.auth.tenantOverride.v1";

type Listener = () => void;
const listeners = new Set<Listener>();

let _token: string | null = null;
let _tenantOverride: string | null = null;
let _hydrated = false;

function hydrate(): void {
  if (_hydrated) return;
  _hydrated = true;
  if (typeof window === "undefined") return;
  try {
    _token = window.sessionStorage.getItem(TOKEN_KEY);
    _tenantOverride = window.sessionStorage.getItem(TENANT_OVERRIDE_KEY);
  } catch {
    // ignore storage failures
  }
}

export function getToken(): string | null {
  hydrate();
  return _token;
}

export function getTenantOverride(): string | null {
  hydrate();
  return _tenantOverride;
}

export function setToken(token: string | null): void {
  hydrate();
  _token = token;
  if (typeof window !== "undefined") {
    try {
      if (token) window.sessionStorage.setItem(TOKEN_KEY, token);
      else window.sessionStorage.removeItem(TOKEN_KEY);
    } catch {
      // ignore
    }
  }
  listeners.forEach((l) => l());
}

export function setTenantOverride(tenantId: string | null): void {
  hydrate();
  _tenantOverride = tenantId;
  if (typeof window !== "undefined") {
    try {
      if (tenantId) window.sessionStorage.setItem(TENANT_OVERRIDE_KEY, tenantId);
      else window.sessionStorage.removeItem(TENANT_OVERRIDE_KEY);
    } catch {
      // ignore
    }
  }
  listeners.forEach((l) => l());
}

export function subscribe(l: Listener): () => void {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
}
