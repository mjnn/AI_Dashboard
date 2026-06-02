import type { AnalysisResponse } from "../types";
import ExploratoryDashboard from "./ExploratoryDashboard";
import SummaryBar from "./SummaryBar";
import ChartRouter from "./charts/ChartRouter";
import { resolvePanelChartType } from "./chartTypeUtils";
import PanelCaliberBlock from "./PanelCaliberBlock";

interface DashboardProps {
  response: AnalysisResponse;
}

function SingleDashboard({ response }: DashboardProps) {
  const { plan, execution, chart_config: config, presentation } = response;
  const unavailable = execution.unavailable_dimensions;
  const narration = presentation?.panels[0];
  const section = presentation?.sections[0];

  return (
    <div className="space-y-6">
      {presentation && (
        <div className="narrative-banner">
          <h2 className="text-lg font-bold text-slate-800">{presentation.headline}</h2>
          <p className="mt-2 text-sm leading-relaxed text-dash-mut">{presentation.summary}</p>
        </div>
      )}

      {execution.status === "failed" && (
        <div className="glass-panel border-red-200/80 bg-red-50/60 px-4 py-3 text-sm text-red-700">
          数据处理失败：CSV 中缺少必要的事件列，无法完成分析。
        </div>
      )}

      <SummaryBar execution={execution} />

      <section className="dash-section">
        {(section || narration) && (
          <div className="sec-head">
            {section && <h2>{section.title}</h2>}
            {(section?.subtitle || narration?.subtitle) && (
              <p>{section?.subtitle ?? narration?.subtitle}</p>
            )}
            {section?.highlight && (
              <span className="sec-highlight">{section.highlight}</span>
            )}
          </div>
        )}

        <div className="glass-panel overflow-hidden p-1">
          {narration && (
            <header className="border-b border-slate-200/60 px-4 py-3">
              <h3 className="text-sm font-bold text-slate-800">{narration.title}</h3>
              {narration.subtitle && (
                <p className="mt-1 text-xs text-dash-mut">{narration.subtitle}</p>
              )}
            </header>
          )}
          <div className="chart-embed">
            <ChartRouter
              config={config}
              chartType={resolvePanelChartType({
                analysis_type: plan.analysis_type,
                plan_chart_type: plan.visualization.chart_type,
                config_chart_type: config.chart_type,
              })}
              hideTitle
            />
          </div>
          <PanelCaliberBlock plan={plan} chartConfig={config} />
        </div>
      </section>

      {unavailable.length > 0 && (
        <div className="glass-panel border-amber-200/80 bg-amber-50/50 px-4 py-3">
          <p className="text-sm font-medium text-amber-800">不可用维度</p>
          <ul className="mt-2 flex flex-wrap gap-2">
            {unavailable.map((dimension) => (
              <li
                key={dimension}
                className="rounded-full bg-amber-100 px-3 py-1 text-xs text-amber-700"
              >
                {dimension}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default function Dashboard({ response }: DashboardProps) {
  const usePanelGrid =
    (response.mode === "exploratory" || response.mode === "comprehensive") &&
    Boolean(response.panels?.length);
  if (usePanelGrid) {
    return <ExploratoryDashboard response={response} />;
  }
  return <SingleDashboard response={response} />;
}
