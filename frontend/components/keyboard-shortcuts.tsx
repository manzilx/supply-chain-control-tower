"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { useAuth } from "@/lib/auth-context";
import { navShortcutMap, navShortcuts } from "@/lib/nav";

function isTyping(el: EventTarget | null): boolean {
  const node = el as HTMLElement | null;
  if (!node) return false;
  const tag = node.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || node.isContentEditable;
}

export function KeyboardShortcuts() {
  const router = useRouter();
  const { status } = useAuth();
  const [help, setHelp] = useState(false);
  const [pendingG, setPendingG] = useState(false);
  const nav = useMemo(() => navShortcutMap(), []);
  const shortcuts = useMemo(() => navShortcuts(), []);

  useEffect(() => {
    let gTimer: ReturnType<typeof setTimeout> | undefined;

    function onKey(e: KeyboardEvent) {
      if (isTyping(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;

      if (e.key === "?") {
        e.preventDefault();
        setHelp((v) => !v);
        return;
      }
      if (e.key === "Escape") {
        setHelp(false);
        setPendingG(false);
        return;
      }
      // Copilot quick-open
      if (e.key === "i" && !pendingG) {
        window.dispatchEvent(new CustomEvent("copilot:toggle"));
        return;
      }
      if (e.key === "g") {
        setPendingG(true);
        clearTimeout(gTimer);
        gTimer = setTimeout(() => setPendingG(false), 1400);
        return;
      }
      if (pendingG) {
        const target = nav[e.key.toLowerCase()];
        setPendingG(false);
        clearTimeout(gTimer);
        if (target) {
          e.preventDefault();
          router.push(target.href);
        }
      }
    }

    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      clearTimeout(gTimer);
    };
  }, [nav, pendingG, router]);

  if (status !== "authed") return null;

  return (
    <>
      {pendingG ? (
        <div className="fixed bottom-5 left-5 z-[110] panel-sm text-xs text-muted animate-fade-up">
          <span className="text-accent font-bold">g</span> then a key — press{" "}
          <span className="text-ink font-bold">?</span> for the map
        </div>
      ) : null}

      {help ? (
        <div
          className="fixed inset-0 z-[130] flex items-center justify-center bg-black/55 backdrop-blur-sm animate-fade-up p-4"
          onClick={() => setHelp(false)}
        >
          <div className="panel w-[min(560px,100%)]" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <div>
                <div className="text-[0.65rem] uppercase tracking-[0.14em] text-accent font-bold">Help</div>
                <h2 className="m-0 text-xl font-bold">Keyboard shortcuts</h2>
              </div>
              <button onClick={() => setHelp(false)} className="text-muted hover:text-ink">✕</button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-2">
              <Shortcut keys={["⌘", "K"]} label="Command palette / search" />
              <Shortcut keys={["⌘", "J"]} label="Toggle AI Copilot" />
              <Shortcut keys={["i"]} label="Toggle AI Copilot" />
              <Shortcut keys={["?"]} label="This help" />
              <div className="sm:col-span-2 text-[0.65rem] uppercase tracking-[0.14em] text-muted font-bold mt-3 mb-1">
                Go to (press g, then…)
              </div>
              {shortcuts.map(({ key, label }) => (
                <Shortcut key={key} keys={["g", key]} label={label} />
              ))}
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}

function Shortcut({ keys, label }: { keys: string[]; label: string }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1">
      <span className="text-sm text-ink">{label}</span>
      <span className="flex gap-1 shrink-0">
        {keys.map((k, i) => (
          <kbd
            key={i}
            className="text-[0.65rem] uppercase tracking-[0.05em] text-muted border border-line rounded px-1.5 py-0.5 font-mono bg-white/[0.03]"
          >
            {k}
          </kbd>
        ))}
      </span>
    </div>
  );
}
