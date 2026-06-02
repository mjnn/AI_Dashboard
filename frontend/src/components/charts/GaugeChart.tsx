import ReactECharts from "echarts-for-react";
import type { ChartConfig } from "../../types";
import { ChartContainer } from "./ChartContainer";
import { CHART_COLORS, getGaugeValue } from "./chartUtils";

interface GaugeChartProps {
  config: ChartConfig;
  hideTitle?: boolean;
}

export default function GaugeChart({ config, hideTitle = false }: GaugeChartProps) {
  const value = getGaugeValue(config);
  const max = value <= 100 ? 100 : Math.ceil(value * 1.2);

  const option = {
    series: [
      {
        type: "gauge" as const,
        startAngle: 200,
        endAngle: -20,
        min: 0,
        max,
        splitNumber: 5,
        itemStyle: { color: CHART_COLORS[0] },
        progress: { show: true, width: 16 },
        pointer: { show: false },
        axisLine: { lineStyle: { width: 16 } },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { show: false },
        detail: {
          valueAnimation: true,
          fontSize: 28,
          fontWeight: 600,
          color: "#111827",
          formatter: max === 100 ? "{value}%" : "{value}",
          offsetCenter: [0, "10%"],
        },
        data: [{ value: Math.round(value * 100) / 100 }],
      },
    ],
  };

  return (
    <ChartContainer title={config.title} hideTitle={hideTitle}>
      <ReactECharts option={option} style={{ height: 320, width: "100%" }} />
    </ChartContainer>
  );
}
