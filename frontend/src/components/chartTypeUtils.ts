/** 解析面板实际渲染的图表类型（plan 与 chart_config 不一致时以 config 为准）。 */
export function resolvePanelChartType(input: {
  analysis_type?: string | null;
  plan_chart_type?: string | null;
  config_chart_type?: string | null;
}): string {
  const planned = input.plan_chart_type ?? "";
  const built = input.config_chart_type ?? "";
  if (input.analysis_type === "funnel") {
    if (planned === "table") {
      return built || "funnel_chart";
    }
    return planned || built || "funnel_chart";
  }
  return planned || built || "line";
}
