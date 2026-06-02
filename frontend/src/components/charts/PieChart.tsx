import ReactECharts from "echarts-for-react";
import type { ChartConfig } from "../../types";
import { ChartContainer } from "./ChartContainer";
import { parseSeries } from "./chartUtils";

interface PieChartProps {
  config: ChartConfig;
  hideTitle?: boolean;
}

export default function PieChart({ config, hideTitle = false }: PieChartProps) {
  const seriesMeta = parseSeries(config);
  const metric = seriesMeta[0];
  const valueKey = metric?.key ?? config.y_axis_keys[0];

  const pieData = config.data.map((row) => ({
    name: String(row[config.x_axis_key] ?? ""),
    value: Number(row[valueKey] ?? 0),
  }));

  const option = {
    toolbox: { show: false },
    tooltip: {
      trigger: "item" as const,
      formatter: "{b}: {c} ({d}%)",
    },
    legend: {
      show: true,
      bottom: 0,
      type: "scroll" as const,
    },
    color: seriesMeta.map((item) => item.color),
    series: [
      {
        name: metric?.name ?? config.title,
        type: "pie" as const,
        radius: ["40%", "70%"],
        center: ["50%", "45%"],
        avoidLabelOverlap: true,
        itemStyle: {
          borderRadius: 6,
          borderColor: "#fff",
          borderWidth: 2,
        },
        label: {
          show: true,
          position: "outside" as const,
          color: "#374151",
          formatter: "{b}\n{d}%",
        },
        labelLine: {
          show: true,
          length: 12,
          length2: 8,
        },
        data: pieData,
      },
    ],
  };

  return (
    <ChartContainer title={config.title} hideTitle={hideTitle}>
      <ReactECharts option={option} style={{ height: 360, width: "100%" }} />
    </ChartContainer>
  );
}
