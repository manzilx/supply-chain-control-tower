"use client";

import { createContext, useCallback, useContext, useRef, useState } from "react";

export type ToastKind = "success" | "error" | "info" | "warn";

export type Toast = {
  id: number;
  kind: ToastKind;
  message: string;
  action?: { label: string; href: string };
};

type ToastApi = {
  toast: (message: string, opts?: { kind?: ToastKind; action?: Toast["action"]; ttl?: number }) => void;
  success: (message: string, action?: Toast["action"]) => void;
  error: (message: string) => void;
  info: (message: string, action?: Toast["action"]) => void;
  warn: (message: string, action?: Toast["action"]) => void;
};

const Ctx = createContext<ToastApi | null>(null);

let _seq = 0;

const TONE: Record<ToastKind, { ring: string; dot: string }> = {
  success: { ring: "border-accent/40", dot: "bg-accent" },
  error: { ring: "border-danger/40", dot: "bg-danger" },
  info: { ring: "border-steady/40", dot: "bg-steady" },
  warn: { ring: "border-warning/40", dot: "bg-warning" },
};

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timers = useRef<Record<number, ReturnType<typeof setTimeout>>>({});

  const remove = useCallback((id: number) => {
    setToasts((t) => t.filter((x) => x.id !== id));
    const tm = timers.current[id];
    if (tm) {
      clearTimeout(tm);
      delete timers.current[id];
    }
  }, []);

  const toast = useCallback<ToastApi["toast"]>((message, opts = {}) => {
    const id = ++_seq;
    const kind = opts.kind ?? "info";
    setToasts((t) => [...t, { id, kind, message, action: opts.action }].slice(-4));
    timers.current[id] = setTimeout(() => remove(id), opts.ttl ?? 5000);
  }, [remove]);

  const api: ToastApi = {
    toast,
    success: (m, action) => toast(m, { kind: "success", action }),
    error: (m) => toast(m, { kind: "error", ttl: 7000 }),
    info: (m, action) => toast(m, { kind: "info", action }),
    warn: (m, action) => toast(m, { kind: "warn", action }),
  };

  return (
    <Ctx.Provider value={api}>
      {children}
      <div className="fixed bottom-20 right-5 z-[120] flex flex-col gap-2 w-[min(380px,calc(100vw-2.5rem))]">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`panel-sm border ${TONE[t.kind].ring} shadow-panel animate-fade-up flex items-start gap-3`}
            role="status"
          >
            <span className={`mt-1.5 w-2 h-2 rounded-full shrink-0 ${TONE[t.kind].dot}`} />
            <div className="min-w-0 flex-1">
              <div className="text-sm text-ink">{t.message}</div>
              {t.action ? (
                <a href={t.action.href} className="text-xs text-accent hover:text-accent-strong mt-1 inline-block">
                  {t.action.label} →
                </a>
              ) : null}
            </div>
            <button
              onClick={() => remove(t.id)}
              className="text-muted hover:text-ink text-xs shrink-0"
              aria-label="Dismiss"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

export function useToast(): ToastApi {
  const ctx = useContext(Ctx);
  if (!ctx) {
    // No-op fallback so components don't crash outside the provider (SSR edge).
    return {
      toast: () => {},
      success: () => {},
      error: () => {},
      info: () => {},
      warn: () => {},
    };
  }
  return ctx;
}
