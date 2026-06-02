import ReactECharts from "echarts-for-react";
import { useChartTheme } from "../../context/ChartThemeContext";
import type { ChartConfig } from "../../types";
import { ChartContainer } from "./ChartContainer";
import {
  baseChartOption,
  getSeriesData,
  getXAxisData,
  parseSeries,
} from "./chartUtils";

interface LineChartProps {
  config: ChartConfig;
  withArea?: boolean;
  hideTitle?: boolean;
}

export default function LineChart({ config, withArea = true, hideTitle = false }: LineChartProps) {
  const { colors } = useChartTheme();
  const seriesMeta = parseSeries(config, colors);
  const xData = getXAxisData(config);

  const option = {
    ...baseChartOption,
    color: colors,
    xAxis: {
      type: "category" as const,
      data: xData,
      boundaryGap: false,
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
      type: "line" as const,
      smooth: true,
      symbol: "circle",
      symbolSize: 6,
      data: getSeriesData(config, item.key),
      lineStyle: { width: 2, color: item.color },
      itemStyle: { color: item.color },
      ...(withArea
        ? {
            areaStyle: {
              color: item.color,
              opacity: 0.12,
            },
          }
        : {}),
    })),
  };

  return (
    <ChartContainer title={config.title} hideTitle={hideTitle}>
      <ReactECharts
        option={option}
        notMerge
        style={{ height: 360, width: "100%" }}
      />
    </ChartContainer>
  );
}
