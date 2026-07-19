"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { PageHeader } from "@/components/page-header";
import { sendChat } from "@/lib/api";
import { useStore } from "@/lib/store-context";
import type { ChatReply, ChatTurn, ToolCallRecord } from "@/lib/types";

const SUGGESTIONS = [
  "Show me this week's action plan",
  "Which vendors are most likely to cause delays?",
  "Draft an urgent follow-up for PO-24017",
  "Any savings or overruns this quarter?",
  "Show long-lead items for Riverbank",
  "What should we do about single-source vendors?",
];

const SOURCE_LABEL: Record<ChatReply["source"], string> = {
  grok: "Grok",
  claude: "Claude",
  openai: "OpenAI",
  deterministic: "Rule-based",
};

const PERSONA_LABEL: Record<ChatReply["persona"], string> = {
  sourcing: "Sourcing agent",
  expediting: "Expediting agent",
  vendor_risk: "Vendor-risk agent",
  logistics: "Logistics agent",
  commercial: "Commercial agent",
  planning: "Planning agent",
  reporting: "Reporting agent",
  general: "Control Tower",
};

type DisplayTurn = ChatTurn & { persona?: ChatReply["persona"]; source?: ChatReply["source"] };

export default function AgentPage() {
  const { scenario } = useStore();
  const [turns, setTurns] = useState<DisplayTurn[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [turns.length, sending]);

  async function send(text: string) {
    const message = text.trim();
    if (!message || sending) return;
    setDraft("");
    setError(null);
    setSending(true);

    const userTurn: DisplayTurn = {
      role: "user",
      content: message,
      created_at: new Date().toISOString(),
    };
    const history = [...turns, userTurn];
    setTurns(history);

    try {
      const history_for_api: ChatTurn[] = turns.map((t) => ({
        role: t.role,
        content: t.content,
      }));
      const reply = await sendChat({ message, history: history_for_api });
      setTurns((prev) => [
        ...prev,
        {
          role: "assistant",
          content: reply.reply,
          tool_calls: reply.tool_calls,
          created_at: reply.generated_at,
          persona: reply.persona,
          source: reply.source,
        },
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Chat request failed");
    } finally {
      setSending(false);
    }
  }

  function clear() {
    setTurns([]);
    setError(null);
  }

  return (
    <div className="space-y-5 max-w-5xl">
      <PageHeader
        eyebrow="Agent"
        title="AI Command Center"
        description="Ask anything. The agent will call the right tools across sourcing, expediting, vendor intel, logistics, commercial, and planning — with every call visible below each reply."
        right={
          turns.length > 0 ? (
            <button className="btn btn-secondary text-xs" onClick={clear}>
              New chat
            </button>
          ) : null
        }
      />

      <div className="panel flex flex-col min-h-[520px]">
        <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto pr-1 max-h-[62vh]">
          {turns.length === 0 ? (
            <div className="text-center py-8">
              <div className="text-ink font-semibold mb-2">Start a conversation</div>
              <div className="text-sm text-muted mb-5 max-w-md mx-auto">
                {scenario
                  ? `Ask about ${scenario.company.company_name}'s supply chain. Try one of these:`
                  : "Load the demo scenario first via the top-bar button."}
              </div>
              <div className="flex flex-wrap gap-2 justify-center">
                {SUGGESTIONS.map((s) => (
                  <button key={s} className="btn btn-secondary text-xs" onClick={() => send(s)}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            turns.map((turn, idx) => (
              <MessageBubble key={idx} turn={turn} />
            ))
          )}
          {sending ? (
            <div className="flex justify-start">
              <div className="panel-sm text-sm text-muted animate-pulse">Thinking...</div>
            </div>
          ) : null}
        </div>

        <div className="mt-4 pt-4 border-t border-line space-y-2">
          {error ? <div className="text-[#ff9d9d] text-sm">{error}</div> : null}
          <div className="flex gap-2">
            <input
              placeholder={scenario ? "Ask a question..." : "Load a scenario first..."}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send(draft);
                }
              }}
              disabled={!scenario || sending}
            />
            <button
              className="btn btn-primary"
              onClick={() => void send(draft)}
              disabled={!scenario || !draft.trim() || sending}
            >
              Send
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function MessageBubble({ turn }: { turn: DisplayTurn }) {
  if (turn.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap bg-accent/15 text-ink border border-accent/20">
          {turn.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[92%] space-y-2">
        {(turn.persona || turn.source) ? (
          <div className="flex items-center gap-2 text-[0.65rem] uppercase tracking-[0.14em]">
            {turn.persona ? (
              <span className="text-accent font-bold">{PERSONA_LABEL[turn.persona]}</span>
            ) : null}
            {turn.source ? (
              <span className="text-muted">via {SOURCE_LABEL[turn.source]}</span>
            ) : null}
          </div>
        ) : null}

        <div className="rounded-2xl px-4 py-3 text-sm leading-relaxed bg-white/5 text-ink border border-line markdown-body">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD_COMPONENTS}>
            {turn.content}
          </ReactMarkdown>
        </div>

        {turn.tool_calls && turn.tool_calls.length > 0 ? (
          <StructuredOutputs calls={turn.tool_calls} />
        ) : null}

        {turn.tool_calls && turn.tool_calls.length > 0 ? (
          <ToolCallList calls={turn.tool_calls} />
        ) : null}
      </div>
    </div>
  );
}

// --- Markdown renderer overrides -------------------------------------------

const MD_COMPONENTS = {
  // GFM tables: scrollable wrapper + tight typography
  table: (props: any) => (
    <div className="my-3 overflow-x-auto rounded border border-line">
      <table className="w-full text-xs border-collapse" {...props} />
    </div>
  ),
  thead: (props: any) => <thead className="bg-white/[0.04]" {...props} />,
  th: (props: any) => (
    <th
      className="text-left font-semibold text-ink px-3 py-1.5 border-b border-line text-[0.65rem] uppercase tracking-[0.06em]"
      {...props}
    />
  ),
  td: (props: any) => <td className="px-3 py-1.5 border-b border-line/40 align-top" {...props} />,
  tr: (props: any) => <tr {...props} />,
  // Headings: smaller in chat context
  h1: (props: any) => <h3 className="text-base font-semibold text-ink mt-3 mb-1" {...props} />,
  h2: (props: any) => <h4 className="text-sm font-semibold text-ink mt-3 mb-1" {...props} />,
  h3: (props: any) => <h4 className="text-sm font-semibold text-ink mt-2 mb-1" {...props} />,
  h4: (props: any) => <div className="text-[0.7rem] font-bold text-accent uppercase tracking-[0.1em] mt-3 mb-1" {...props} />,
  // Lists
  ul: (props: any) => <ul className="list-disc pl-5 space-y-0.5 my-1" {...props} />,
  ol: (props: any) => <ol className="list-decimal pl-5 space-y-0.5 my-1" {...props} />,
  li: (props: any) => <li className="text-ink" {...props} />,
  // Inline code + code blocks
  code: ({ inline, ...props }: any) =>
    inline ? (
      <code className="font-mono text-[0.78em] bg-white/10 rounded px-1 py-0.5" {...props} />
    ) : (
      <pre className="my-2 text-[0.72rem] bg-black/40 rounded p-2 overflow-x-auto">
        <code className="font-mono" {...props} />
      </pre>
    ),
  p: (props: any) => <p className="my-1.5" {...props} />,
  strong: (props: any) => <strong className="text-ink font-semibold" {...props} />,
  em: (props: any) => <em className="text-muted" {...props} />,
  a: (props: any) => <a className="text-accent underline" {...props} />,
};

// --- Structured table renderers --------------------------------------------

function StructuredOutputs({ calls }: { calls: ToolCallRecord[] }) {
  return (
    <>
      {calls.map((c, i) => {
        const preview = c.output_preview as any;
        if (!preview) return null;

        // Weekly plan: render the items array as a table
        if (c.tool === "build_weekly_plan" && Array.isArray(preview?.items) && preview.items.length > 0) {
          return <WeeklyPlanTable key={i} items={preview.items} />;
        }
        // Expediting queue: items array
        if (c.tool === "get_expedite_queue" && Array.isArray(preview?.items) && preview.items.length > 0) {
          return <ExpediteTable key={i} items={preview.items} />;
        }
        // Vendor list
        if (c.tool === "list_vendors" && Array.isArray(preview) && preview.length > 0) {
          return <VendorTable key={i} rows={preview} />;
        }
        // Top risks
        if (c.tool === "get_top_risks" && Array.isArray(preview) && preview.length > 0) {
          return <RisksTable key={i} rows={preview} />;
        }
        // Open RFQs / PRs
        if ((c.tool === "get_open_rfqs" || c.tool === "get_open_prs") && Array.isArray(preview) && preview.length > 0) {
          return <SourcingTable key={i} tool={c.tool} rows={preview} />;
        }
        return null;
      })}
    </>
  );
}

function StructTable({ title, columns, rows }: { title: string; columns: { key: string; label: string; cls?: string; render?: (r: any) => any }[]; rows: any[] }) {
  return (
    <div className="rounded-xl border border-accent/20 bg-accent/[0.04] p-3">
      <div className="text-[0.65rem] uppercase tracking-[0.14em] text-accent font-bold mb-2">{title}</div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="bg-white/[0.04]">
              {columns.map((c) => (
                <th key={c.key} className={`text-left font-semibold text-ink px-2.5 py-1.5 border-b border-line text-[0.65rem] uppercase tracking-[0.06em] ${c.cls ?? ""}`}>
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, idx) => (
              <tr key={idx} className="border-b border-line/40 hover:bg-white/[0.02]">
                {columns.map((c) => (
                  <td key={c.key} className={`px-2.5 py-1.5 align-top ${c.cls ?? ""}`}>
                    {c.render ? c.render(r) : (r[c.key] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function priorityPill(p: string) {
  const cls = p === "P1" ? "bg-rose-500/20 text-rose-300" : p === "P2" ? "bg-amber-500/20 text-amber-300" : "bg-sky-500/20 text-sky-300";
  return <span className={`inline-block rounded px-1.5 py-0.5 text-[0.6rem] font-bold ${cls}`}>{p}</span>;
}

function severityPill(s: string) {
  const cls =
    s === "critical" ? "bg-rose-500/25 text-rose-300" :
    s === "high"     ? "bg-amber-500/25 text-amber-300" :
    s === "medium"   ? "bg-sky-500/25 text-sky-300" :
                       "bg-zinc-500/20 text-zinc-300";
  return <span className={`inline-block rounded px-1.5 py-0.5 text-[0.6rem] font-bold uppercase ${cls}`}>{s}</span>;
}

function WeeklyPlanTable({ items }: { items: any[] }) {
  return (
    <StructTable
      title={`Weekly plan — ${items.length} actions`}
      columns={[
        { key: "priority", label: "Pri", render: (r) => priorityPill(r.priority) },
        { key: "category", label: "Cat" },
        { key: "title", label: "Action", cls: "text-ink font-medium" },
        { key: "owner", label: "Owner" },
        { key: "due_in_days", label: "Due", render: (r) => `${r.due_in_days}d` },
        { key: "confidence", label: "Conf", render: (r) => `${r.confidence}%` },
        { key: "why", label: "Why", cls: "text-muted max-w-[220px]" },
        { key: "expected_impact", label: "Impact", cls: "text-muted max-w-[220px]" },
        { key: "supporting_refs", label: "Refs", cls: "text-muted font-mono text-[0.65rem]", render: (r) => (r.supporting_refs || []).join(", ") },
      ]}
      rows={items}
    />
  );
}

function ExpediteTable({ items }: { items: any[] }) {
  const urgencyColor: Record<string, string> = {
    escalate: "text-rose-300",
    nudge: "text-amber-300",
    watch: "text-sky-300",
    ok: "text-emerald-300",
  };
  return (
    <StructTable
      title={`Expediting queue — ${items.length} POs`}
      columns={[
        { key: "po_number", label: "PO", cls: "font-mono" },
        { key: "supplier_name", label: "Supplier", cls: "text-ink" },
        { key: "due_in_days", label: "Due", render: (r) => `${r.due_in_days}d` },
        { key: "predicted_slip_days", label: "Slip", render: (r) => `${r.predicted_slip_days}d` },
        { key: "slip_probability_pct", label: "Prob", render: (r) => `${r.slip_probability_pct}%` },
        { key: "urgency", label: "Urgency", render: (r) => <span className={`font-bold uppercase text-[0.65rem] ${urgencyColor[r.urgency] || ""}`}>{r.urgency}</span> },
        { key: "value_usd", label: "Value", render: (r) => `$${Math.round(r.value_usd).toLocaleString()}` },
      ]}
      rows={items}
    />
  );
}

function VendorTable({ rows }: { rows: any[] }) {
  return (
    <StructTable
      title={`Vendors — ${rows.length}`}
      columns={[
        { key: "vendor", label: "Vendor", cls: "text-ink" },
        { key: "category", label: "Category" },
        { key: "country", label: "Country" },
        { key: "composite_score", label: "Score" },
        { key: "composite_grade", label: "Grade" },
        { key: "on_time_delivery_pct", label: "OTD%", render: (r) => `${r.on_time_delivery_pct}%` },
        { key: "annual_spend_usd", label: "Spend", render: (r) => `$${Math.round(r.annual_spend_usd).toLocaleString()}` },
        { key: "flags_count", label: "Flags" },
      ]}
      rows={rows.slice(0, 25)}
    />
  );
}

function RisksTable({ rows }: { rows: any[] }) {
  return (
    <StructTable
      title={`Top risks — ${rows.length}`}
      columns={[
        { key: "severity", label: "Sev", render: (r) => severityPill(r.severity) },
        { key: "risk_type", label: "Type" },
        { key: "score", label: "Score" },
        { key: "title", label: "Title", cls: "text-ink" },
        { key: "supplier_name", label: "Supplier" },
        { key: "owner", label: "Owner" },
      ]}
      rows={rows}
    />
  );
}

function SourcingTable({ tool, rows }: { tool: string; rows: any[] }) {
  const isPr = tool === "get_open_prs";
  return (
    <StructTable
      title={isPr ? `Open PRs — ${rows.length}` : `Open RFQs — ${rows.length}`}
      columns={
        isPr
          ? [
              { key: "pr_no", label: "PR", cls: "font-mono" },
              { key: "code", label: "Code" },
              { key: "description", label: "Description", cls: "text-ink" },
              { key: "quantity", label: "Qty" },
              { key: "buyer", label: "Buyer" },
              { key: "status", label: "Status" },
              { key: "need_by", label: "Need by" },
            ]
          : [
              { key: "rfq_no", label: "RFQ", cls: "font-mono" },
              { key: "code", label: "Code" },
              { key: "description", label: "Description", cls: "text-ink" },
              { key: "vendors", label: "Vendors", render: (r) => (r.vendors || []).length },
              { key: "due_at", label: "Due" },
              { key: "status", label: "Status" },
            ]
      }
      rows={rows}
    />
  );
}

function ToolCallList({ calls }: { calls: ToolCallRecord[] }) {
  return (
    <div className="space-y-1.5">
      {calls.map((c, i) => (
        <ToolCallBlock key={i} call={c} />
      ))}
    </div>
  );
}

function ToolCallBlock({ call }: { call: ToolCallRecord }) {
  const [open, setOpen] = useState(false);
  const hasPreview = call.output_preview !== null && call.output_preview !== undefined;
  return (
    <div className="panel-sm text-xs">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 text-left hover:opacity-85"
      >
        <span className="font-mono text-accent">{call.tool}</span>
        {Object.keys(call.input).length > 0 ? (
          <span className="font-mono text-muted truncate">{JSON.stringify(call.input)}</span>
        ) : null}
        <span className="flex-1 text-ink truncate">{call.output_summary}</span>
        {hasPreview ? (
          <span className="text-muted text-[0.6rem] shrink-0">{open ? "hide" : "data"}</span>
        ) : null}
      </button>
      {open && hasPreview ? (
        <pre className="mt-2 text-[0.7rem] text-muted max-h-64 overflow-auto font-mono bg-black/30 rounded-md p-2 whitespace-pre-wrap break-all">
          {JSON.stringify(call.output_preview, null, 2)}
        </pre>
      ) : null}
    </div>
  );
}
