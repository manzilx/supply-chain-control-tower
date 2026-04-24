"use client";

import { useEffect, useRef, useState } from "react";

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

        <div className="rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap bg-white/5 text-ink border border-line">
          {turn.content}
        </div>

        {turn.tool_calls && turn.tool_calls.length > 0 ? (
          <ToolCallList calls={turn.tool_calls} />
        ) : null}
      </div>
    </div>
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
