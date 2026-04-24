"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type Props = {
  projectId: string;
};

export function ProjectTabs({ projectId }: Props) {
  const pathname = usePathname();
  const base = `/projects/${encodeURIComponent(projectId)}`;
  const tabs = [
    { href: base, label: "Overview" },
    { href: `${base}/bom`, label: "BOM" },
    { href: `${base}/plan`, label: "Procurement Plan" },
  ];

  return (
    <nav className="flex gap-1 border-b border-line -mb-px">
      {tabs.map((t) => {
        const active = pathname === t.href;
        return (
          <Link
            key={t.href}
            href={t.href}
            className={[
              "px-4 py-2 text-sm font-semibold border-b-2 transition-colors",
              active
                ? "border-accent text-accent"
                : "border-transparent text-muted hover:text-ink",
            ].join(" ")}
          >
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}
