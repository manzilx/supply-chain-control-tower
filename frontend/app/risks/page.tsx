"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { Donut, MotionPanel, SEVERITY_COLOR, VBar } from "@/components/charts";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { SkeletonCard } from "@/components/skeleton";
import { fetchAlerts } from "@/lib/api";
import { useAsync } from "@/lib/use-async";
import type { Alert, AlertSeverity } from "@/lib/types";

const SEVERITIES: AlertSeverity[] = ["critical", "high", "medium", "low", "info"];

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

export default function RisksPage() {
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

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Risks"
        title="Risk Register"
        description="Live tenant risks from schedule, sourcing, commercial, and expediting signals — the same feed as notifications, filterable here."
      />

      {loading ? (
        <div className="space-y-3">
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : error ? (
        <div className="panel-sm border-[rgba(255,117,117,0.3)] text-[#ff9d9d] space-y-3">
          <div>{error}</div>
          <button type="button" onClick={reload} className="btn btn-secondary text-xs">
            Retry
          </button>
        </div>
      ) : (
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
                  centerLabel="risks"
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
                  title={alerts.length ? "No risks match filters" : "No live risks for this tenant"}
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
      )}
    </div>
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
