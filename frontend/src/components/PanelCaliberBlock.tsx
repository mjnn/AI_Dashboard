import { useState } from "react";

import type { AnalysisPlan, ChartConfig, PanelCaliberDetail } from "../types";

interface PanelCaliberBlockProps {
  plan: AnalysisPlan;
  chartConfig: ChartConfig;
  compact?: boolean;
}

function fallbackDetail(plan: AnalysisPlan): PanelCaliberDetail {
  const formulas = plan.metrics.map((metric) => {
    if (metric.type === "formula" && metric.formula) {
      const parts = metric.formula_components?.join("、") ?? metric.formula;
      return `${metric.name}：由 ${parts} 组合计算得出`;
    }
    if (metric.type === "nunique") {
      const field = metric.field === "vin_code" ? "车辆 VIN" : metric.field ?? "车辆 VIN";
      return `${metric.name}：对 ${field} 去重计数，得到独立对象数量`;
    }
    if (metric.name.includes("触发") || metric.id === "pv") {
      return `${metric.name}：统计事件触发记录的总条数`;
    }
    return `${metric.name}：统计满足筛选条件的记录条数`;
  });
  const events = plan.comparison_events?.length
    ? plan.comparison_events
    : plan.csv_event_filter?.length
      ? plan.csv_event_filter
      : plan.matched_event
        ? [plan.matched_event]
        : [];

  return {
    description: plan.statistical_caliber.description,
    dedup_method: plan.statistical_caliber.dedup_method,
    time_granularity: plan.statistical_caliber.time_granularity,
    events,
    formulas,
  };
}

export default function PanelCaliberBlock({
  plan,
  chartConfig,
  compact = false,
}: PanelCaliberBlockProps) {
  const [expanded, setExpanded] = useState(false);
  const detail = chartConfig.caliber_detail ?? fallbackDetail(plan);
  const contentId = `panel-caliber-${plan.matched_event}-${plan.analysis_type ?? "chart"}`;

  return (
    <div
      className={`border-t border-slate-200/60 bg-slate-50/50 ${
        compact ? "px-3 py-2" : "px-4 py-3"
      }`}
    >
      <button
        type="button"
        className="flex w-full items-center justify-between gap-2 text-left"
        aria-expanded={expanded}
        aria-controls={contentId}
        onClick={() => setExpanded((open) => !open)}
      >
        <span className="text-[10px] font-semibold uppercase tracking-wide text-dash-mut">
          图表构成 / 统计口径 / 指标计算
        </span>
        <span className="shrink-0 text-[11px] font-medium text-slate-500">
          {expanded ? "收起" : "展开"}
        </span>
      </button>

      {expanded && (
        <div id={contentId} className="mt-2.5 space-y-2.5">
          {(detail.chart_layout?.length ?? 0) > 0 && (
            <section>
              <h4 className="text-[10px] font-semibold uppercase tracking-wide text-dash-mut">
                图表构成
              </h4>
              <ul className="mt-1 space-y-0.5">
                {detail.chart_layout!.map((line) => (
                  <li
                    key={line}
                    className="text-[11px] leading-relaxed text-slate-700"
                  >
                    {line}
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section>
            <h4 className="text-[10px] font-semibold uppercase tracking-wide text-dash-mut">
              统计口径
            </h4>
            <p className="mt-1 text-xs leading-relaxed text-slate-600">
              {detail.description}
            </p>
            <p className="mt-1 text-[11px] text-slate-500">
              去重：{detail.dedup_method} · 粒度：{detail.time_granularity}
            </p>
          </section>

          {(detail.grouping_rules?.length ?? 0) > 0 && (
            <section>
              <h4 className="text-[10px] font-semibold uppercase tracking-wide text-dash-mut">
                分组规则
              </h4>
              <ul className="mt-1 space-y-0.5">
                {detail.grouping_rules!.map((rule) => (
                  <li
                    key={rule}
                    className="text-[11px] leading-relaxed text-slate-600"
                  >
                    {rule}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {detail.events.length > 0 && (
            <section>
              <h4 className="text-[10px] font-semibold uppercase tracking-wide text-dash-mut">
                使用事件
              </h4>
              <ul className="mt-1 flex flex-wrap gap-1.5">
                {detail.events.map((event) => (
                  <li
                    key={event}
                    className="rounded-full bg-white px-2 py-0.5 text-[11px] text-slate-700 ring-1 ring-slate-200/80"
                  >
                    {event}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {detail.formulas.length > 0 && (
            <section>
              <h4 className="text-[10px] font-semibold uppercase tracking-wide text-dash-mut">
                指标计算
              </h4>
              <ul className="mt-1 space-y-0.5">
                {detail.formulas.map((formula) => (
                  <li
                    key={formula}
                    className="text-[11px] leading-relaxed text-slate-600"
                  >
                    {formula}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
