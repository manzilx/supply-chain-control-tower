"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { analyzeScenario, fetchDemoScenario } from "@/lib/api";
import type { AgentRequest, AgentResponse } from "@/lib/types";

type Status = "idle" | "loading" | "analyzing" | "error";

type StoreValue = {
  scenario: AgentRequest | null;
  analysis: AgentResponse | null;
  status: Status;
  error: string | null;
  loadDemo: () => Promise<void>;
  analyze: () => Promise<void>;
  setScenario: (next: AgentRequest) => void;
  lastAnalyzedAt: string | null;
};

const StoreContext = createContext<StoreValue | null>(null);

const SCENARIO_KEY = "sct.scenario.v1";
const ANALYSIS_KEY = "sct.analysis.v1";

function readSession<T>(key: string): T | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function writeSession(key: string, value: unknown): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    // ignore quota/serialization errors
  }
}

export function StoreProvider({ children }: { children: ReactNode }) {
  const [scenario, setScenarioState] = useState<AgentRequest | null>(null);
  const [analysis, setAnalysis] = useState<AgentResponse | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const bootstrapped = useRef(false);

  useEffect(() => {
    if (bootstrapped.current) return;
    bootstrapped.current = true;

    const cachedScenario = readSession<AgentRequest>(SCENARIO_KEY);
    const cachedAnalysis = readSession<AgentResponse>(ANALYSIS_KEY);

    if (cachedScenario) {
      setScenarioState(cachedScenario);
      if (cachedAnalysis) setAnalysis(cachedAnalysis);
      return;
    }

    setStatus("loading");
    fetchDemoScenario()
      .then((demo) => {
        setScenarioState(demo);
        writeSession(SCENARIO_KEY, demo);
        setStatus("idle");
        return analyzeScenario(demo);
      })
      .then((result) => {
        if (!result) return;
        setAnalysis(result);
        writeSession(ANALYSIS_KEY, result);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Failed to bootstrap scenario.");
        setStatus("error");
      });
  }, []);

  const setScenario = useCallback((next: AgentRequest) => {
    setScenarioState(next);
    writeSession(SCENARIO_KEY, next);
  }, []);

  const loadDemo = useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      const demo = await fetchDemoScenario();
      setScenarioState(demo);
      writeSession(SCENARIO_KEY, demo);
      setAnalysis(null);
      window.sessionStorage.removeItem(ANALYSIS_KEY);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load demo scenario.");
      setStatus("error");
      return;
    }
    setStatus("idle");
  }, []);

  const analyze = useCallback(async () => {
    if (!scenario) return;
    setStatus("analyzing");
    setError(null);
    try {
      const result = await analyzeScenario(scenario);
      setAnalysis(result);
      writeSession(ANALYSIS_KEY, result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed.");
      setStatus("error");
      return;
    }
    setStatus("idle");
  }, [scenario]);

  const value = useMemo<StoreValue>(
    () => ({
      scenario,
      analysis,
      status,
      error,
      loadDemo,
      analyze,
      setScenario,
      lastAnalyzedAt: analysis?.generated_at ?? null,
    }),
    [scenario, analysis, status, error, loadDemo, analyze, setScenario],
  );

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

export function useStore(): StoreValue {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error("useStore must be used inside <StoreProvider>");
  return ctx;
}
