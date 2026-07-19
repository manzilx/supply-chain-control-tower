"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { GROUP_LABEL, navGroups } from "@/lib/nav";

export function Sidebar() {
  const pathname = usePathname();

  const groups = navGroups();

  return (
    <aside className="hidden lg:flex flex-col w-60 shrink-0 border-r border-line bg-[rgba(7,16,24,0.6)] backdrop-blur-lg">
      <div className="px-5 py-5 border-b border-line">
        <div className="text-[0.68rem] tracking-[0.2em] uppercase text-accent font-bold">
          Control Tower
        </div>
        <div className="text-ink font-bold mt-1 leading-tight">
          Supply Chain<br />
          <span className="text-muted font-normal text-sm">Engineering Procurement</span>
        </div>
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
                        "block rounded-xl px-3 py-2 text-sm transition-colors",
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

      <div className="px-5 py-4 border-t border-line text-xs text-muted">
        v0.1 · M1 shell
      </div>
    </aside>
  );
}
