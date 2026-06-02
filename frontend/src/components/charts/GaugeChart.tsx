import ReactECharts from "echarts-for-react";
import { useChartTheme } from "../../context/ChartThemeContext";
import type { ChartConfig } from "../../types";
import { ChartContainer } from "./ChartContainer";
import { getGaugeValue, parseSeries } from "./chartUtils";

interface GaugeChartProps {
  config: ChartConfig;
  hideTitle?: boolean;
}

export default function GaugeChart({ config, hideTitle = false }: GaugeChartProps) {
  const { colors } = useChartTheme();
  const seriesMeta = parseSeries(config, colors);
  const primary = seriesMeta[0]?.color ?? colors[0];

  const option = {
    series: [
      {
        type: "gauge" as const,
        min: 0,
        max: 100,
        progress: { show: true, width: 14 },
        axisLine: { lineStyle: { width: 14 } },
        axisTick: { show: false },
        splitLine: { length: 8, lineStyle: { width: 2, color: "#999" } },
        axisLabel: { distance: 20, color: "#6B7280", fontSize: 12 },
        anchor: { show: true, size: 16, itemStyle: { borderWidth: 4 } },
        detail: {
          valueAnimation: true,
          formatter: "{value}%",
          color: "#111827",
          fontSize: 24,
        },
        data: [{ value: getGaugeValue(config), name: config.title }],
        itemStyle: { color: primary },
      },
    ],
  };

  return (
    <ChartContainer title={config.title} hideTitle={hideTitle}>
      <ReactECharts option={option} notMerge style={{ height: 320, width: "100%" }} />
    </ChartContainer>
  );
}
