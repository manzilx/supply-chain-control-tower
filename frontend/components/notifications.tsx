"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { fetchAlerts } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { Alert, AlertFeed, AlertSeverity } from "@/lib/types";

const SEV_TONE: Record<AlertSeverity, { dot: string; text: string; chip: string }> = {
  critical: { dot: "bg-danger", text: "text-danger", chip: "severity-critical" },
  high: { dot: "bg-[#ff9187]", text: "text-[#ff9187]", chip: "severity-high" },
  medium: { dot: "bg-warning", text: "text-warning", chip: "severity-medium" },
  low: { dot: "bg-steady", text: "text-steady", chip: "severity-low" },
  info: { dot: "bg-steady", text: "text-steady", chip: "severity-low" },
};

const CATEGORY_ICON: Record<string, string> = {
  approval: "✓",
  schedule: "◷",
  vendor: "▤",
  commercial: "$",
  expediting: "▲",
  engineering: "⚙",
};

export function Notifications() {
  const { status } = useAuth();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [feed, setFeed] = useState<AlertFeed | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (status !== "authed") return;
    let active = true;
    const load = () => {
      fetchAlerts()
        .then((f) => {
          if (!active) return;
          setFeed(f);
          setError(null);
        })
        .catch((err) => {
          if (!active) return;
          setError(err instanceof Error ? err.message : "Couldn't load alerts");
        });
    };
    load();
    const id = setInterval(load, 30000); // live-ish poll
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [status]);

  function retry() {
    fetchAlerts()
      .then((f) => {
        setFeed(f);
        setError(null);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Couldn't load alerts");
      });
  }

  if (status !== "authed") return null;

  const urgent = feed ? (feed.counts.critical ?? 0) + (feed.counts.high ?? 0) : 0;
  const total = feed?.total ?? 0;

  function go(alert: Alert) {
    setOpen(false);
    router.push(alert.href);
  }

  return (
    <>
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative flex items-center justify-center w-9 h-9 rounded-lg border border-line bg-white/[0.02] hover:bg-white/[0.05] transition-colors"
        aria-label={`Notifications (${total})`}
        title="Alerts"
      >
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-ink/80">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {urgent > 0 ? (
          <span className="absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px] px-1 rounded-full bg-danger text-white text-[0.6rem] font-bold flex items-center justify-center">
            {urgent}
          </span>
        ) : total > 0 ? (
          <span className="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-warning" />
        ) : null}
      </button>

      {open ? (
        <>
          <div className="fixed inset-0 z-[80]" onClick={() => setOpen(false)} />
          <div className="fixed top-[60px] right-4 z-[81] w-[min(420px,calc(100vw-2rem))] panel p-0 overflow-hidden shadow-panel animate-fade-up max-h-[80vh] flex flex-col">
            <div className="px-4 py-3 border-b border-line flex items-center justify-between">
              <div>
                <div className="text-[0.65rem] uppercase tracking-[0.14em] text-muted font-bold">Control Tower</div>
                <div className="text-base font-bold">Alerts {total ? `· ${total}` : ""}</div>
              </div>
              <div className="flex gap-1.5">
                {(["critical", "high", "medium"] as const).map((s) =>
                  feed?.counts[s] ? (
                    <span key={s} className={`badge ${SEV_TONE[s].chip}`}>
                      {feed.counts[s]} {s}
                    </span>
                  ) : null,
                )}
              </div>
            </div>
            <div className="overflow-y-auto flex-1">
              {error && !feed ? (
                <div className="px-4 py-10 text-center space-y-3">
                  <div className="text-sm text-danger">{error}</div>
                  <button type="button" onClick={retry} className="btn btn-secondary text-xs">
                    Retry
                  </button>
                </div>
              ) : !feed ? (
                <div className="px-4 py-10 text-center text-muted text-sm">Loading…</div>
              ) : feed.alerts.length === 0 ? (
                <div className="px-4 py-12 text-center">
                  <div className="text-3xl mb-2">✓</div>
                  <div className="text-sm text-ink">All clear</div>
                  <div className="text-xs text-muted mt-1">No alerts need attention right now.</div>
                </div>
              ) : (
                <ul>
                  {feed.alerts.map((a) => {
                    const tone = SEV_TONE[a.severity];
                    return (
                      <li
                        key={a.alert_id}
                        onClick={() => go(a)}
                        className="px-4 py-3 border-b border-line/60 cursor-pointer hover:bg-white/[0.03] flex items-start gap-3"
                      >
                        <span className={`mt-1 w-2 h-2 rounded-full shrink-0 ${tone.dot}`} />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span className="text-[0.6rem]">{CATEGORY_ICON[a.category] ?? "•"}</span>
                            <span className={`text-[0.6rem] uppercase tracking-[0.1em] font-bold ${tone.text}`}>
                              {a.category}
                            </span>
                          </div>
                          <div className="text-sm text-ink mt-0.5 leading-snug">{a.title}</div>
                          <div className="text-xs text-muted mt-0.5 leading-snug">{a.detail}</div>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </div>
        </>
      ) : null}
    </>
  );
}
