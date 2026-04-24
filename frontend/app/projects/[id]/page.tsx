"use client";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { ProjectTabs } from "@/components/project-tabs";
import { fetchProject } from "@/lib/api";
import { daysFromNow, formatDate } from "@/lib/format-date";
import { useAsync } from "@/lib/use-async";

const PHASE_TONE: Record<string, string> = {
  engineering: "severity-low",
  procurement: "severity-medium",
  fabrication: "severity-medium",
  delivery: "severity-high",
  installation: "severity-high",
  commissioning: "severity-critical",
};

export default function ProjectDetailPage({ params }: { params: { id: string } }) {
  const { data, loading, error } = useAsync(() => fetchProject(params.id), [params.id]);

  return (
    <div className="space-y-5">
      {loading ? (
        <EmptyState title="Loading project..." />
      ) : error ? (
        <div className="panel-sm border-[rgba(255,117,117,0.3)] text-[#ff9d9d]">{error}</div>
      ) : !data ? (
        <EmptyState title="Project not found" />
      ) : (
        <>
          <PageHeader
            eyebrow={data.project_id}
            title={data.name}
            description={`${data.client} · ${data.site} · started ${formatDate(data.start_date)}`}
          />
          <ProjectTabs projectId={data.project_id} />

          <section className="panel">
            <h2 className="m-0 text-lg font-bold mb-4">Milestones</h2>
            {data.milestones.length === 0 ? (
              <EmptyState title="No milestones" />
            ) : (
              <ol className="space-y-3">
                {data.milestones.map((m, idx) => {
                  const days = daysFromNow(m.required_on_site_date);
                  const past = days !== null && days < 0;
                  return (
                    <li key={m.code} className="flex items-start gap-3">
                      <div className="flex flex-col items-center pt-1">
                        <div
                          className={[
                            "w-6 h-6 rounded-full border-2 flex items-center justify-center text-xs font-bold",
                            past
                              ? "bg-accent border-accent text-bg"
                              : "bg-bg border-accent text-accent",
                          ].join(" ")}
                        >
                          {idx + 1}
                        </div>
                        {idx < data.milestones.length - 1 ? (
                          <div className="w-px flex-1 bg-line mt-1 min-h-[24px]" />
                        ) : null}
                      </div>
                      <div className="flex-1 min-w-0 pb-3">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-bold text-ink">{m.code}</span>
                          <span className="text-ink">{m.name}</span>
                          <span className={`badge ${PHASE_TONE[m.phase] ?? "severity-low"}`}>
                            {m.phase}
                          </span>
                        </div>
                        <div className="text-sm text-muted mt-1">
                          Required on site: {formatDate(m.required_on_site_date)}
                          {days !== null ? (
                            <span className={days < 14 && days >= 0 ? " text-warning font-semibold" : ""}>
                              {" · "}
                              {past ? `${Math.abs(days)}d ago` : `in ${days}d`}
                            </span>
                          ) : null}
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ol>
            )}
          </section>
        </>
      )}
    </div>
  );
}
