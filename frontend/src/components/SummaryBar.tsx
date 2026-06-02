import type { ExecutionSummary } from "../types";

interface SummaryBarProps {
  execution: ExecutionSummary;
}

function formatDuration(ms: number): string {
  if (ms < 1000) {
    return `${ms} ms`;
  }
  return `${(ms / 1000).toFixed(1)} s`;
}

export default function SummaryBar({ execution }: SummaryBarProps) {
  const items = [
    { label: "总行数", value: execution.total_rows.toLocaleString() },
    { label: "过滤后", value: execution.filtered_rows.toLocaleString() },
    { label: "耗时", value: formatDuration(execution.execution_time_ms) },
  ];

  return (
    <div className="glass-panel flex flex-wrap items-center gap-6 px-5 py-3">
      {items.map((item) => (
        <div key={item.label} className="flex items-baseline gap-2">
          <span className="text-xs text-dash-mut">{item.label}</span>
          <span className="text-sm font-bold text-slate-800">{item.value}</span>
        </div>
      ))}
      {execution.status === "partial" && (
        <span className="rounded-full bg-amber-50 px-2.5 py-0.5 text-xs text-amber-700">
          部分维度不可用
        </span>
      )}
      {execution.status === "failed" && (
        <span className="rounded-full bg-red-50 px-2.5 py-0.5 text-xs text-red-700">
          处理失败
        </span>
      )}
    </div>
  );
}
