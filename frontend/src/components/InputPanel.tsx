import { useEffect, useRef, useState } from "react";
import { api } from "../services/api";
import type {
  AnalysisModePreference,
  AnalysisRecommendation,
  DataSummary,
} from "../types";

const MODE_OPTIONS: {
  id: AnalysisModePreference;
  label: string;
  hint: string;
}[] = [
  {
    id: "auto",
    label: "智能",
    hint: "意图明确时精准分析，模糊时自动探索",
  },
  {
    id: "precise",
    label: "精准",
    hint: "只执行 LLM 选定的单一分析",
  },
  {
    id: "exploratory",
    label: "探索",
    hint: "全量运行当前数据支持的所有分析",
  },
];

const MODE_LABEL: Record<AnalysisModePreference, string> = {
  auto: "智能",
  precise: "精准",
  exploratory: "探索",
};

function formatDataSummary(summary: DataSummary | null): string {
  if (!summary) {
    return "";
  }
  const parts: string[] = [];
  if (summary.events?.length) {
    parts.push(summary.events[0].name);
  }
  if (summary.unique_vins != null) {
    parts.push(`${summary.unique_vins.toLocaleString()} 车辆`);
  }
  if (summary.date_range) {
    parts.push(`${summary.date_range.span_days} 天数据`);
  }
  parts.push(`${summary.total_rows.toLocaleString()} 条记录`);
  return parts.join(" · ");
}

interface InputPanelProps {
  onSubmit: (query: string, mode: AnalysisModePreference) => void;
  disabled?: boolean;
}

export default function InputPanel({ onSubmit, disabled = false }: InputPanelProps) {
  const [query, setQuery] = useState("");
  const [analysisMode, setAnalysisMode] = useState<AnalysisModePreference>("auto");
  const [showRecommendations, setShowRecommendations] = useState(false);
  const [recommendations, setRecommendations] = useState<AnalysisRecommendation[]>([]);
  const [dataSummary, setDataSummary] = useState<DataSummary | null>(null);
  const [recLoading, setRecLoading] = useState(false);
  const [recError, setRecError] = useState<string | null>(null);
  const [recSource, setRecSource] = useState<"llm" | "fallback" | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(event.target as Node)) {
        setShowRecommendations(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const loadRecommendations = async () => {
    if (recLoading) {
      return;
    }
    setRecLoading(true);
    setRecError(null);
    try {
      const data = await api.getRecommendations();
      setRecommendations(data.recommendations);
      setDataSummary(data.data_summary);
      setRecSource(data.source);
    } catch (err) {
      setRecError(err instanceof Error ? err.message : "加载分析推荐失败");
    } finally {
      setRecLoading(false);
    }
  };

  const handleFocus = () => {
    setShowRecommendations(true);
    void loadRecommendations();
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!query.trim() || disabled) {
      return;
    }
    setShowRecommendations(false);
    onSubmit(query, analysisMode);
  };

  const handlePickRecommendation = (rec: AnalysisRecommendation) => {
    setQuery(rec.query);
    setAnalysisMode(rec.analysis_mode);
    setShowRecommendations(false);
  };

  const activeHint = MODE_OPTIONS.find((m) => m.id === analysisMode)?.hint ?? "";
  const summaryText = formatDataSummary(dataSummary);

  return (
    <div
      ref={panelRef}
      className={`glass-panel relative p-5 ${showRecommendations ? "z-50" : ""}`}
    >
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="flex gap-3">
          <input
            type="text"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onFocus={handleFocus}
            placeholder="例如：蓝牙连接的近30天每日使用趋势"
            disabled={disabled}
            className="flex-1 rounded-lg border border-slate-200/80 bg-white/70 px-4 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-cyan-600 focus:outline-none focus:ring-2 focus:ring-cyan-600/20 disabled:bg-slate-50 disabled:text-slate-400"
          />
          <button
            type="submit"
            disabled={disabled || !query.trim()}
            className="rounded-lg bg-gradient-to-r from-cyan-600 to-violet-600 px-5 py-2.5 text-sm font-medium text-white transition hover:from-cyan-700 hover:to-violet-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {disabled ? "分析中..." : "开始分析"}
          </button>
        </div>

        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div
            className="inline-flex rounded-lg border border-gray-200 bg-gray-50 p-0.5"
            role="group"
            aria-label="分析模式"
          >
            {MODE_OPTIONS.map((option) => {
              const selected = analysisMode === option.id;
              return (
                <button
                  key={option.id}
                  type="button"
                  disabled={disabled}
                  onClick={() => setAnalysisMode(option.id)}
                  className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
                    selected
                      ? "bg-white text-blue-700 shadow-sm"
                      : "text-gray-600 hover:text-gray-900"
                  } disabled:cursor-not-allowed disabled:opacity-50`}
                >
                  {option.label}
                </button>
              );
            })}
          </div>
          <p className="text-xs text-gray-500">{activeHint}</p>
        </div>
      </form>

      {showRecommendations && (
        <div className="absolute left-0 right-0 top-full z-[100] mt-2 max-h-80 overflow-y-auto rounded-xl border border-slate-200/90 bg-white/95 shadow-2xl backdrop-blur-md">
          <div className="sticky top-0 border-b border-gray-100 bg-gray-50 px-4 py-2.5">
            <div className="flex items-center justify-between gap-2">
              <p className="text-xs font-medium text-gray-700">智能分析推荐</p>
              {recSource === "llm" && (
                <span className="rounded bg-blue-50 px-1.5 py-0.5 text-[10px] text-blue-600">
                  AI 生成
                </span>
              )}
            </div>
            {summaryText && (
              <p className="mt-0.5 text-[11px] text-gray-400">{summaryText}</p>
            )}
          </div>

          {recLoading && (
            <p className="px-4 py-4 text-sm text-gray-400">正在基于数据生成推荐...</p>
          )}
          {recError && (
            <p className="px-4 py-4 text-sm text-red-500">{recError}</p>
          )}
          {!recLoading &&
            !recError &&
            recommendations.map((rec) => (
              <button
                key={`${rec.title}-${rec.query}`}
                type="button"
                onClick={() => handlePickRecommendation(rec)}
                className="flex w-full flex-col gap-1 border-b border-gray-50 px-4 py-3 text-left transition last:border-0 hover:bg-blue-50/50"
              >
                <div className="flex items-center gap-2">
                  <span className="rounded bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-700">
                    {rec.title}
                  </span>
                  <span className="text-[10px] text-gray-400">
                    {MODE_LABEL[rec.analysis_mode]}模式
                  </span>
                </div>
                <p className="text-sm text-gray-800">{rec.query}</p>
                <p className="text-xs text-gray-400">{rec.reason}</p>
              </button>
            ))}
        </div>
      )}
    </div>
  );
}
