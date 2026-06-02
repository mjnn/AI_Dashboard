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

interface BarChartProps {
  config: ChartConfig;
  hideTitle?: boolean;
}

export default function BarChart({ config, hideTitle = false }: BarChartProps) {
  const { colors } = useChartTheme();
  const seriesMeta = parseSeries(config, colors);
  const xData = getXAxisData(config);
  const categorical = isCategoricalChart(config) && seriesMeta.length === 1;

  const option = {
    ...baseChartOption,
    color: colors,
    xAxis: {
      type: "category" as const,
      data: xData,
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
      barMaxWidth: 40,
      data: buildCategoricalBarData(
        getSeriesData(config, item.key),
        colors,
        categorical
      ),
      itemStyle: categorical
        ? { borderRadius: [4, 4, 0, 0] }
        : { color: item.color, borderRadius: [4, 4, 0, 0] },
    })),
  };

  return (
    <ChartContainer title={config.title} hideTitle={hideTitle}>
      <ReactECharts option={option} notMerge style={{ height: 360, width: "100%" }} />
    </ChartContainer>
  );
}
