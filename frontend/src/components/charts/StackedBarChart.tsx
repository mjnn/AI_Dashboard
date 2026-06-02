import ReactECharts from "echarts-for-react";
import { useChartTheme } from "../../context/ChartThemeContext";
import type { ChartConfig } from "../../types";
import { ChartContainer } from "./ChartContainer";
import {
  baseChartOption,
  buildPivotSeries,
  getSeriesData,
  getXAxisData,
  parseSeries,
} from "./chartUtils";

interface StackedBarChartProps {
  config: ChartConfig;
  hideTitle?: boolean;
}

export default function StackedBarChart({ config, hideTitle = false }: StackedBarChartProps) {
  const { colors } = useChartTheme();
  const seriesMeta = parseSeries(config, colors);
  const pivot = buildPivotSeries(config, colors);

  const option = pivot
    ? {
        ...baseChartOption,
        color: colors,
        xAxis: {
          type: "category" as const,
          data: pivot.xCategories,
          axisLine: { lineStyle: { color: "#E5E7EB" } },
          axisLabel: { color: "#6B7280" },
        },
        yAxis: {
          type: "value" as const,
          splitLine: { lineStyle: { color: "#F3F4F6" } },
          axisLabel: { color: "#6B7280" },
        },
        series: pivot.series.map((item) => ({
          name: item.name,
          type: "bar" as const,
          stack: "total",
          emphasis: { focus: "series" as const },
          data: item.data,
          itemStyle: { color: item.color, borderRadius: [2, 2, 0, 0] },
        })),
      }
    : {
        ...baseChartOption,
        color: colors,
        xAxis: {
          type: "category" as const,
          data: getXAxisData(config),
          axisLine: { lineStyle: { color: "#E5E7EB" } },
          axisLabel: { color: "#6B7280" },
        },
        yAxis: {
          type: "value" as const,
          splitLine: { lineStyle: { color: "#F3F4F6" } },
          axisLabel: { color: "#6B7280" },
        },
        series: seriesMeta.map((item) => ({
          name: item.name,
          type: "bar" as const,
          stack: "total",
          data: getSeriesData(config, item.key),
          itemStyle: { color: item.color, borderRadius: [2, 2, 0, 0] },
        })),
      };

  return (
    <ChartContainer title={config.title} hideTitle={hideTitle}>
      <ReactECharts option={option} notMerge style={{ height: 360, width: "100%" }} />
    </ChartContainer>
  );
}
