import ReactECharts from "echarts-for-react";
import { useChartTheme } from "../../context/ChartThemeContext";
import { heatmapGradient } from "../../theme/chartPalettes";
import type { ChartConfig } from "../../types";
import { ChartContainer } from "./ChartContainer";
import { buildHeatmapMatrix } from "./chartUtils";

interface HeatmapChartProps {
  config: ChartConfig;
  hideTitle?: boolean;
}

export default function HeatmapChart({ config, hideTitle = false }: HeatmapChartProps) {
  const { colors } = useChartTheme();
  const { xLabels, yLabels, matrix } = buildHeatmapMatrix(config);
  const gradient = heatmapGradient(colors[0] ?? "#6366F1");

  const option = {
    tooltip: { position: "top" as const },
    grid: { left: 64, right: 24, top: 24, bottom: 64, containLabel: true },
    xAxis: {
      type: "category" as const,
      data: xLabels,
      splitArea: { show: true },
      axisLabel: { color: "#6B7280", rotate: xLabels.length > 12 ? 45 : 0 },
    },
    yAxis: {
      type: "category" as const,
      data: yLabels,
      splitArea: { show: true },
      axisLabel: { color: "#6B7280" },
    },
    visualMap: {
      min: 0,
      max: Math.max(...matrix.map((item) => Number(item[2])), 1),
      calculable: true,
      orient: "horizontal" as const,
      left: "center",
      bottom: 0,
      inRange: { color: gradient },
    },
    series: [
      {
        name: config.title,
        type: "heatmap" as const,
        data: matrix,
        label: { show: false },
        emphasis: {
          itemStyle: { shadowBlur: 8, shadowColor: "rgba(0,0,0,0.2)" },
        },
      },
    ],
  };

  return (
    <ChartContainer title={config.title} hideTitle={hideTitle}>
      <ReactECharts option={option} notMerge style={{ height: 400, width: "100%" }} />
    </ChartContainer>
  );
}
