"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { CompletionBar } from "@/components/completion-bar";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { SkeletonCard } from "@/components/skeleton";
import { fetchBom, fetchProject, fetchProjects, fetchProjectsProgress } from "@/lib/api";
import { daysFromNow, formatDate } from "@/lib/format-date";
import { useAsync } from "@/lib/use-async";
import type { Milestone } from "@/lib/types";

function nextMilestone(ms: Milestone[]): Milestone | null {
  const future = ms
    .map((m) => ({ m, days: daysFromNow(m.required_on_site_date) }))
    .filter((x) => x.days !== null && x.days >= 0)
    .sort((a, b) => (a.days ?? 0) - (b.days ?? 0));
  if (future.length) return future[0].m;
  return ms.length ? ms[ms.length - 1] : null;
}

// Cheap memo so hover-prefetch fires at most once per project per session.
const _prefetched = new Set<string>();

export default function ProjectsPage() {
  const { data, loading, error } = useAsync(fetchProjects, []);
  const progress = useAsync(fetchProjectsProgress, []);
  const progressById = new Map(
    (progress.data ?? []).map((p) => [p.project_id, p]),
  );
  const router = useRouter();

  function prefetch(projectId: string) {
    if (_prefetched.has(projectId)) return;
    _prefetched.add(projectId);
    // Warm Next.js' route cache + warm the API caches in parallel.
    router.prefetch(`/projects/${encodeURIComponent(projectId)}`);
    void fetchProject(projectId);
    void fetchBom(projectId);
  }

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Plan"
        title="Projects"
        description="Engineering projects with their milestones and procurement plans. Open a project to see its BOM and generated plan."
      />

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : error ? (
        <div className="panel-sm border-[rgba(255,117,117,0.3)] text-[#ff9d9d]">{error}</div>
      ) : !data || data.length === 0 ? (
        <EmptyState title="No projects" hint="The backend returned an empty list." />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {data.map((p) => {
            const next = nextMilestone(p.milestones);
            const days = next ? daysFromNow(next.required_on_site_date) : null;
            return (
              <Link
                key={p.project_id}
                href={`/projects/${encodeURIComponent(p.project_id)}`}
                onMouseEnter={() => prefetch(p.project_id)}
                onFocus={() => prefetch(p.project_id)}
                className="panel hover:border-accent/50 hover:shadow-glow transition-all block animate-fade-up"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-[0.7rem] uppercase tracking-[0.14em] text-muted font-bold">
                      {p.project_id}
                    </div>
                    <h2 className="m-0 text-lg font-bold mt-1">{p.name}</h2>
                    <div className="text-sm text-muted mt-1">
                      {p.client} · {p.site}
                    </div>
                  </div>
                  <span className="chip">{p.sector}</span>
                </div>

                {progressById.has(p.project_id) ? (
                  <div className="mt-4">
                    <CompletionBar progress={progressById.get(p.project_id)!} />
                  </div>
                ) : null}

                <div className="grid grid-cols-3 gap-3 mt-5">
                  <Stat label="Milestones" value={String(p.milestones.length)} />
                  <Stat
                    label="Next Milestone"
                    value={next ? next.code : "—"}
                    hint={next ? next.name : undefined}
                  />
                  <Stat
                    label="In"
                    value={days !== null ? `${days}d` : "—"}
                    hint={next ? formatDate(next.required_on_site_date) : undefined}
                    tone={days !== null && days <= 14 ? "bad" : days !== null && days <= 45 ? "warn" : "neutral"}
                  />
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  hint,
  tone = "neutral",
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "neutral" | "good" | "warn" | "bad";
}) {
  const color = tone === "bad" ? "text-danger" : tone === "warn" ? "text-warning" : tone === "good" ? "text-accent" : "text-ink";
  return (
    <div>
      <div className="text-[0.65rem] uppercase tracking-[0.12em] text-muted font-bold">{label}</div>
      <div className={`font-bold ${color}`}>{value}</div>
      {hint ? <div className="text-xs text-muted truncate">{hint}</div> : null}
    </div>
  );
}
