"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { fetchAuthMode, fetchPersonas } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { Persona, Role } from "@/lib/types";

const ROLE_LABELS: Record<Role, string> = {
  admin: "Admin",
  procurement_head: "Procurement Head",
  buyer: "Buyer",
  expeditor: "Expeditor",
  viewer: "Viewer",
  storekeeper: "Site Storekeeper",
};

const ROLE_ACCENT: Record<Role, string> = {
  admin: "bg-violet-500/15 text-violet-300 border-violet-500/40",
  procurement_head: "bg-sky-500/15 text-sky-300 border-sky-500/40",
  buyer: "bg-emerald-500/15 text-emerald-300 border-emerald-500/40",
  expeditor: "bg-amber-500/15 text-amber-300 border-amber-500/40",
  viewer: "bg-zinc-500/15 text-zinc-300 border-zinc-500/40",
  storekeeper: "bg-teal-500/15 text-teal-300 border-teal-500/40",
};

export default function LoginPage() {
  const [demoLogin, setDemoLogin] = useState<boolean | null>(null);
  const [personas, setPersonas] = useState<Persona[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const router = useRouter();
  const { login, status } = useAuth();

  useEffect(() => {
    fetchAuthMode()
      .then(({ demo_login }) => demo_login)
      // An older backend has no /api/auth/mode — it only knows the picker.
      .catch(() => true)
      .then((demo) => {
        setDemoLogin(demo);
        if (!demo) return;
        return fetchPersonas().then(setPersonas);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Could not reach the server"));
  }, []);

  useEffect(() => {
    if (status === "authed") router.replace("/overview");
  }, [status, router]);

  const byTenant = useMemo(() => {
    const groups = new Map<string, { name: string; personas: Persona[] }>();
    for (const p of personas ?? []) {
      const entry = groups.get(p.tenant_id);
      if (entry) entry.personas.push(p);
      else groups.set(p.tenant_id, { name: p.tenant_name, personas: [p] });
    }
    return Array.from(groups.entries());
  }, [personas]);

  const handleLogin = async (userId: string, pwd?: string) => {
    setSubmitting(userId);
    setError(null);
    try {
      await login(userId, pwd);
      router.replace("/overview");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Login failed");
    } finally {
      setSubmitting(null);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-6 py-12 bg-[rgba(7,16,24,1)]">
      <div className="w-full max-w-4xl">
        <div className="mb-8 text-center">
          <div className="text-[0.68rem] uppercase tracking-[0.2em] text-muted font-bold">
            Supply Chain Control Tower
          </div>
          {demoLogin === false ? (
            <h1 className="mt-2 text-2xl font-semibold text-ink">Sign in</h1>
          ) : (
            <>
              <h1 className="mt-2 text-2xl font-semibold text-ink">Pick a persona to sign in</h1>
              <p className="mt-1 text-sm text-muted">
                Demo environment — no password required. Each tenant seeds one user per role.
              </p>
            </>
          )}
        </div>

        {error ? (
          <div className="mb-4 rounded border border-[rgba(255,117,117,0.3)] bg-[rgba(255,117,117,0.08)] px-4 py-3 text-sm text-[#ff9d9d]">
            {error}
          </div>
        ) : null}

        {demoLogin === false ? (
          <form
            className="mx-auto max-w-sm space-y-4 rounded-xl border border-line bg-[rgba(17,26,36,0.6)] p-5"
            onSubmit={(e) => {
              e.preventDefault();
              void handleLogin(email.trim(), password);
            }}
          >
            <label className="block text-sm text-muted">
              Email
              <input
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1 w-full rounded border border-line bg-[rgba(7,16,24,0.6)] px-3 py-2 text-sm text-ink"
              />
            </label>
            <label className="block text-sm text-muted">
              Password
              <input
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1 w-full rounded border border-line bg-[rgba(7,16,24,0.6)] px-3 py-2 text-sm text-ink"
              />
            </label>
            <button
              type="submit"
              disabled={submitting !== null}
              className="w-full rounded-lg border border-[rgba(120,180,255,0.4)] bg-[rgba(17,26,36,0.9)] px-3 py-2 text-sm font-semibold text-ink disabled:opacity-50"
            >
              {submitting !== null ? "Signing in…" : "Sign in"}
            </button>
          </form>
        ) : !personas ? (
          <div className="text-center text-sm text-muted">Loading…</div>
        ) : (
          <div className="space-y-6">
            {byTenant.map(([tenantId, { name, personas: members }]) => (
              <section
                key={tenantId}
                className="rounded-xl border border-line bg-[rgba(17,26,36,0.6)] p-5"
              >
                <div className="mb-3 flex items-baseline gap-3">
                  <h2 className="text-sm font-semibold text-ink">{name}</h2>
                  <span className="text-[0.68rem] uppercase tracking-[0.14em] text-muted">
                    {tenantId}
                  </span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                  {members.map((p) => (
                    <button
                      key={p.user_id}
                      type="button"
                      disabled={submitting !== null}
                      onClick={() => void handleLogin(p.user_id)}
                      className="group text-left rounded-lg border border-line bg-[rgba(7,16,24,0.6)] p-3 hover:border-[rgba(120,180,255,0.4)] hover:bg-[rgba(17,26,36,0.9)] transition disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="text-sm font-semibold text-ink truncate">
                            {p.display_name}
                          </div>
                          <div className="text-xs text-muted truncate">{p.email}</div>
                        </div>
                        <span
                          className={`shrink-0 rounded border px-1.5 py-0.5 text-[0.6rem] font-semibold uppercase tracking-wider ${ROLE_ACCENT[p.role]}`}
                        >
                          {ROLE_LABELS[p.role]}
                        </span>
                      </div>
                      <div className="mt-2 text-xs text-muted">
                        {submitting === p.user_id ? "Signing in…" : "Sign in"}
                      </div>
                    </button>
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
