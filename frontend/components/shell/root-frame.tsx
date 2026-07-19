"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { StoreProvider } from "@/lib/store-context";
import { useAuth } from "@/lib/auth-context";
import { Shell } from "./shell";

/**
 * Gates the authed shell on login state.
 *
 * - /login: rendered bare, no Shell, no StoreProvider. Anyone can see it.
 * - Anonymous elsewhere → redirect to /login.
 * - Authed on /login → redirect to /overview (back to work).
 * - Authed elsewhere → mount StoreProvider + Shell as before.
 *
 * StoreProvider only mounts once authed, so its bootstrap calls never fire
 * against protected routes without a token.
 */
export function RootFrame({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { status } = useAuth();

  const isLoginRoute = pathname === "/login";

  useEffect(() => {
    if (status === "anonymous" && !isLoginRoute) {
      router.replace("/login");
    } else if (status === "authed" && isLoginRoute) {
      router.replace("/overview");
    }
  }, [status, isLoginRoute, router]);

  if (isLoginRoute) {
    return <>{children}</>;
  }

  if (status === "bootstrapping" || status === "anonymous") {
    return (
      <div className="min-h-screen flex items-center justify-center text-muted text-sm">
        Loading…
      </div>
    );
  }

  return (
    <StoreProvider>
      <Shell>{children}</Shell>
    </StoreProvider>
  );
}
