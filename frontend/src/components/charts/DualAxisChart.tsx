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

interface DualAxisChartProps {
  config: ChartConfig;
  hideTitle?: boolean;
}

export default function DualAxisChart({ config, hideTitle = false }: DualAxisChartProps) {
  const { colors } = useChartTheme();
  const seriesMeta = parseSeries(config, colors);
  const xData = getXAxisData(config);

  const left = seriesMeta[0];
  const right = seriesMeta[1];

  const yAxis = [
    {
      type: "value" as const,
      name: left?.name,
      position: "left" as const,
      axisLine: { show: true, lineStyle: { color: left?.color ?? colors[0] } },
      axisLabel: { color: "#6B7280" },
      splitLine: { lineStyle: { color: "#F3F4F6" } },
    },
    ...(right
      ? [
          {
            type: "value" as const,
            name: right.name,
            position: "right" as const,
            axisLine: { show: true, lineStyle: { color: right.color } },
            axisLabel: { color: "#6B7280" },
            splitLine: { show: false },
          },
        ]
      : []),
  ];

  const series = [];
  if (left) {
    series.push({
      name: left.name,
      type: "line" as const,
      yAxisIndex: 0,
      smooth: false,
      data: getSeriesData(config, left.key),
      lineStyle: { width: 2, color: left.color },
      itemStyle: { color: left.color },
    });
  }
  if (right) {
    series.push({
      name: right.name,
      type: "line" as const,
      yAxisIndex: 1,
      smooth: false,
      data: getSeriesData(config, right.key),
      lineStyle: { width: 2, color: right.color },
      itemStyle: { color: right.color },
    });
  }

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
    yAxis,
    series,
  };

  return (
    <ChartContainer title={config.title} hideTitle={hideTitle}>
      <ReactECharts option={option} notMerge style={{ height: 360, width: "100%" }} />
    </ChartContainer>
  );
}
