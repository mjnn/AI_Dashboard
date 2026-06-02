import type { AnalysisPanel, PanelNarration } from "../types";
import ChartRouter from "./charts/ChartRouter";
import { resolvePanelChartType } from "./chartTypeUtils";
import PanelCaliberBlock from "./PanelCaliberBlock";

interface AnalysisPanelCardProps {
  panel: AnalysisPanel;
  narration?: PanelNarration;
  embedded?: boolean;
}

function extractKpiValue(panel: AnalysisPanel): string | null {
  const row = panel.chart_config.data[0];
  if (!row) {
    return null;
  }
  const key =
    panel.chart_config.value_key ??
    panel.chart_config.y_axis_keys[0] ??
    panel.plan.metrics[0]?.id;
  if (!key || row[key] == null) {
    return null;
  }
  const raw = row[key];
  if (typeof raw === "number") {
    return raw.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return String(raw);
}

export default function AnalysisPanelCard({
  panel,
  narration,
  embedded = false,
}: AnalysisPanelCardProps) {
  const chartType = resolvePanelChartType({
    analysis_type: panel.analysis_type,
    plan_chart_type: panel.plan.visualization.chart_type,
    config_chart_type: panel.chart_config.chart_type,
  });
  const isKpi = panel.layout === "kpi";
  const kpiValue = isKpi ? extractKpiValue(panel) : null;
  const title = narration?.title ?? panel.name;
  const subtitle = narration?.subtitle;

  if (isKpi && kpiValue) {
    return (
      <article className="kpi-card flex flex-col">
        <p className="kpi-value">{kpiValue}</p>
        <p className="kpi-sub">{title}</p>
        {subtitle && <p className="mt-1 text-[11px] text-dash-mut">{subtitle}</p>}
        {narration?.tag && (
          <span className="kpi-tag kpi-tag-core">{narration.tag}</span>
        )}
        <div className="mt-auto">
          <PanelCaliberBlock plan={panel.plan} chartConfig={panel.chart_config} compact />
        </div>
      </article>
    );
  }

  return (
    <article className={`glass-panel flex flex-col overflow-hidden ${embedded ? "" : "h-full"}`}>
      <header className="border-b border-slate-200/60 px-4 py-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <h3 className="text-sm font-bold leading-snug text-slate-800">{title}</h3>
            {subtitle && (
              <p className="mt-1 text-xs leading-relaxed text-dash-mut">{subtitle}</p>
            )}
          </div>
          {narration?.tag && (
            <span className="shrink-0 rounded bg-cyan-50 px-2 py-0.5 text-[10px] font-semibold text-cyan-700">
              {narration.tag}
            </span>
          )}
        </div>
      </header>

      <div className={`chart-embed flex-1 ${isKpi ? "p-2" : "p-1"}`}>
        <ChartRouter
          config={panel.chart_config}
          chartType={chartType}
          compact={isKpi}
          hideTitle
        />
      </div>

      <PanelCaliberBlock plan={panel.plan} chartConfig={panel.chart_config} />
    </article>
  );
}
