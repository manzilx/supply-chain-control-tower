"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { fetchAiStatus, sendChat, streamChat } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { AiStatus, ChatReply, ChatTurn } from "@/lib/types";

// Page-aware starter prompts.
function suggestionsFor(path: string): string[] {
  if (path.startsWith("/projects")) {
    return [
      "Which projects are most behind schedule?",
      "Summarise long-lead risk across my projects",
      "What BOM lines are missing specs?",
    ];
  }
  if (path.startsWith("/vendors")) {
    return [
      "Which vendors are single-source?",
      "Rank my vendors by composite score",
      "Where is my spend most concentrated?",
      "Propose onboarding a new backup vendor for valves",
    ];
  }
  if (path.startsWith("/sourcing") || path.startsWith("/approvals")) {
    return [
      "Show me open PRs",
      "What's awaiting approval?",
      "Which RFQs still need quotes?",
    ];
  }
  if (path.startsWith("/commercial")) {
    return [
      "Where am I over budget?",
      "Total committed spend this quarter?",
      "Biggest savings opportunities?",
    ];
  }
  if (path.startsWith("/expediting") || path.startsWith("/logistics")) {
    return [
      "Which POs are most likely to slip?",
      "What shipments are at a bottleneck?",
      "Draft a follow-up for the worst PO",
    ];
  }
  return [
    "What needs my attention today?",
    "Summarise portfolio health",
    "What are my top 3 supply-chain risks?",
  ];
}

const SOURCE_LABEL: Record<string, string> = {
  grok: "Grok",
  claude: "Claude",
  openai: "OpenAI",
  deterministic: "Rule-based",
};

export function Copilot() {
  const { status } = useAuth();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [history, setHistory] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [activity, setActivity] = useState<string | null>(null);
  const [lastSource, setLastSource] = useState<string | null>(null);
  const [aiStatus, setAiStatus] = useState<AiStatus | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open || status !== "authed") return;
    fetchAiStatus().then(setAiStatus).catch(() => {});
  }, [open, status]);

  useEffect(() => {
    const toggle = () => setOpen((v) => !v);
    window.addEventListener("copilot:toggle", toggle);
    return () => window.removeEventListener("copilot:toggle", toggle);
  }, []);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "j") {
        e.preventDefault();
        setOpen((v) => !v);
      } else if (e.key === "Escape" && open) {
        setOpen(false);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 50);
  }, [open]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [history, busy]);

  if (status !== "authed") return null;

  async function ask(message: string) {
    const text = message.trim();
    if (!text || busy) return;
    const userTurn: ChatTurn = { role: "user", content: text };
    const nextHistory = [...history, userTurn];
    setHistory(nextHistory);
    setInput("");
    setBusy(true);
    setActivity(null);

    const applyReply = (reply: ChatReply) => {
      setLastSource(reply.source);
      setHistory([
        ...nextHistory,
        { role: "assistant", content: reply.reply, tool_calls: reply.tool_calls },
      ]);
    };

    try {
      // Streaming path — live status + tool events while the agent works.
      await streamChat(
        { message: text, history, page: pathname },
        {
          onStatus: () => setActivity("thinking…"),
          onTool: (tool) => setActivity(`⚙ ${tool.replace(/_/g, " ")}…`),
          onReply: applyReply,
        },
      );
    } catch {
      // Stream unavailable (proxy buffering, old backend) — plain POST fallback.
      try {
        const reply = await sendChat({ message: text, history, page: pathname });
        applyReply(reply);
      } catch (err) {
        setHistory([
          ...nextHistory,
          {
            role: "assistant",
            content: err instanceof Error ? `⚠️ ${err.message}` : "Something went wrong.",
          },
        ]);
      }
    } finally {
      setBusy(false);
      setActivity(null);
    }
  }

  const suggestions = suggestionsFor(pathname);

  return (
    <>
      {/* Floating launcher */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="fixed bottom-5 right-5 z-[70] flex items-center gap-2 h-12 px-4 rounded-full shadow-glow bg-gradient-to-r from-accent-strong to-accent text-bg font-bold hover:brightness-110 transition-all"
        aria-label="Open AI Copilot (⌘J)"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
          <path d="M12 3l1.9 4.6L18.5 9l-4.6 1.9L12 15.5 10.1 10.9 5.5 9l4.6-1.4L12 3z" />
        </svg>
        <span className="hidden sm:inline">Copilot</span>
      </button>

      {open ? (
        <div className="fixed inset-0 z-[71] flex justify-end" onClick={() => setOpen(false)}>
          <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px]" />
          <div
            className="relative w-[min(440px,100vw)] h-full bg-surface border-l border-line shadow-panel flex flex-col animate-[slide-in_0.25s_ease-out]"
            onClick={(e) => e.stopPropagation()}
            style={{ animationName: "slide-in" }}
          >
            <div className="px-4 py-3 border-b border-line flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-accent-strong to-accent flex items-center justify-center text-bg">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                    <path d="M12 3l1.9 4.6L18.5 9l-4.6 1.9L12 15.5 10.1 10.9 5.5 9l4.6-1.4L12 3z" />
                  </svg>
                </div>
                <div>
                  <div className="text-base font-bold leading-none flex items-center gap-1.5">
                    Copilot
                    {aiStatus ? (
                      <span
                        className={`w-1.5 h-1.5 rounded-full ${aiStatus.enabled ? "bg-accent" : "bg-muted"}`}
                        title={
                          aiStatus.enabled
                            ? `${aiStatus.model} · ${aiStatus.stats.calls} calls · last ${aiStatus.stats.last_latency_ms ?? "—"}ms`
                            : "Deterministic fallback (no XAI_API_KEY)"
                        }
                      />
                    ) : null}
                  </div>
                  <div className="text-[0.6rem] uppercase tracking-[0.1em] text-muted mt-0.5">
                    {lastSource
                      ? `via ${SOURCE_LABEL[lastSource] ?? lastSource}`
                      : aiStatus?.enabled
                        ? aiStatus.model
                        : aiStatus
                          ? "rule-based mode"
                          : ""}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {history.length ? (
                  <button onClick={() => setHistory([])} className="text-xs text-muted hover:text-ink">
                    Clear
                  </button>
                ) : null}
                <button onClick={() => setOpen(false)} className="text-muted hover:text-ink" aria-label="Close">
                  ✕
                </button>
              </div>
            </div>

            <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
              {history.length === 0 ? (
                <div className="text-sm text-muted">
                  <p className="mt-0">
                    Ask anything about your procurement data — projects, vendors, sourcing, risk. I can call
                    live tools to answer.
                  </p>
                  <div className="text-[0.65rem] uppercase tracking-[0.12em] text-muted font-bold mt-4 mb-2">
                    Try
                  </div>
                  <div className="space-y-2">
                    {suggestions.map((s) => (
                      <button
                        key={s}
                        onClick={() => void ask(s)}
                        className="block w-full text-left text-sm panel-sm hover:border-accent/50 transition-colors"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                history.map((t, i) => (
                  <div key={i} className={t.role === "user" ? "flex justify-end" : "flex justify-start"}>
                    <div
                      className={[
                        "max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed whitespace-pre-wrap",
                        t.role === "user"
                          ? "bg-accent/15 text-ink rounded-br-sm"
                          : "bg-white/[0.04] text-ink rounded-bl-sm",
                      ].join(" ")}
                    >
                      {t.content}
                      {t.tool_calls && t.tool_calls.length ? (
                        <div className="mt-2 pt-2 border-t border-line/60 text-[0.65rem] text-muted">
                          ⚙ used {t.tool_calls.length} tool{t.tool_calls.length > 1 ? "s" : ""}:{" "}
                          {t.tool_calls.map((tc) => tc.tool).join(", ")}
                        </div>
                      ) : null}
                    </div>
                  </div>
                ))
              )}
              {busy ? (
                <div className="flex justify-start">
                  <div className="bg-white/[0.04] rounded-2xl rounded-bl-sm px-3.5 py-2.5">
                    <span className="inline-flex items-center gap-2">
                      <span className="inline-flex gap-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-muted animate-pulse" />
                        <span className="w-1.5 h-1.5 rounded-full bg-muted animate-pulse [animation-delay:0.2s]" />
                        <span className="w-1.5 h-1.5 rounded-full bg-muted animate-pulse [animation-delay:0.4s]" />
                      </span>
                      {activity ? (
                        <span className="text-[0.7rem] text-muted italic">{activity}</span>
                      ) : null}
                    </span>
                  </div>
                </div>
              ) : null}
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                void ask(input);
              }}
              className="border-t border-line p-3 flex gap-2"
            >
              <input
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask the copilot…"
                className="flex-1"
                disabled={busy}
              />
              <button type="submit" className="btn btn-primary" disabled={busy || !input.trim()}>
                Send
              </button>
            </form>
          </div>
        </div>
      ) : null}
    </>
  );
}
