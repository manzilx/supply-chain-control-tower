"use client";

import { motion, AnimatePresence } from "framer-motion";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AnimatedKpiTile, CHART_PALETTE, Donut, HBar, MotionPanel } from "@/components/charts";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { TraceabilityLadder } from "@/components/traceability";
import {
  downloadAuditCsv,
  fetchAudit,
  fetchAuditStats,
  fetchPivotMaterials,
  fetchPivotPos,
  fetchPivotVendors,
} from "@/lib/api";
import { useToast } from "@/lib/toast-context";
import type {
  AuditAction,
  AuditEvent,
  AuditSource,
  PivotCount,
} from "@/lib/types";

type Mode = "all" | "material" | "po" | "vendor";

const ACTION_TONE: Partial<Record<AuditAction, string>> = {
  created:           "bg-emerald-500/15 text-emerald-300 border-emerald-500/40",
  uploaded:          "bg-emerald-500/15 text-emerald-300 border-emerald-500/40",
  issued:            "bg-sky-500/15 text-sky-300 border-sky-500/40",
  received:          "bg-sky-500/15 text-sky-300 border-sky-500/40",
  evaluated:         "bg-violet-500/15 text-violet-300 border-violet-500/40",
  awarded:           "bg-amber-500/15 text-amber-300 border-amber-500/40",
  po_drafted:        "bg-amber-500/15 text-amber-300 border-amber-500/40",
  submitted_to_sap:  "bg-orange-500/15 text-orange-300 border-orange-500/40",
  sap_status_changed:"bg-orange-500/15 text-orange-300 border-orange-500/40",
  stage_advanced:    "bg-lime-500/15 text-lime-300 border-lime-500/40",
  gr_posted:         "bg-lime-500/15 text-lime-300 border-lime-500/40",
  ir_posted:         "bg-lime-500/15 text-lime-300 border-lime-500/40",
  delivered:         "bg-emerald-500/15 text-emerald-300 border-emerald-500/40",
  approved:          "bg-emerald-500/15 text-emerald-300 border-emerald-500/40",
  rejected:          "bg-rose-500/15 text-rose-300 border-rose-500/40",
  ai_generated:      "bg-violet-500/15 text-violet-300 border-violet-500/40",
};

const SOURCE_TONE: Record<AuditSource, string> = {
  ui:            "bg-sky-500/10 text-sky-300",
  api:           "bg-emerald-500/10 text-emerald-300",
  sap_webhook:   "bg-orange-500/10 text-orange-300",
  ai:            "bg-violet-500/10 text-violet-300",
  scheduled_job: "bg-zinc-500/10 text-zinc-300",
  csv_upload:    "bg-amber-500/10 text-amber-300",
  system:        "bg-zinc-500/10 text-zinc-300",
};

export default function AuditPage() {
  const search = useSearchParams();
  const [mode, setMode] = useState<Mode>((search.get("mode") as Mode) || "all");
  const [selected, setSelected] = useState<string | null>(
    search.get("bom_code") || search.get("po_no") || search.get("vendor") || null
  );

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Audit"
        title="Audit Trail"
        description="Pivot on material, PO, or vendor — or browse the full event feed. Filter, drill, export."
      />

      {/* Mode tabs */}
      <div className="panel-sm flex flex-wrap items-center gap-1">
        {(["all", "material", "po", "vendor"] as Mode[]).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => { setMode(m); setSelected(null); }}
            className={`px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-[0.1em] transition ${
              mode === m
                ? "bg-accent/20 text-accent border border-accent/40"
                : "text-muted hover:text-ink"
            }`}
          >
            {m === "all" ? "All events" :
             m === "material" ? "By Material" :
             m === "po" ? "By PO" : "By Vendor"}
          </button>
        ))}
      </div>

      <AnimatePresence mode="wait">
        <motion.div
          key={mode}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          transition={{ duration: 0.2 }}
          className="space-y-5"
        >
          {mode === "all" ? (
            <AllEventsView />
          ) : (
            <PivotView mode={mode} selected={selected} onSelect={setSelected} />
          )}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

// ====================================================================
// All Events view (the original feed)
// ====================================================================

function AllEventsView() {
  const search = useSearchParams();
  const { error: toastError, success } = useToast();
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [stats, setStats] = useState<Record<string, any> | null>(null);
  const [filters, setFilters] = useState<Record<string, string>>(() => ({
    actor:       search.get("actor")       || "",
    action:      search.get("action")      || "",
    entity_kind: search.get("entity_kind") || "",
    search:      search.get("search")      || "",
  }));

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [page, s] = await Promise.all([
        fetchAudit({ ...filters, limit: 200, offset: 0 }),
        fetchAuditStats(),
      ]);
      setEvents(page.events);
      setTotal(page.total);
      setStats(s);
    } finally {
      setLoading(false);
    }
  }, [filters]);
  useEffect(() => { void load(); }, [load]);

  async function handleExport() {
    setExporting(true);
    try {
      await downloadAuditCsv(filters);
      success("Audit CSV downloaded");
    } catch (err) {
      toastError(err instanceof Error ? err.message : "CSV export failed");
    } finally {
      setExporting(false);
    }
  }

  return (
    <>
      <section className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <AnimatedKpiTile label="Total events" value={stats?.total ?? 0} delay={0.0} />
        <AnimatedKpiTile label="Matched filter" value={total} delay={0.05} />
        <AnimatedKpiTile label="Actions tracked" value={Object.keys(stats?.by_action ?? {}).length} hint={`${Object.keys(stats?.by_entity_kind ?? {}).length} kinds`} delay={0.10} />
        <AnimatedKpiTile label="AI events" value={(stats?.by_source ?? {})["ai"] ?? 0} tone="warn" delay={0.15} />
        <AnimatedKpiTile label="SAP events" value={(stats?.by_source ?? {})["sap_webhook"] ?? 0} delay={0.20} />
      </section>

      <div className="panel-sm flex flex-wrap gap-3 items-end">
        <FilterField label="Search" wide>
          <input placeholder="Subject or summary..." value={filters.search} onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))} />
        </FilterField>
        <FilterField label="Action">
          <select value={filters.action} onChange={(e) => setFilters((f) => ({ ...f, action: e.target.value }))}>
            <option value="">All actions</option>
            {Object.keys(stats?.by_action ?? {}).sort().map((a) => <option key={a} value={a}>{a.replace(/_/g, " ")}</option>)}
          </select>
        </FilterField>
        <FilterField label="Entity">
          <select value={filters.entity_kind} onChange={(e) => setFilters((f) => ({ ...f, entity_kind: e.target.value }))}>
            <option value="">All kinds</option>
            {Object.keys(stats?.by_entity_kind ?? {}).sort().map((k) => <option key={k} value={k}>{k.replace(/_/g, " ")}</option>)}
          </select>
        </FilterField>
        <FilterField label="Actor">
          <select value={filters.actor} onChange={(e) => setFilters((f) => ({ ...f, actor: e.target.value }))}>
            <option value="">All actors</option>
            {Object.keys(stats?.by_actor ?? {}).sort().map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
        </FilterField>
        <button
          type="button"
          className="btn btn-secondary text-xs"
          onClick={() => void handleExport()}
          disabled={exporting}
        >
          {exporting ? "Exporting…" : "⬇ Export CSV"}
        </button>
        <button className="btn btn-secondary text-xs" onClick={() => setFilters({ actor: "", action: "", entity_kind: "", search: "" })}>Clear</button>
      </div>

      <EventsTable events={events} total={total} loading={loading} />
    </>
  );
}

// ====================================================================
// Pivot views
// ====================================================================

function PivotView({ mode, selected, onSelect }: { mode: Mode; selected: string | null; onSelect: (k: string | null) => void }) {
  const [pivots, setPivots] = useState<PivotCount[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const fetcher = mode === "material" ? fetchPivotMaterials :
                    mode === "po"       ? fetchPivotPos :
                                          fetchPivotVendors;
    fetcher()
      .then((r) => { if (!cancelled) setPivots(r); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [mode]);

  const filtered = useMemo(() => {
    if (!pivots) return [];
    const q = search.toLowerCase().trim();
    if (!q) return pivots;
    return pivots.filter((p) =>
      p.key.toLowerCase().includes(q) ||
      (p.description || "").toLowerCase().includes(q) ||
      (p.category || "").toLowerCase().includes(q)
    );
  }, [pivots, search]);

  const label = mode === "material" ? "Material" : mode === "po" ? "Purchase Order" : "Vendor";

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-4">
      {/* Picker */}
      <aside className="panel space-y-2 max-h-[calc(100vh-280px)] overflow-y-auto">
        <div className="flex items-baseline justify-between">
          <div className="text-[0.65rem] uppercase tracking-[0.12em] text-accent font-bold">
            Select {label}
          </div>
          <div className="text-xs text-muted">{filtered.length}</div>
        </div>
        <input
          placeholder={`Search ${label.toLowerCase()}...`}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full"
        />
        {loading ? (
          <div className="text-muted text-sm py-4">Loading…</div>
        ) : (
          <ol className="space-y-1">
            {filtered.map((p, i) => (
              <motion.li
                key={p.key}
                initial={{ opacity: 0, x: -4 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.2, delay: Math.min(i * 0.01, 0.3) }}
              >
                <button
                  type="button"
                  onClick={() => onSelect(p.key)}
                  className={`w-full text-left px-2.5 py-2 rounded-md border transition ${
                    selected === p.key
                      ? "bg-accent/15 border-accent/40 text-ink"
                      : "border-transparent hover:bg-white/[0.04] text-muted hover:text-ink"
                  }`}
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="font-mono text-xs text-ink truncate">{p.label}</span>
                    <span className={`text-[0.6rem] font-bold ${p.event_count > 0 ? "text-accent" : "text-muted"}`}>
                      {p.event_count}
                    </span>
                  </div>
                  {p.description ? (
                    <div className="text-[0.65rem] text-muted truncate mt-0.5">{p.description}</div>
                  ) : null}
                  <div className="flex items-center gap-2 mt-1 text-[0.6rem] text-muted">
                    {p.value_usd ? <span>${(p.value_usd / 1000).toFixed(0)}k</span> : null}
                    {p.related_pos ? <span>· {p.related_pos} PO</span> : null}
                    {p.related_rfqs ? <span>· {p.related_rfqs} RFQ</span> : null}
                    {p.related_vendors ? <span>· {p.related_vendors} vendors</span> : null}
                    {p.status ? <span>· {p.status}</span> : null}
                  </div>
                </button>
              </motion.li>
            ))}
            {filtered.length === 0 ? (
              <li className="text-muted text-xs py-4">No matches</li>
            ) : null}
          </ol>
        )}
      </aside>

      {/* Detail */}
      <div className="space-y-4">
        {!selected ? (
          <div className="panel">
            <EmptyState
              title={`Select a ${label.toLowerCase()} from the list`}
              hint={`Each ${label.toLowerCase()} has its full event history, traceability chain, and related entities.`}
            />
          </div>
        ) : mode === "material" ? (
          <MaterialDetail bomCode={selected} pivot={(pivots || []).find((p) => p.key === selected)} />
        ) : mode === "po" ? (
          <PoDetail poNo={selected} pivot={(pivots || []).find((p) => p.key === selected)} />
        ) : (
          <VendorDetail vendor={selected} pivot={(pivots || []).find((p) => p.key === selected)} />
        )}
      </div>
    </div>
  );
}

// --- Material detail -------------------------------------------------

function MaterialDetail({ bomCode, pivot }: { bomCode: string; pivot?: PivotCount }) {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchAudit({ bom_code: bomCode, limit: 500 })
      .then((p) => { if (!cancelled) setEvents(p.events); })
      .finally(() => { if (!cancelled) setLoading(false); });
  }, [bomCode]);

  // Find a bom_item_id from the events (any one will do for the trace API)
  const bomItemId = useMemo(() => events.find((e) => e.bom_item_id)?.bom_item_id, [events]);

  return (
    <>
      <PivotHeader
        kind="Material"
        title={bomCode}
        subtitle={pivot?.description}
        tags={[pivot?.category, pivot?.project_id].filter(Boolean) as string[]}
      />

      <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <AnimatedKpiTile label="Audit events" value={pivot?.event_count ?? 0} delay={0.0} />
        <AnimatedKpiTile label="Related POs" value={pivot?.related_pos ?? 0} delay={0.05} />
        <AnimatedKpiTile label="Related RFQs" value={pivot?.related_rfqs ?? 0} delay={0.10} />
        <AnimatedKpiTile label="Related vendors" value={pivot?.related_vendors ?? 0} delay={0.15} />
      </section>

      {bomItemId ? <TraceabilityLadder kind="bom" id={bomItemId} /> : (
        <div className="panel-sm text-muted text-sm">No BOM-rooted trace available — this material may not have a PR yet.</div>
      )}

      <EventsTable events={events} total={events.length} loading={loading} />
    </>
  );
}

// --- PO detail -------------------------------------------------------

function PoDetail({ poNo, pivot }: { poNo: string; pivot?: PivotCount }) {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchAudit({ po_no: poNo, limit: 500 })
      .then((p) => { if (!cancelled) setEvents(p.events); })
      .finally(() => { if (!cancelled) setLoading(false); });
  }, [poNo]);

  const isSourcingPo = poNo.startsWith("SPO-");

  return (
    <>
      <PivotHeader
        kind="Purchase Order"
        title={poNo}
        subtitle={pivot?.description}
        tags={[pivot?.status, pivot?.project_id].filter(Boolean) as string[]}
      />

      <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <AnimatedKpiTile label="Audit events" value={pivot?.event_count ?? 0} delay={0.0} />
        <AnimatedKpiTile
          label="PO value"
          value={pivot?.value_usd ?? 0}
          prefix="$"
          format={(v) => Math.round(v).toLocaleString()}
          delay={0.05}
        />
        <AnimatedKpiTile
          label="SAP events"
          value={events.filter((e) => e.source === "sap_webhook").length}
          delay={0.10}
        />
        <AnimatedKpiTile
          label="Last activity"
          value={pivot?.last_at ? Math.floor((Date.now() - new Date(pivot.last_at).getTime()) / 86400000) : 0}
          suffix=" days ago"
          delay={0.15}
        />
      </section>

      {isSourcingPo ? <TraceabilityLadder kind="po" id={poNo} /> : null}

      <EventsTable events={events} total={events.length} loading={loading} />
    </>
  );
}

// --- Vendor detail ---------------------------------------------------

function VendorDetail({ vendor, pivot }: { vendor: string; pivot?: PivotCount }) {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchAudit({ vendor, limit: 500 })
      .then((p) => { if (!cancelled) setEvents(p.events); })
      .finally(() => { if (!cancelled) setLoading(false); });
  }, [vendor]);

  const byAction = useMemo(() => {
    const counts: Record<string, number> = {};
    events.forEach((e) => { counts[e.action] = (counts[e.action] || 0) + 1; });
    return Object.entries(counts).map(([name, value]) => ({ name: name.replace(/_/g, " "), value }));
  }, [events]);

  const valueByPo = useMemo(() => {
    const m: Record<string, number> = {};
    events.forEach((e) => {
      if (e.po_no && typeof e.metadata?.["value_usd"] === "number") {
        const v = e.metadata["value_usd"] as number;
        if (!m[e.po_no] || v > m[e.po_no]) m[e.po_no] = v;
      }
    });
    return Object.entries(m).sort((a, b) => b[1] - a[1]).slice(0, 8).map(([name, value]) => ({ name, value }));
  }, [events]);

  return (
    <>
      <PivotHeader
        kind="Vendor"
        title={vendor}
        subtitle={pivot?.category}
        tags={[pivot?.related_pos ? `${pivot.related_pos} PO` : null, pivot?.related_rfqs ? `${pivot.related_rfqs} RFQ` : null].filter(Boolean) as string[]}
      />

      <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <AnimatedKpiTile label="Audit events" value={pivot?.event_count ?? 0} delay={0.0} />
        <AnimatedKpiTile label="Awarded POs" value={pivot?.related_pos ?? 0} delay={0.05} />
        <AnimatedKpiTile label="Invited to RFQs" value={pivot?.related_rfqs ?? 0} delay={0.10} />
        <AnimatedKpiTile
          label="Total spend / annual"
          value={pivot?.value_usd ?? 0}
          prefix="$"
          format={(v) => Math.round(v).toLocaleString()}
          delay={0.15}
        />
      </section>

      {(events.length > 0) ? (
        <MotionPanel delay={0.1}>
          <section className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Donut
              title="Events by action"
              data={byAction}
              centerLabel="events"
              centerValue={events.length}
              height={220}
            />
            {valueByPo.length > 0 ? (
              <HBar
                title="PO values"
                color={CHART_PALETTE.accent}
                data={valueByPo}
                valueFormat={(v) => `$${(v / 1000).toFixed(0)}k`}
                height={220}
              />
            ) : null}
          </section>
        </MotionPanel>
      ) : null}

      <EventsTable events={events} total={events.length} loading={loading} />
    </>
  );
}

// --- Shared bits -----------------------------------------------------

function PivotHeader({ kind, title, subtitle, tags }: { kind: string; title: string; subtitle?: string | null; tags?: string[] }) {
  return (
    <div className="panel flex items-baseline justify-between gap-3 flex-wrap">
      <div>
        <div className="text-[0.65rem] uppercase tracking-[0.12em] text-accent font-bold">{kind}</div>
        <h2 className="text-xl font-bold m-0 mt-1 font-mono">{title}</h2>
        {subtitle ? <div className="text-sm text-muted mt-1">{subtitle}</div> : null}
      </div>
      {tags && tags.length > 0 ? (
        <div className="flex gap-1 flex-wrap">
          {tags.map((t, i) => (
            <span key={i} className="text-[0.62rem] uppercase tracking-wider font-bold text-ink/80 bg-white/[0.05] border border-line px-2 py-0.5 rounded">
              {t}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function EventsTable({ events, total, loading }: { events: AuditEvent[]; total: number; loading: boolean }) {
  return (
    <section className="panel overflow-x-auto p-0">
      {loading ? (
        <EmptyState title="Loading events..." />
      ) : events.length === 0 ? (
        <EmptyState
          title="No events"
          hint="Either nothing has happened yet, or your filters excluded everything."
        />
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>When</th>
              <th>Action</th>
              <th>Entity</th>
              <th>Summary</th>
              <th>Actor</th>
              <th>Source</th>
              <th>Vendor</th>
              <th>Links</th>
            </tr>
          </thead>
          <tbody>
            {events.map((e, i) => (
              <motion.tr
                key={e.event_id}
                initial={{ opacity: 0, y: 3 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.22, delay: Math.min(i * 0.008, 0.3) }}
              >
                <td className="font-mono text-xs text-muted whitespace-nowrap">
                  {new Date(e.occurred_at).toLocaleString()}
                </td>
                <td>
                  <span className={`inline-block rounded border px-1.5 py-0.5 text-[0.6rem] font-bold uppercase tracking-wider ${ACTION_TONE[e.action] ?? "bg-zinc-500/15 text-zinc-300 border-zinc-500/40"}`}>
                    {e.action.replace(/_/g, " ")}
                  </span>
                </td>
                <td>
                  <div className="text-xs text-muted">{e.entity_kind.replace(/_/g, " ")}</div>
                  <div className="font-mono text-xs text-ink">{e.entity_id}</div>
                </td>
                <td className="max-w-md">
                  <div className="text-sm text-ink">{e.subject}</div>
                  <div className="text-xs text-muted">{e.summary}</div>
                </td>
                <td className="font-mono text-xs">{e.actor}</td>
                <td>
                  <span className={`rounded px-1.5 py-0.5 text-[0.6rem] font-bold uppercase tracking-wider ${SOURCE_TONE[e.source]}`}>
                    {e.source.replace(/_/g, " ")}
                  </span>
                </td>
                <td className="text-xs text-ink">{e.vendor ?? "—"}</td>
                <td>
                  <div className="flex flex-wrap gap-1 text-[0.65rem]">
                    {e.bom_code ? <LinkChip kind="material" id={e.bom_code} /> : null}
                    {e.pr_no ?    <LinkChip kind="pr" id={e.pr_no} /> : null}
                    {e.rfq_no ?   <LinkChip kind="rfq" id={e.rfq_no} /> : null}
                    {e.po_no ?    <LinkChip kind="po" id={e.po_no} /> : null}
                    {e.sap_doc_no ? <span className="font-mono text-orange-300">SAP {e.sap_doc_no}</span> : null}
                  </div>
                </td>
              </motion.tr>
            ))}
          </tbody>
        </table>
      )}
      {!loading && total > events.length ? (
        <div className="p-3 text-xs text-muted text-center border-t border-line">
          Showing {events.length} of {total} matching events — refine to narrow.
        </div>
      ) : null}
    </section>
  );
}

function FilterField({ label, wide, children }: { label: string; wide?: boolean; children: React.ReactNode }) {
  return (
    <label className={`flex flex-col gap-1 ${wide ? "flex-1 min-w-[220px]" : "min-w-[140px]"}`}>
      <span className="text-[0.68rem] uppercase tracking-[0.12em] text-muted font-bold">{label}</span>
      {children}
    </label>
  );
}

function LinkChip({ kind, id }: { kind: "material" | "pr" | "rfq" | "po"; id: string }) {
  const href =
    kind === "material" ? `/audit?mode=material&bom_code=${encodeURIComponent(id)}` :
    kind === "pr"  ? `/sourcing/prs/${encodeURIComponent(id)}` :
    kind === "rfq" ? `/sourcing/rfqs/${encodeURIComponent(id)}` :
                     `/audit?mode=po&po_no=${encodeURIComponent(id)}`;
  return (
    <a href={href} className="font-mono text-accent hover:underline whitespace-nowrap">
      {id}
    </a>
  );
}
