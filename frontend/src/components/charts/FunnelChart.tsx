import ReactECharts from "echarts-for-react";
import type { ChartConfig } from "../../types";
import { ChartContainer } from "./ChartContainer";
import { CHART_COLORS, formatAxisLabel, getXAxisData } from "./chartUtils";

interface FunnelChartProps {
  config: ChartConfig;
  hideTitle?: boolean;
}

export default function FunnelChart({ config, hideTitle = false }: FunnelChartProps) {
  const labels = getXAxisData(config);
  const valueKey =
    config.value_key ??
    config.y_axis_keys.find((key) => key !== "conversion_rate") ??
    config.y_axis_keys[0] ??
    "user_count";

  const data = config.data.map((row, index) => ({
    name: formatAxisLabel(row[config.x_axis_key]) || labels[index] || `Step ${index + 1}`,
    value: Number(row[valueKey] ?? 0),
  }));

  const option = {
    color: CHART_COLORS,
    tooltip: { trigger: "item" as const, formatter: "{b}: {c}" },
    series: [
      {
        type: "funnel" as const,
        left: "10%",
        top: 24,
        bottom: 24,
        width: "80%",
        min: 0,
        max: Math.max(...data.map((item) => item.value), 1),
        sort: "descending" as const,
        gap: 4,
        label: { show: true, position: "inside" as const, color: "#fff" },
        itemStyle: { borderColor: "#fff", borderWidth: 1 },
        data,
      },
    ],
  };

  return (
    <ChartContainer title={config.title} hideTitle={hideTitle}>
      <ReactECharts option={option} style={{ height: 360, width: "100%" }} />
    </ChartContainer>
  );
}
