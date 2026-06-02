import { useCallback, useRef, useState } from "react";
import { api } from "../services/api";
import type { AnalysisModePreference, AnalysisResponse } from "../types";

export type AnalysisStatus = "idle" | "loading" | "success" | "error";

export function useAnalysis() {
  const [status, setStatus] = useState<AnalysisStatus>("idle");
  const [result, setResult] = useState<AnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastQuery, setLastQuery] = useState("");
  const [lastMode, setLastMode] = useState<AnalysisModePreference>("auto");
  const abortRef = useRef<AbortController | null>(null);

  const execute = useCallback(
    async (query: string, analysisMode: AnalysisModePreference = "auto") => {
      const trimmed = query.trim();
      if (!trimmed) {
        return;
      }

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setLastQuery(trimmed);
      setLastMode(analysisMode);
      setStatus("loading");
      setError(null);
      setResult(null);

      try {
        const response = await api.analyze(trimmed, analysisMode, controller.signal);
        if (controller.signal.aborted) {
          return;
        }
        setResult(response);
        setStatus("success");
      } catch (err) {
        if (controller.signal.aborted) {
          return;
        }
        setError(err instanceof Error ? err.message : "分析失败，请稍后重试");
        setStatus("error");
      }
    },
    []
  );

  const retry = useCallback(() => {
    if (lastQuery) {
      void execute(lastQuery, lastMode);
    }
  }, [execute, lastQuery, lastMode]);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setStatus("idle");
    setError(null);
    setResult(null);
  }, []);

  return { status, result, error, lastQuery, execute, retry, reset };
}
