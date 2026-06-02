import ReactECharts from "echarts-for-react";
import type { ChartConfig } from "../../types";
import { ChartContainer } from "./ChartContainer";
import {
  baseChartOption,
  getSeriesData,
  getXAxisData,
  parseSeries,
} from "./chartUtils";

interface HorizontalBarChartProps {
  config: ChartConfig;
  hideTitle?: boolean;
}

export default function HorizontalBarChart({ config, hideTitle = false }: HorizontalBarChartProps) {
  const seriesMeta = parseSeries(config);
  const yData = getXAxisData(config);

  const option = {
    ...baseChartOption,
    color: seriesMeta.map((item) => item.color),
    xAxis: {
      type: "value" as const,
      splitLine: { lineStyle: { color: "#F3F4F6" } },
      axisLabel: { color: "#6B7280" },
    },
    yAxis: {
      type: "category" as const,
      data: yData,
      axisLine: { lineStyle: { color: "#E5E7EB" } },
      axisLabel: { color: "#6B7280" },
    },
    series: seriesMeta.map((item) => ({
      name: item.name,
      type: "bar" as const,
      barMaxWidth: 28,
      data: getSeriesData(config, item.key),
      itemStyle: {
        color: item.color,
        borderRadius: [0, 4, 4, 0],
      },
    })),
  };

  return (
    <ChartContainer title={config.title} hideTitle={hideTitle}>
      <ReactECharts option={option} style={{ height: 360, width: "100%" }} />
    </ChartContainer>
  );
}
