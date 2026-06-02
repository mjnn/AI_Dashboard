import ReactECharts from "echarts-for-react";
import { useChartTheme } from "../../context/ChartThemeContext";
import type { ChartConfig } from "../../types";
import { ChartContainer } from "./ChartContainer";
import {
  baseChartOption,
  buildCategoricalBarData,
  getSeriesData,
  getXAxisData,
  isCategoricalChart,
  parseSeries,
} from "./chartUtils";

interface HorizontalBarChartProps {
  config: ChartConfig;
  hideTitle?: boolean;
}

export default function HorizontalBarChart({
  config,
  hideTitle = false,
}: HorizontalBarChartProps) {
  const { colors } = useChartTheme();
  const seriesMeta = parseSeries(config, colors);
  const yData = getXAxisData(config);
  const categorical = isCategoricalChart(config) && seriesMeta.length === 1;

  const option = {
    ...baseChartOption,
    color: colors,
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
      data: buildCategoricalBarData(
        getSeriesData(config, item.key),
        colors,
        categorical
      ),
      itemStyle: categorical
        ? { borderRadius: [0, 4, 4, 0] }
        : { color: item.color, borderRadius: [0, 4, 4, 0] },
    })),
  };

  return (
    <ChartContainer title={config.title} hideTitle={hideTitle}>
      <ReactECharts option={option} notMerge style={{ height: 360, width: "100%" }} />
    </ChartContainer>
  );
}
