import type { AnalysisResponse } from "../types";
import AnalysisPanelCard from "./AnalysisPanelCard";
import CaliberCard from "./CaliberCard";
import SummaryBar from "./SummaryBar";
import {
  buildNarrationMap,
  fallbackSections,
  sectionGridClass,
} from "./dashboardUtils";

interface ExploratoryDashboardProps {
  response: AnalysisResponse;
}

export default function ExploratoryDashboard({ response }: ExploratoryDashboardProps) {
  const panels = response.panels ?? [];
  const panelMap = new Map(panels.map((p) => [p.panel_id, p]));
  const narrationMap = buildNarrationMap(response.presentation);
  const sections = response.presentation?.sections.length
    ? response.presentation.sections
    : fallbackSections(response);
  const unavailable = response.execution.unavailable_dimensions;
  const presentation = response.presentation;

  return (
    <div className="space-y-7">
      {presentation && (
        <div className="narrative-banner">
          <h2 className="text-lg font-bold text-slate-800">{presentation.headline}</h2>
          <p className="mt-2 text-sm leading-relaxed text-dash-mut">{presentation.summary}</p>
        </div>
      )}

      {!presentation && response.exploratory_reason && (
        <div className="narrative-banner border-cyan-200/60 bg-cyan-50/40">
          <p className="text-sm font-medium text-cyan-900">探索性分析</p>
          <p className="mt-1 text-sm text-cyan-800">{response.exploratory_reason}</p>
        </div>
      )}

      <CaliberCard plan={response.plan} />
      <SummaryBar execution={response.execution} />

      {sections.map((section, index) => {
        const sectionPanels = section.panel_ids
          .map((id) => panelMap.get(id))
          .filter((p): p is NonNullable<typeof p> => Boolean(p));

        if (!sectionPanels.length) {
          return null;
        }

        return (
          <section
            key={section.id}
            className="dash-section"
            style={{ animationDelay: `${index * 0.04}s` }}
          >
            <div className="sec-head">
              <h2>{section.title}</h2>
              <p>{section.subtitle}</p>
              {section.highlight && (
                <span className="sec-highlight">{section.highlight}</span>
              )}
            </div>

            <div className={sectionGridClass(section.layout)}>
              {sectionPanels.map((panel) => (
                <AnalysisPanelCard
                  key={panel.panel_id}
                  panel={panel}
                  narration={narrationMap.get(panel.panel_id)}
                />
              ))}
            </div>
          </section>
        );
      })}

      {unavailable.length > 0 && (
        <div className="glass-panel border-amber-200/80 bg-amber-50/50 px-4 py-3">
          <p className="text-sm font-medium text-amber-800">部分维度不可用</p>
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
