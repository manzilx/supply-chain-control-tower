"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { KpiTile } from "@/components/kpi-tile";
import { PageHeader } from "@/components/page-header";
import { ProjectTabs } from "@/components/project-tabs";
import {
  createProjectRisk,
  fetchProcessMap,
  fetchRiskMitigations,
  patchProjectRisk,
} from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useAsync } from "@/lib/use-async";
import type {
  CreateManagedRiskRequest,
  ManagedRisk,
  ManagedRiskStatus,
  ProcessStageBucket,
  ProcessStageName,
  Severity,
} from "@/lib/types";

const SEV_CHIP: Record<Severity, string> = {
  critical: "severity-critical",
  high: "severity-high",
  medium: "severity-medium",
  low: "severity-low",
};

const STATUSES: ManagedRiskStatus[] = ["open", "mitigating", "accepted", "closed"];
const SEVERITIES: Severity[] = ["critical", "high", "medium", "low"];
const STAGES: ProcessStageName[] = [
  "spec", "pr", "rfq", "quotes", "technical_eval", "award", "po", "shipment", "site_grn", "delivery",
];

const SCORE: Record<Severity, number> = { low: 30, medium: 55, high: 78, critical: 92 };

export default function ProcessPage({ params }: { params: { id: string } }) {
  const { hasPerm } = useAuth();
  const canUpdate = hasPerm("risk", "update");
  const map = useAsync(() => fetchProcessMap(params.id), [params.id]);
  const [stage, setStage] = useState<ProcessStageName | null>(null);
  const [statusFilter, setStatusFilter] = useState<ManagedRiskStatus | "all">("all");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [suggesting, setSuggesting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const data = map.data;
  const selected: ProcessStageBucket | undefined = data?.stages.find(
    (s) => s.stage === (stage ?? data.stages.find((x) => x.current)?.stage),
  );

  const risks = useMemo(() => {
    const all = data?.risks ?? [];
    return all.filter((r) => statusFilter === "all" || r.status === statusFilter);
  }, [data, statusFilter]);

  async function patch(risk: ManagedRisk, body: { status?: ManagedRiskStatus; owner?: string; mitigation?: string }) {
    setBusyId(risk.risk_id);
    setError(null);
    try {
      await patchProjectRisk(params.id, risk.risk_id, body);
      map.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not update risk");
    } finally {
      setBusyId(null);
    }
  }

  async function suggest(risk: ManagedRisk) {
    setSuggesting(risk.risk_id);
    setError(null);
    try {
      const reply = await fetchRiskMitigations({
        title: risk.title,
        risk_type: risk.category,
        severity: risk.severity,
        score: SCORE[risk.severity],
        summary: risk.detail,
        owner: risk.owner || "Procurement",
      });
      const text = reply.mitigations.join("\n");
      await patchProjectRisk(params.id, risk.risk_id, { mitigation: text });
      map.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not suggest mitigations");
    } finally {
      setSuggesting(null);
    }
  }

  async function addManual(req: CreateManagedRiskRequest) {
    setError(null);
    try {
      await createProjectRisk(params.id, req);
      map.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create risk");
      throw e;
    }
  }

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={params.id}
        title={data?.project_name ?? "SCM Process"}
        description="Live BOM→delivery map for this project. Risks are seeded from current signals; status and owner stick across refreshes."
      />
      <ProjectTabs projectId={params.id} />

      {map.loading ? (
        <EmptyState title="Building process map..." />
      ) : map.error ? (
        <div className="panel-sm border-[rgba(255,117,117,0.3)] text-[#ff9d9d]">{map.error}</div>
      ) : !data ? (
        <EmptyState title="No process map" />
      ) : (
        <>
          <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KpiTile label="BOM Lines" value={String(data.bom_total)} />
            <KpiTile label="Blocked" value={String(data.blocked_total)} tone={data.blocked_total ? "bad" : "good"} />
            <KpiTile label="At Risk" value={String(data.at_risk_total)} tone={data.at_risk_total ? "warn" : "neutral"} />
            <KpiTile label="Open Risks" value={String(data.open_risks)} tone={data.open_risks ? "warn" : "good"} />
          </section>

          {data.bottlenecks.length ? (
            <div className="flex flex-wrap gap-2">
              {data.bottlenecks.map((b) => (
                <button
                  key={b.stage}
                  type="button"
                  className="badge severity-high"
                  onClick={() => setStage(b.stage)}
                >
                  {b.reason}
                </button>
              ))}
            </div>
          ) : null}

          <section className="panel">
            <h2 className="m-0 text-lg font-bold mb-4">Pipeline</h2>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
              {data.stages.map((s) => {
                const active = selected?.stage === s.stage;
                return (
                  <button
                    key={s.stage}
                    type="button"
                    onClick={() => setStage(s.stage)}
                    className={["panel-sm text-left transition-colors", active ? "border-accent" : ""].join(" ")}
                  >
                    <div className="text-[0.65rem] uppercase tracking-[0.12em] text-muted font-bold">
                      {s.label}
                    </div>
                    <div className="text-2xl font-extrabold text-ink mt-1">{s.current}</div>
                    <div className="text-xs text-muted mt-1">
                      {s.done} past
                      {s.blocked ? ` · ${s.blocked} blocked` : ""}
                      {s.at_risk ? ` · ${s.at_risk} at risk` : ""}
                    </div>
                  </button>
                );
              })}
            </div>
          </section>

          <section className="panel">
            <h2 className="m-0 text-lg font-bold mb-3">
              {selected ? `${selected.label} · ${selected.current} current` : "Stage items"}
            </h2>
            {!selected || selected.items.length === 0 ? (
              <EmptyState title="No lines in this stage" />
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Item</th>
                    <th>Status</th>
                    <th>Flags</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {selected.items.map((item) => (
                    <tr key={item.bom_item_id}>
                      <td>
                        <div className="font-semibold">{item.code}</div>
                        <div className="text-xs text-muted">{item.description}</div>
                      </td>
                      <td className="text-muted text-sm">{item.status ?? "—"}</td>
                      <td>
                        {item.blocked ? <span className="badge severity-high">blocked</span> : null}
                        {item.at_risk ? <span className="badge severity-medium ml-1">at risk</span> : null}
                      </td>
                      <td>
                        <Link href={item.href} className="text-[0.62rem] uppercase tracking-[0.1em] font-bold text-accent">
                          Open
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          <RiskRegister
            projectId={params.id}
            risks={risks}
            allCount={data.risks.length}
            statusFilter={statusFilter}
            onStatusFilter={setStatusFilter}
            canUpdate={canUpdate}
            busyId={busyId}
            suggesting={suggesting}
            error={error}
            onPatch={patch}
            onSuggest={suggest}
            onCreate={canUpdate ? addManual : undefined}
          />
        </>
      )}
    </div>
  );
}

function RiskRegister({
  projectId,
  risks,
  allCount,
  statusFilter,
  onStatusFilter,
  canUpdate,
  busyId,
  suggesting,
  error,
  onPatch,
  onSuggest,
  onCreate,
}: {
  projectId: string;
  risks: ManagedRisk[];
  allCount: number;
  statusFilter: ManagedRiskStatus | "all";
  onStatusFilter: (s: ManagedRiskStatus | "all") => void;
  canUpdate: boolean;
  busyId: string | null;
  suggesting: string | null;
  error: string | null;
  onPatch: (risk: ManagedRisk, body: { status?: ManagedRiskStatus; owner?: string; mitigation?: string }) => Promise<void>;
  onSuggest: (risk: ManagedRisk) => Promise<void>;
  onCreate?: (req: CreateManagedRiskRequest) => Promise<void>;
}) {
  const [title, setTitle] = useState("");
  const [detail, setDetail] = useState("");
  const [severity, setSeverity] = useState<Severity>("medium");
  const [stage, setStage] = useState<ProcessStageName | "">("");
  const [saving, setSaving] = useState(false);

  return (
    <section className="panel space-y-3">
      <div className="flex items-baseline justify-between flex-wrap gap-2">
        <h2 className="m-0 text-lg font-bold">Risk register</h2>
        <label className="flex items-center gap-2 text-xs text-muted">
          Status
          <select
            value={statusFilter}
            onChange={(e) => onStatusFilter(e.target.value as ManagedRiskStatus | "all")}
            className="w-auto"
          >
            <option value="all">All</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>
      </div>
      {error ? <div className="text-sm text-[#ff9d9d]">{error}</div> : null}
      {risks.length === 0 ? (
        <EmptyState title={allCount ? "No risks match this status" : "No risks yet"} />
      ) : (
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Risk</th>
                <th>Stage</th>
                <th>Severity</th>
                <th>Status</th>
                <th>Owner</th>
                <th>Mitigation</th>
              </tr>
            </thead>
            <tbody>
              {risks.map((r) => (
                <tr key={`${r.risk_id}-${r.updated_at}`}>
                  <td>
                    {r.href ? (
                      <Link href={r.href} className="font-semibold hover:text-accent">{r.title}</Link>
                    ) : (
                      <div className="font-semibold">{r.title}</div>
                    )}
                    <div className="text-xs text-muted mt-1 max-w-md">{r.detail}</div>
                    <div className="text-[0.62rem] uppercase tracking-[0.1em] text-muted mt-1">
                      {r.category}
                      {r.source === "live" && !r.live ? " · signal gone" : ""}
                      {r.source === "manual" ? " · manual" : ""}
                    </div>
                  </td>
                  <td className="text-muted text-sm">{r.process_stage ?? "—"}</td>
                  <td>
                    <span className={`badge ${SEV_CHIP[r.severity]}`}>{r.severity}</span>
                  </td>
                  <td>
                    {canUpdate ? (
                      <select
                        value={r.status}
                        disabled={busyId === r.risk_id}
                        onChange={(e) => void onPatch(r, { status: e.target.value as ManagedRiskStatus })}
                        className="w-auto min-w-[8rem]"
                      >
                        {STATUSES.map((s) => (
                          <option key={s} value={s}>{s}</option>
                        ))}
                      </select>
                    ) : (
                      <span className="text-sm capitalize">{r.status}</span>
                    )}
                  </td>
                  <td>
                    {canUpdate ? (
                      <input
                        defaultValue={r.owner}
                        disabled={busyId === r.risk_id}
                        onBlur={(e) => {
                          const v = e.target.value;
                          if (v !== r.owner) void onPatch(r, { owner: v });
                        }}
                        placeholder="Owner"
                      />
                    ) : (
                      <span className="text-sm">{r.owner || "—"}</span>
                    )}
                  </td>
                  <td className="min-w-[16rem]">
                    {canUpdate ? (
                      <div className="space-y-2">
                        <textarea
                          defaultValue={r.mitigation}
                          rows={2}
                          disabled={busyId === r.risk_id}
                          onBlur={(e) => {
                            const v = e.target.value;
                            if (v !== r.mitigation) void onPatch(r, { mitigation: v });
                          }}
                          placeholder="Mitigation"
                        />
                        <button
                          type="button"
                          className="btn btn-secondary text-xs py-1"
                          disabled={suggesting === r.risk_id}
                          onClick={() => void onSuggest(r)}
                        >
                          {suggesting === r.risk_id ? "Suggesting…" : "Suggest mitigation"}
                        </button>
                      </div>
                    ) : (
                      <div className="text-sm text-muted whitespace-pre-wrap">{r.mitigation || "—"}</div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {onCreate ? (
        <form
          className="panel-sm grid grid-cols-1 md:grid-cols-2 gap-3"
          onSubmit={async (e) => {
            e.preventDefault();
            if (!title.trim()) return;
            setSaving(true);
            try {
              await onCreate({
                title: title.trim(),
                detail: detail.trim(),
                severity,
                process_stage: stage || null,
                category: "process",
              });
              setTitle("");
              setDetail("");
            } finally {
              setSaving(false);
            }
          }}
        >
          <div className="md:col-span-2 text-[0.68rem] uppercase tracking-[0.12em] text-muted font-bold">
            Add risk · {projectId}
          </div>
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title" required />
          <input value={detail} onChange={(e) => setDetail(e.target.value)} placeholder="Detail" />
          <select value={severity} onChange={(e) => setSeverity(e.target.value as Severity)}>
            {SEVERITIES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <select value={stage} onChange={(e) => setStage(e.target.value as ProcessStageName | "")}>
            <option value="">No stage</option>
            {STAGES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <div className="md:col-span-2">
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? "Adding…" : "Add risk"}
            </button>
          </div>
        </form>
      ) : null}
    </section>
  );
}
