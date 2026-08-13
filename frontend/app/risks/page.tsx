"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { Donut, MotionPanel, SEVERITY_COLOR, VBar } from "@/components/charts";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { SkeletonCard } from "@/components/skeleton";
import {
  fetchAlerts,
  fetchRiskMitigations,
  fetchRiskRegister,
  patchProjectRisk,
} from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useAsync } from "@/lib/use-async";
import type {
  Alert,
  AlertSeverity,
  ManagedRisk,
  ManagedRiskStatus,
  Severity,
} from "@/lib/types";

const SEVERITIES: AlertSeverity[] = ["critical", "high", "medium", "low", "info"];
const RISK_SEVERITIES: Severity[] = ["critical", "high", "medium", "low"];
const STATUSES: ManagedRiskStatus[] = ["open", "mitigating", "accepted", "closed"];

const SEV_CHIP: Record<AlertSeverity, string> = {
  critical: "severity-critical",
  high: "severity-high",
  medium: "severity-medium",
  low: "severity-low",
  info: "severity-low",
};

const SEVERITY_RANK: Record<AlertSeverity, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  info: 4,
};

const KNOWN_CATEGORIES = [
  "approval",
  "schedule",
  "vendor",
  "commercial",
  "expediting",
  "engineering",
] as const;

const SCORE: Record<Severity, number> = { low: 30, medium: 55, high: 78, critical: 92 };

type Tab = "register" | "alerts";

export default function RisksPage() {
  const [tab, setTab] = useState<Tab>("register");

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Risks"
        title="Risk Register"
        description="Managed risks seeded from live SCM process signals, plus the tenant alert feed. Status, owner, and mitigation persist across refreshes."
      />

      <nav className="flex gap-1 border-b border-line -mb-px">
        {(
          [
            { id: "register", label: "Register" },
            { id: "alerts", label: "Alerts" },
          ] as const
        ).map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={[
              "px-4 py-2 text-sm font-semibold border-b-2 transition-colors bg-transparent",
              tab === t.id
                ? "border-accent text-accent"
                : "border-transparent text-muted hover:text-ink",
            ].join(" ")}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {tab === "register" ? <RegisterPanel /> : <AlertsPanel />}
    </div>
  );
}

function RegisterPanel() {
  const { hasPerm } = useAuth();
  const canUpdate = hasPerm("risk", "update");
  const feed = useAsync(fetchRiskRegister, []);
  const risks = feed.data ?? [];

  const [project, setProject] = useState<string>("all");
  const [status, setStatus] = useState<ManagedRiskStatus | "all">("all");
  const [severity, setSeverity] = useState<Severity | "all">("all");
  const [query, setQuery] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [suggesting, setSuggesting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const projects = useMemo(() => {
    const ids = Array.from(new Set(risks.map((r) => r.project_id))).sort();
    return ids;
  }, [risks]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return risks.filter(
      (r) =>
        (project === "all" || r.project_id === project) &&
        (status === "all" || r.status === status) &&
        (severity === "all" || r.severity === severity) &&
        (!q ||
          r.title.toLowerCase().includes(q) ||
          r.detail.toLowerCase().includes(q) ||
          r.project_id.toLowerCase().includes(q) ||
          r.category.toLowerCase().includes(q)),
    );
  }, [risks, project, status, severity, query]);

  const openCount = risks.filter((r) => r.status === "open" || r.status === "mitigating").length;
  const liveCount = risks.filter((r) => r.live).length;

  async function patch(risk: ManagedRisk, body: { status?: ManagedRiskStatus; owner?: string; mitigation?: string }) {
    setBusyId(risk.risk_id);
    setError(null);
    try {
      await patchProjectRisk(risk.project_id, risk.risk_id, body);
      feed.reload();
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
      await patchProjectRisk(risk.project_id, risk.risk_id, {
        mitigation: reply.mitigations.join("\n"),
      });
      feed.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not suggest mitigations");
    } finally {
      setSuggesting(null);
    }
  }

  if (feed.loading) {
    return (
      <div className="space-y-3">
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }
  if (feed.error) {
    return (
      <div className="panel-sm border-[rgba(255,117,117,0.3)] text-[#ff9d9d] space-y-3">
        <div>{feed.error}</div>
        <button type="button" onClick={feed.reload} className="btn btn-secondary text-xs">
          Retry
        </button>
      </div>
    );
  }

  return (
    <>
      <div className="flex flex-wrap gap-2">
        <span className="badge severity-high">{openCount} open</span>
        <span className="badge severity-medium">{liveCount} live signals</span>
        <span className="badge severity-low">{risks.length} total</span>
      </div>

      {error ? <div className="text-sm text-[#ff9d9d]">{error}</div> : null}

      <div className="panel-sm flex flex-wrap gap-3 items-end">
        <FilterGroup label="Project">
          <select value={project} onChange={(e) => setProject(e.target.value)}>
            <option value="all">All projects</option>
            {projects.map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>
        </FilterGroup>
        <FilterGroup label="Status">
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value as ManagedRiskStatus | "all")}
          >
            <option value="all">All statuses</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </FilterGroup>
        <FilterGroup label="Severity">
          <select
            value={severity}
            onChange={(e) => setSeverity(e.target.value as Severity | "all")}
          >
            <option value="all">All severities</option>
            {RISK_SEVERITIES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </FilterGroup>
        <FilterGroup label="Search" grow>
          <input
            placeholder="Filter by title, project, or category..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </FilterGroup>
        <div className="text-xs text-muted pb-2">
          {filtered.length} of {risks.length}
        </div>
      </div>

      <div className="panel overflow-x-auto p-0">
        {filtered.length ? (
          <table className="data-table">
            <thead>
              <tr>
                <th>Risk</th>
                <th>Project</th>
                <th>Stage</th>
                <th>Severity</th>
                <th>Status</th>
                <th>Owner</th>
                <th>Mitigation</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr key={`${r.risk_id}-${r.updated_at}`}>
                  <td>
                    {r.href ? (
                      <Link href={r.href} className="font-semibold hover:text-accent">
                        {r.title}
                      </Link>
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
                  <td>
                    <Link
                      href={`/projects/${encodeURIComponent(r.project_id)}/process`}
                      className="text-sm font-semibold hover:text-accent"
                    >
                      {r.project_id}
                    </Link>
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
                        onChange={(e) => void patch(r, { status: e.target.value as ManagedRiskStatus })}
                        className="w-auto min-w-[8rem]"
                      >
                        {STATUSES.map((s) => (
                          <option key={s} value={s}>
                            {s}
                          </option>
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
                          if (v !== r.owner) void patch(r, { owner: v });
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
                            if (v !== r.mitigation) void patch(r, { mitigation: v });
                          }}
                          placeholder="Mitigation"
                        />
                        <button
                          type="button"
                          className="btn btn-secondary text-xs py-1"
                          disabled={suggesting === r.risk_id}
                          onClick={() => void suggest(r)}
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
        ) : (
          <div className="p-6">
            <EmptyState
              title={risks.length ? "No risks match filters" : "No managed risks yet"}
              hint={
                risks.length
                  ? "Adjust the filters above to see more."
                  : "Open a project Process tab to seed live signals, or add a risk there."
              }
            />
          </div>
        )}
      </div>
    </>
  );
}

function AlertsPanel() {
  const { data, loading, error, reload } = useAsync(fetchAlerts, []);
  const alerts = data?.alerts ?? [];

  const [severity, setSeverity] = useState<AlertSeverity | "all">("all");
  const [category, setCategory] = useState<string>("all");
  const [query, setQuery] = useState("");

  const categories = useMemo(() => {
    const s = new Set<string>(KNOWN_CATEGORIES);
    alerts.forEach((a) => s.add(a.category));
    return Array.from(s).sort();
  }, [alerts]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return alerts
      .filter((a) => severity === "all" || a.severity === severity)
      .filter((a) => category === "all" || a.category === category)
      .filter(
        (a) =>
          !q ||
          a.title.toLowerCase().includes(q) ||
          a.detail.toLowerCase().includes(q) ||
          a.category.toLowerCase().includes(q),
      )
      .sort(
        (a, b) =>
          SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity] ||
          a.title.localeCompare(b.title),
      );
  }, [alerts, severity, category, query]);

  const byCategory = alerts.reduce((acc: Record<string, number>, a) => {
    acc[a.category] = (acc[a.category] || 0) + 1;
    return acc;
  }, {});

  const bySev = alerts.reduce((acc: Record<string, number>, a) => {
    const key = a.severity === "info" ? "low" : a.severity;
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});

  const sevByCategory: Record<string, Record<string, number>> = {};
  alerts.forEach((a) => {
    sevByCategory[a.category] = sevByCategory[a.category] || {};
    const key = a.severity === "info" ? "low" : a.severity;
    sevByCategory[a.category][key] = (sevByCategory[a.category][key] || 0) + 1;
  });

  const stackData = Object.entries(sevByCategory).map(([cat, m]) => ({
    name: cat.replace(/_/g, " "),
    critical: m.critical || 0,
    high: m.high || 0,
    medium: m.medium || 0,
    low: (m.low || 0) + (m.info || 0),
  }));

  const urgentCount = (data?.counts.critical ?? 0) + (data?.counts.high ?? 0);

  if (loading) {
    return (
      <div className="space-y-3">
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }
  if (error) {
    return (
      <div className="panel-sm border-[rgba(255,117,117,0.3)] text-[#ff9d9d] space-y-3">
        <div>{error}</div>
        <button type="button" onClick={reload} className="btn btn-secondary text-xs">
          Retry
        </button>
      </div>
    );
  }

  return (
    <>
      {alerts.length > 0 ? (
        <MotionPanel>
          <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Donut
              title="By category"
              data={Object.entries(byCategory).map(([name, value]) => ({
                name: name.replace(/_/g, " "),
                value,
              }))}
              centerLabel="alerts"
              centerValue={alerts.length}
              height={220}
            />
            <Donut
              title="By severity"
              colorMap={SEVERITY_COLOR}
              data={Object.entries(bySev).map(([name, value]) => ({ name, value }))}
              centerLabel="critical"
              centerValue={bySev.critical || 0}
              height={220}
            />
            <VBar
              title="Severity by category"
              data={stackData}
              stacked
              series={[
                { key: "critical", name: "critical", color: SEVERITY_COLOR.critical },
                { key: "high", name: "high", color: SEVERITY_COLOR.high },
                { key: "medium", name: "medium", color: SEVERITY_COLOR.medium },
                { key: "low", name: "low", color: SEVERITY_COLOR.low },
              ]}
              height={220}
            />
          </section>
        </MotionPanel>
      ) : null}

      {urgentCount > 0 ? (
        <div className="flex flex-wrap gap-2">
          {(["critical", "high"] as const).map((s) =>
            data?.counts[s] ? (
              <span key={s} className={`badge ${SEV_CHIP[s]}`}>
                {data.counts[s]} {s}
              </span>
            ) : null,
          )}
        </div>
      ) : null}

      <div className="panel-sm flex flex-wrap gap-3 items-end">
        <FilterGroup label="Severity">
          <select
            value={severity}
            onChange={(e) => setSeverity(e.target.value as AlertSeverity | "all")}
          >
            <option value="all">All severities</option>
            {SEVERITIES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </FilterGroup>
        <FilterGroup label="Category">
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="all">All categories</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </FilterGroup>
        <FilterGroup label="Search" grow>
          <input
            placeholder="Filter by title or detail..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </FilterGroup>
        <div className="text-xs text-muted pb-2">
          {filtered.length} of {alerts.length}
        </div>
      </div>

      <div className="panel overflow-x-auto p-0">
        {filtered.length ? (
          <table className="data-table">
            <thead>
              <tr>
                <th>Risk</th>
                <th>Category</th>
                <th>Severity</th>
                <th className="w-24">Action</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((a) => (
                <AlertRow key={a.alert_id} alert={a} />
              ))}
            </tbody>
          </table>
        ) : (
          <div className="p-6">
            <EmptyState
              title={alerts.length ? "No alerts match filters" : "No live alerts for this tenant"}
              hint={
                alerts.length
                  ? "Adjust the filters above to see more."
                  : "Check back as schedule and sourcing signals change."
              }
            />
          </div>
        )}
      </div>
    </>
  );
}

function FilterGroup({
  label,
  grow,
  children,
}: {
  label: string;
  grow?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className={`flex flex-col gap-1 ${grow ? "flex-1 min-w-[200px]" : "min-w-[160px]"}`}>
      <span className="text-[0.68rem] uppercase tracking-[0.12em] text-muted font-bold">
        {label}
      </span>
      {children}
    </label>
  );
}

function AlertRow({ alert }: { alert: Alert }) {
  return (
    <tr className="group">
      <td>
        <Link href={alert.href} className="block hover:text-accent transition-colors">
          <div className="font-semibold text-ink group-hover:text-accent">{alert.title}</div>
          <div className="text-xs text-muted mt-1 max-w-xl">{alert.detail}</div>
        </Link>
      </td>
      <td className="text-muted capitalize">{alert.category.replace(/_/g, " ")}</td>
      <td>
        <span className={`badge ${SEV_CHIP[alert.severity]}`}>{alert.severity}</span>
      </td>
      <td>
        <Link
          href={alert.href}
          className="text-[0.62rem] uppercase tracking-[0.1em] font-bold text-accent hover:text-accent-soft"
        >
          View
        </Link>
      </td>
    </tr>
  );
}
