import ReactECharts from "echarts-for-react";
import type { ChartConfig } from "../../types";
import { ChartContainer } from "./ChartContainer";
import {
  getSeriesData,
  getXAxisData,
  parseSeries,
} from "./chartUtils";

interface DualAxisChartProps {
  config: ChartConfig;
  hideTitle?: boolean;
}

export default function DualAxisChart({ config, hideTitle = false }: DualAxisChartProps) {
  const seriesMeta = parseSeries(config);
  const xData = getXAxisData(config);
  const left = seriesMeta[0];
  const right = seriesMeta[1];
  const hasDual = Boolean(left && right && right.key !== left.key);

  const yAxis = [
    {
      type: "value" as const,
      name: left?.name,
      position: "left" as const,
      axisLine: { show: true, lineStyle: { color: left?.color ?? "#007AFF" } },
      axisLabel: { color: "#6B7280" },
      splitLine: { lineStyle: { color: "#F3F4F6" } },
    },
    ...(hasDual
      ? [
          {
            type: "value" as const,
            name: right?.name,
            position: "right" as const,
            axisLine: {
              show: true,
              lineStyle: { color: right?.color ?? "#FF9500" },
            },
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
      smooth: true,
      data: getSeriesData(config, left.key),
      lineStyle: { width: 2, color: left.color },
      itemStyle: { color: left.color },
    });
  }
  if (hasDual && right) {
    series.push({
      name: right.name,
      type: "line" as const,
      yAxisIndex: 1,
      smooth: true,
      data: getSeriesData(config, right.key),
      lineStyle: { width: 2, color: right.color },
      itemStyle: { color: right.color },
    });
  }

  const option = {
    toolbox: { show: false },
    tooltip: { trigger: "axis" as const },
    legend: { show: true, bottom: 0 },
    grid: { left: 56, right: hasDual ? 56 : 24, top: 24, bottom: 48, containLabel: true },
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
      <ReactECharts option={option} style={{ height: 360, width: "100%" }} />
    </ChartContainer>
  );
}
