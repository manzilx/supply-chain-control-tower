"use client";

import { useStore } from "@/lib/store-context";
import { formatTimestamp } from "@/lib/format";

export function TopBar() {
  const { scenario, analysis, status, error, loadDemo, analyze, lastAnalyzedAt } = useStore();
  const busy = status === "loading" || status === "analyzing";

  return (
    <header className="sticky top-0 z-10 border-b border-line bg-[rgba(7,16,24,0.72)] backdrop-blur-xl">
      <div className="flex items-center gap-4 px-6 py-3">
        <div className="min-w-0">
          <div className="text-[0.68rem] uppercase tracking-[0.16em] text-muted font-bold">
            Active Scenario
          </div>
          <div className="flex items-center gap-3 text-sm">
            <span className="text-ink font-semibold truncate">
              {scenario?.company.company_name ?? "No scenario loaded"}
            </span>
            {scenario ? (
              <span className="text-muted hidden md:inline">
                · {scenario.company.sector} · {scenario.company.active_projects} projects
              </span>
            ) : null}
          </div>
        </div>

        <div className="ml-auto flex items-center gap-3">
          {analysis ? (
            <div className="hidden md:block text-right">
              <div className="text-[0.68rem] uppercase tracking-[0.14em] text-muted">
                Overall Risk
              </div>
              <div className="text-lg font-bold text-ink">
                {analysis.overall_risk_score}
                <span className="text-muted text-sm font-normal">/100</span>
              </div>
            </div>
          ) : null}

          {lastAnalyzedAt ? (
            <div className="hidden md:block text-xs text-muted">
              Updated {formatTimestamp(lastAnalyzedAt)}
            </div>
          ) : null}

          <button
            className="btn btn-secondary"
            onClick={() => void loadDemo()}
            disabled={busy}
            aria-label="Load demo scenario"
          >
            {status === "loading" ? "Loading..." : "Load Demo"}
          </button>
          <button
            className="btn btn-primary"
            onClick={() => void analyze()}
            disabled={busy || !scenario}
            aria-label="Run agent analysis"
          >
            {status === "analyzing" ? "Analyzing..." : "Run Analysis"}
          </button>
        </div>
      </div>
      {error ? (
        <div className="px-6 py-2 text-sm text-[#ff9d9d] bg-[rgba(255,117,117,0.08)] border-t border-[rgba(255,117,117,0.2)]">
          {error}
        </div>
      ) : null}
    </header>
  );
}
