"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { GROUP_LABEL, navGroups } from "@/lib/nav";

// Mobile / tablet navigation. The desktop sidebar is `hidden lg:flex`, so
// below 1024px there was no way to move between pages — this hamburger +
// slide-out drawer fills that gap. Hidden at lg+ where the sidebar takes over.
export function MobileNav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  // Close on navigation + lock body scroll while open.
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const groups = navGroups();

  return (
    <div className="lg:hidden">
      <button
        onClick={() => setOpen(true)}
        aria-label="Open navigation"
        className="flex items-center justify-center w-9 h-9 rounded-lg border border-line bg-white/[0.02] hover:bg-white/[0.05] transition-colors"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-ink/80">
          <line x1="3" y1="6" x2="21" y2="6" />
          <line x1="3" y1="12" x2="21" y2="12" />
          <line x1="3" y1="18" x2="21" y2="18" />
        </svg>
      </button>

      {open ? (
        <div className="fixed inset-0 z-[95]" role="dialog" aria-modal="true">
          <div className="absolute inset-0 bg-black/55 backdrop-blur-sm" onClick={() => setOpen(false)} />
          <aside className="absolute left-0 top-0 h-full w-[78vw] max-w-[300px] bg-surface border-r border-line shadow-panel flex flex-col animate-[slide-in-left_0.22s_ease-out]">
            <div className="px-5 py-5 border-b border-line flex items-center justify-between">
              <div>
                <div className="text-[0.68rem] tracking-[0.2em] uppercase text-accent font-bold">
                  Control Tower
                </div>
                <div className="text-ink font-bold mt-1 leading-tight text-sm">Supply Chain</div>
              </div>
              <button onClick={() => setOpen(false)} aria-label="Close navigation" className="text-muted hover:text-ink text-lg">
                ✕
              </button>
            </div>

            <nav className="flex-1 overflow-y-auto py-4">
              {groups.map(({ group, items }) => (
                <div key={group} className="px-3 pb-4">
                  <div className="px-2 pb-2 text-[0.65rem] uppercase tracking-[0.16em] text-muted font-bold">
                    {GROUP_LABEL[group]}
                  </div>
                  <ul className="space-y-1">
                    {items.map((item) => {
                      const active = pathname === item.href || pathname.startsWith(item.href + "/");
                      return (
                        <li key={item.href}>
                          <Link
                            href={item.href}
                            className={[
                              "block rounded-xl px-3 py-2.5 text-sm transition-colors",
                              active
                                ? "bg-[rgba(87,212,192,0.12)] text-accent font-semibold"
                                : "text-ink/85 hover:bg-white/5",
                            ].join(" ")}
                          >
                            {item.label}
                          </Link>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ))}
            </nav>
          </aside>
        </div>
      ) : null}
    </div>
  );
}
