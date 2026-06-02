import type { AnalysisResponse, DashboardSection, PanelNarration } from "../types";

export function buildNarrationMap(
  presentation?: AnalysisResponse["presentation"]
): Map<string, PanelNarration> {
  const map = new Map<string, PanelNarration>();
  presentation?.panels.forEach((item) => map.set(item.panel_id, item));
  return map;
}

export function sectionGridClass(layout: DashboardSection["layout"]): string {
  switch (layout) {
    case "kpi_grid":
      return "grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4";
    case "wide_grid":
      return "grid grid-cols-1 gap-3 lg:grid-cols-2";
    case "compact_grid":
      return "grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3";
    case "single":
      return "grid grid-cols-1 gap-3";
    case "half_grid":
    default:
      return "grid grid-cols-1 gap-3 lg:grid-cols-2";
  }
}

export function fallbackSections(response: AnalysisResponse): DashboardSection[] {
  const panels = response.panels ?? [];
  const isPerEventPanel = (id: string) => id.startsWith("event-");
  const kpi = panels.filter((p) => p.layout === "kpi").map((p) => p.panel_id);
  const wide = panels.filter((p) => p.layout === "wide").map((p) => p.panel_id);
  const perEvent = panels
    .filter((p) => isPerEventPanel(p.panel_id))
    .map((p) => p.panel_id);
  const half = panels
    .filter(
      (p) =>
        (p.layout === "half" || p.layout === "compact") &&
        !isPerEventPanel(p.panel_id)
    )
    .map((p) => p.panel_id);

  const sections: DashboardSection[] = [];
  if (kpi.length) {
    sections.push({
      id: "overview",
      title: "一眼看清 / At a Glance",
      subtitle: "核心指标速览",
      panel_ids: kpi,
      layout: "kpi_grid",
    });
  }
  if (wide.length) {
    sections.push({
      id: "trends",
      title: "趋势脉搏 / Trend Pulse",
      subtitle: "时间轴上的变化与起伏",
      panel_ids: wide,
      layout: "wide_grid",
    });
  }
  if (perEvent.length) {
    sections.push({
      id: "per-event",
      title: "分事件趋势 / Per Event",
      subtitle: "范围内每个埋点单独的时间序列",
      panel_ids: perEvent,
      layout: "half_grid",
    });
  }
  if (half.length) {
    sections.push({
      id: "behavior",
      title: "用户行为 / User Behavior",
      subtitle: "频次、留存与分布",
      panel_ids: half,
      layout: "half_grid",
    });
  }
  if (!sections.length && panels.length) {
    sections.push({
      id: "main",
      title: "分析结果",
      subtitle: response.plan.matched_event,
      panel_ids: panels.map((p) => p.panel_id),
      layout: panels.length === 1 ? "single" : "half_grid",
    });
  }
  return sections;
}
