"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { fetchSearchIndex } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { NAV } from "@/lib/nav";
import type { SearchIndex, SearchIndexItem, SearchKind } from "@/lib/types";

const KIND_LABEL: Record<SearchKind | "page", string> = {
  page: "Page",
  project: "Project",
  bom: "BOM",
  vendor: "Vendor",
  pr: "PR",
  po: "PO",
};

const KIND_TONE: Record<SearchKind | "page", string> = {
  page: "text-accent",
  project: "text-accent",
  bom: "text-warning",
  vendor: "text-steady",
  pr: "text-ink",
  po: "text-ink",
};

type PaletteItem = {
  kind: SearchKind | "page";
  href: string;
  title: string;
  subtitle?: string;
  id: string;
};

function scoreEntity(item: SearchIndexItem, q: string): number {
  if (!q) return 0;
  const hay = [item.title, item.subtitle ?? "", ...item.tags, item.id].join(" ").toLowerCase();
  const needle = q.toLowerCase();
  const t = item.title.toLowerCase();
  if (t.startsWith(needle)) return 100;
  if (t.includes(needle)) return 80;
  if ((item.subtitle ?? "").toLowerCase().includes(needle)) return 60;
  if (hay.includes(needle)) return 40;
  return 0;
}

function scorePage(label: string, href: string, q: string): number {
  if (!q) return 0;
  const hay = `${label} ${href}`.toLowerCase();
  const needle = q.toLowerCase();
  const t = label.toLowerCase();
  if (t.startsWith(needle)) return 95;
  if (t.includes(needle)) return 75;
  if (hay.includes(needle)) return 35;
  return 0;
}

function toEntity(item: SearchIndexItem): PaletteItem {
  return {
    kind: item.kind,
    href: item.href,
    title: item.title,
    subtitle: item.subtitle ?? undefined,
    id: item.id,
  };
}

function toPage(item: (typeof NAV)[number]): PaletteItem {
  return {
    kind: "page",
    href: item.href,
    title: item.label,
    id: item.href,
  };
}

export function CommandPalette() {
  const { status } = useAuth();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);
  const [index, setIndex] = useState<SearchIndex | null>(null);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Global hotkey: Cmd/Ctrl + K
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      } else if (e.key === "Escape" && open) {
        setOpen(false);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  // Lazy-load + refresh index when opening
  useEffect(() => {
    if (!open || status !== "authed") return;
    setLoading(true);
    fetchSearchIndex()
      .then((idx) => setIndex(idx))
      .catch(() => setIndex(null))
      .finally(() => setLoading(false));
    setTimeout(() => inputRef.current?.focus(), 30);
  }, [open, status]);

  // Reset selection when query changes
  useEffect(() => setSelected(0), [query]);

  const results = useMemo((): PaletteItem[] => {
    const q = query.trim();
    const pages = NAV.map(toPage);

    if (!index) {
      return q ? pages.filter((p) => scorePage(p.title, p.href, q) > 0).slice(0, 8) : pages;
    }

    const items = index.items;
    if (!q) {
      const grouped: SearchIndexItem[] = [];
      for (const kind of ["project", "pr", "vendor", "bom", "po"] as SearchKind[]) {
        const first = items.filter((i) => i.kind === kind).slice(0, kind === "project" ? 5 : 3);
        grouped.push(...first);
      }
      return [...pages, ...grouped.slice(0, 8).map(toEntity)];
    }

    const scoredPages = pages
      .map((p) => ({ p, s: scorePage(p.title, p.href, q) }))
      .filter((x) => x.s > 0);
    const scoredEntities = items
      .map((i) => ({ i, s: scoreEntity(i, q) }))
      .filter((x) => x.s > 0);

    return [...scoredPages, ...scoredEntities]
      .sort((a, b) => b.s - a.s)
      .slice(0, 20)
      .map((x) => ("p" in x ? x.p : toEntity(x.i)));
  }, [index, query]);

  // Keyboard navigation
  useEffect(() => {
    if (!open) return;
    function onNav(e: KeyboardEvent) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelected((s) => Math.min(results.length - 1, s + 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelected((s) => Math.max(0, s - 1));
      } else if (e.key === "Enter" && results[selected]) {
        e.preventDefault();
        router.push(results[selected].href);
        setOpen(false);
        setQuery("");
      }
    }
    window.addEventListener("keydown", onNav);
    return () => window.removeEventListener("keydown", onNav);
  }, [open, results, selected, router]);

  if (status !== "authed") return null;
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center pt-[8vh] bg-black/55 backdrop-blur-sm animate-fade-up"
      onClick={() => setOpen(false)}
    >
      <div
        className="w-[min(640px,92vw)] panel p-0 overflow-hidden shadow-glow"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 px-4 py-3 border-b border-line">
          <span className="text-muted text-sm">⌘K</span>
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search pages, projects, BOM, vendors, PRs, POs…"
            className="flex-1 bg-transparent outline-none text-ink placeholder:text-muted text-base"
          />
          <button
            onClick={() => setOpen(false)}
            className="text-[0.65rem] uppercase tracking-[0.1em] text-muted hover:text-ink"
          >
            Esc
          </button>
        </div>

        <div className="max-h-[60vh] overflow-y-auto">
          {loading && !index ? (
            <div className="px-4 py-10 text-center text-muted text-sm">Loading index…</div>
          ) : results.length === 0 ? (
            <div className="px-4 py-10 text-center text-muted text-sm">
              {query ? `No matches for "${query}"` : "Empty index"}
            </div>
          ) : (
            <ul className="py-2">
              {results.map((item, i) => {
                const showSection =
                  !query.trim() &&
                  item.kind === "page" &&
                  (i === 0 || results[i - 1]?.kind !== "page");
                const showEntitiesHeader =
                  !query.trim() &&
                  item.kind !== "page" &&
                  results[i - 1]?.kind === "page";

                return (
                  <li key={`${item.kind}-${item.id}`}>
                    {showSection ? (
                      <div className="px-4 pt-2 pb-1 text-[0.6rem] uppercase tracking-[0.12em] font-bold text-muted">
                        Pages
                      </div>
                    ) : null}
                    {showEntitiesHeader ? (
                      <div className="px-4 pt-3 pb-1 text-[0.6rem] uppercase tracking-[0.12em] font-bold text-muted">
                        Entities
                      </div>
                    ) : null}
                    <div
                      className={[
                        "px-4 py-2.5 cursor-pointer flex items-start gap-3",
                        i === selected ? "bg-white/[0.05]" : "hover:bg-white/[0.03]",
                      ].join(" ")}
                      onMouseEnter={() => setSelected(i)}
                      onClick={() => {
                        router.push(item.href);
                        setOpen(false);
                        setQuery("");
                      }}
                    >
                      <span
                        className={`shrink-0 w-14 text-[0.6rem] uppercase tracking-[0.12em] font-bold ${KIND_TONE[item.kind]}`}
                      >
                        {KIND_LABEL[item.kind]}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="text-sm text-ink truncate">{item.title}</div>
                        {item.subtitle ? (
                          <div className="text-xs text-muted truncate">{item.subtitle}</div>
                        ) : null}
                      </div>
                      {i === selected ? (
                        <span className="text-[0.65rem] uppercase tracking-[0.1em] text-muted">↵</span>
                      ) : null}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div className="px-4 py-2 border-t border-line text-[0.65rem] text-muted flex justify-between">
          <span>↑↓ navigate · ↵ open · esc close</span>
          {index ? <span>{index.items.length} indexed</span> : null}
        </div>
      </div>
    </div>
  );
}
