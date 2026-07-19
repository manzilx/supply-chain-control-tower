"use client";

import { useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { fetchSapHealth, resyncSap } from "@/lib/api";
import { useAsync } from "@/lib/use-async";

const MODE_BADGE: Record<string, string> = {
  mock:     "bg-amber-500/15 text-amber-300 border-amber-500/40",
  live:     "bg-emerald-500/15 text-emerald-300 border-emerald-500/40",
  disabled: "bg-zinc-500/15 text-zinc-300 border-zinc-500/40",
};

const MODE_LABEL: Record<string, string> = {
  mock:     "MOCK (test data, no real SAP)",
  live:     "LIVE (real CPI tenant)",
  disabled: "DISABLED",
};

function fmt(ts?: string | null) {
  if (!ts) return "—";
  return new Date(ts).toLocaleString();
}

export default function IntegrationsPage() {
  const health = useAsync(fetchSapHealth, []);
  const [resyncing, setResyncing] = useState(false);
  const [resyncResult, setResyncResult] = useState<string | null>(null);

  async function doResync() {
    setResyncing(true);
    setResyncResult(null);
    try {
      const r = await resyncSap();
      setResyncResult(`Reconciled ${r.prs_reconciled} PRs and ${r.pos_reconciled} POs.`);
      health.reload();
    } catch (e) {
      setResyncResult(e instanceof Error ? e.message : "Resync failed");
    } finally {
      setResyncing(false);
    }
  }

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Integrations"
        title="SAP CPI"
        description="Submit PRs and POs into SAP via Cloud Integration. Status changes flow back through inbound webhooks."
      />

      {health.loading ? (
        <EmptyState title="Reading integration health..." />
      ) : health.error || !health.data ? (
        <div className="panel-sm border-[rgba(255,117,117,0.3)] text-[#ff9d9d]">
          {health.error ?? "Health endpoint unreachable"}
        </div>
      ) : (
        <>
          <section className="panel">
            <div className="flex items-baseline justify-between gap-4 flex-wrap">
              <div>
                <div className="text-[0.68rem] uppercase tracking-[0.14em] text-muted font-bold">Mode</div>
                <div className="mt-1 flex items-center gap-2">
                  <span
                    className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-[0.65rem] font-bold uppercase tracking-[0.08em] ${MODE_BADGE[health.data.mode]}`}
                  >
                    {MODE_LABEL[health.data.mode]}
                  </span>
                </div>
                {health.data.base_url ? (
                  <div className="text-xs text-muted mt-1 font-mono">{health.data.base_url}</div>
                ) : null}
              </div>
              <button
                className="btn btn-primary text-sm"
                onClick={() => void doResync()}
                disabled={resyncing || health.data.mode === "disabled"}
              >
                {resyncing ? "Reconciling…" : "Reconcile now"}
              </button>
            </div>

            {resyncResult ? (
              <div className="mt-3 text-xs text-ink panel-sm">{resyncResult}</div>
            ) : null}
          </section>

          <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Stat label="Submissions" value={String(health.data.submissions_total)} />
            <Stat
              label="Failed"
              value={String(health.data.submissions_failed)}
              tone={health.data.submissions_failed > 0 ? "bad" : "neutral"}
            />
            <Stat label="Events received" value={String(health.data.events_received)} />
            <Stat
              label="Token valid until"
              value={fmt(health.data.token_valid_until)}
              tone={health.data.token_valid_until ? "good" : "neutral"}
            />
          </section>

          <section className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="panel-sm">
              <div className="text-[0.62rem] uppercase tracking-[0.12em] text-emerald-300 font-bold mb-1">
                Last successful sync
              </div>
              <div className="text-sm text-ink">{fmt(health.data.last_success_at)}</div>
            </div>
            <div className="panel-sm">
              <div className="text-[0.62rem] uppercase tracking-[0.12em] text-rose-300 font-bold mb-1">
                Last error
              </div>
              <div className="text-sm text-ink">{fmt(health.data.last_error_at)}</div>
              {health.data.last_error ? (
                <div className="text-xs text-rose-300 mt-1 font-mono">{health.data.last_error}</div>
              ) : null}
            </div>
          </section>

          <section className="panel">
            <h2 className="m-0 text-base font-bold mb-2">How this works</h2>
            <ol className="list-decimal pl-5 space-y-1 text-sm text-ink/90">
              <li>Drafts (PRs and POs) live in Control Tower with <code className="font-mono text-xs bg-white/5 px-1 rounded">sap_status: draft</code>.</li>
              <li>Click <strong>Submit to SAP</strong> on a PR or PO. Control Tower posts to CPI via the contract endpoints.</li>
              <li>CPI iflows handle the SAP-specific protocol (BAPI for ECC, OData for S/4HANA) and return the SAP doc number.</li>
              <li>SAP status changes (PR released, PO approved, GR posted, IR posted) flow back via the inbound webhook at <code className="font-mono text-xs bg-white/5 px-1 rounded">POST /api/integrations/sap/event</code>.</li>
              <li>The reconcile job catches anything the webhook misses.</li>
            </ol>
          </section>

          <section className="panel">
            <h2 className="m-0 text-base font-bold mb-2">Switching to live mode</h2>
            <p className="text-sm text-ink/90 mb-2">
              In <code className="font-mono text-xs bg-white/5 px-1 rounded">.env</code>, set:
            </p>
            <pre className="text-xs bg-black/30 rounded p-3 overflow-x-auto font-mono">
{`SAP_CPI_MODE=live
SAP_CPI_BASE_URL=https://<tenant>.it-cpi-002.cfapps.eu1.hana.ondemand.com
SAP_CPI_CLIENT_ID=...
SAP_CPI_CLIENT_SECRET=...
SAP_CPI_TOKEN_URL=https://<tenant>.authentication.eu1.hana.ondemand.com/oauth/token`}
            </pre>
            <p className="text-xs text-muted mt-2">
              Then <code className="font-mono">make stop && make demo</code>. The orchestrator auto-sources <code className="font-mono">.env</code>.
            </p>
          </section>
        </>
      )}
    </div>
  );
}

function Stat({ label, value, tone = "neutral" }: { label: string; value: string; tone?: "good" | "warn" | "bad" | "neutral" }) {
  const cls = {
    good: "text-emerald-300",
    warn: "text-amber-300",
    bad: "text-rose-300",
    neutral: "text-ink",
  }[tone];
  return (
    <div className="panel-sm">
      <div className="text-[0.62rem] uppercase tracking-[0.12em] text-muted font-bold mb-1">{label}</div>
      <div className={`text-lg font-bold ${cls}`}>{value}</div>
    </div>
  );
}
