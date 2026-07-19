import Link from "next/link";

// Branded 404 for unmatched routes and dead entity links (e.g. a bookmarked
// PR that was never re-seeded). Replaces Next's bare default so a stale URL
// degrades into a useful jumping-off point instead of looking broken.
const QUICK_LINKS = [
  { href: "/overview", label: "Overview" },
  { href: "/projects", label: "Projects" },
  { href: "/sourcing", label: "Sourcing" },
  { href: "/vendors", label: "Vendors" },
  { href: "/approvals", label: "Approvals" },
  { href: "/commercial", label: "Commercial" },
];

export default function NotFound() {
  return (
    <div className="flex items-center justify-center min-h-[60vh] p-6">
      <div className="panel max-w-md w-full text-center">
        <div className="text-[0.65rem] uppercase tracking-[0.14em] text-accent font-bold">
          404
        </div>
        <h2 className="m-0 text-2xl font-bold mt-1">Page not found</h2>
        <p className="text-sm text-muted mt-2">
          That route doesn&rsquo;t exist — or the record it pointed to is no longer here.
          Jump back into the control tower:
        </p>
        <div className="grid grid-cols-2 gap-2 mt-5">
          {QUICK_LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className="panel-sm hover:border-accent/50 transition-colors text-sm text-ink"
            >
              {l.label}
            </Link>
          ))}
        </div>
        <p className="text-[0.65rem] text-muted mt-5">
          Tip: press <kbd className="border border-line rounded px-1 py-0.5 font-mono">⌘K</kbd> anywhere to search.
        </p>
      </div>
    </div>
  );
}
