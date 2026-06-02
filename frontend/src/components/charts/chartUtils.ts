import type { ChartConfig } from "../../types";

export const CHART_COLORS = [
  "#007AFF",
  "#FF9500",
  "#34C759",
  "#FF3B30",
  "#5856D6",
  "#AF52DE",
  "#FF2D55",
  "#00C7BE",
];

export interface ParsedSeries {
  key: string;
  name: string;
  color: string;
  yAxisIndex: number;
}

export function parseSeries(config: ChartConfig): ParsedSeries[] {
  if (config.series.length > 0) {
    return config.series.map((item, index) => ({
      key: String(item.key ?? config.y_axis_keys[index] ?? ""),
      name: String(item.name ?? item.key ?? config.y_axis_keys[index] ?? ""),
      color: String(item.color ?? CHART_COLORS[index % CHART_COLORS.length]),
      yAxisIndex: Number(item.yAxisIndex ?? 0),
    }));
  }

  return config.y_axis_keys.map((key, index) => ({
    key,
    name: key,
    color: CHART_COLORS[index % CHART_COLORS.length],
    yAxisIndex: 0,
  }));
}

export function getXAxisData(config: ChartConfig): string[] {
  return config.data.map((row) => formatAxisLabel(row[config.x_axis_key]));
}

export function getSeriesData(config: ChartConfig, key: string): number[] {
  return config.data.map((row) => Number(row[key] ?? 0));
}

export function formatAxisLabel(value: unknown): string {
  if (value == null) {
    return "";
  }
  const text = String(value);
  if (text.includes("T00:00:00")) {
    return text.slice(0, 10);
  }
  return text;
}

export function buildHeatmapMatrix(config: ChartConfig) {
  const xKey = config.x_axis_key;
  const yKey = config.sub_axis_key ?? config.y_axis_keys[0];
  const valueKey = config.value_key ?? config.y_axis_keys[0] ?? "pv";

  const xLabels = Array.from(
    new Set(config.data.map((row) => formatAxisLabel(row[xKey])))
  );
  const yLabels = Array.from(
    new Set(config.data.map((row) => formatAxisLabel(row[yKey])))
  );

  const matrix = config.data.map((row) => {
    const xIndex = xLabels.indexOf(formatAxisLabel(row[xKey]));
    const yIndex = yLabels.indexOf(formatAxisLabel(row[yKey]));
    return [xIndex, yIndex, Number(row[valueKey] ?? 0)];
  });

  return { xLabels, yLabels, matrix, valueKey };
}

export function buildPivotSeries(config: ChartConfig) {
  const xKey = config.x_axis_key;
  const subKey = config.sub_axis_key;
  const valueKey = config.value_key ?? config.y_axis_keys[0] ?? "pv";

  if (!subKey) {
    return null;
  }

  const xCategories = Array.from(
    new Set(config.data.map((row) => formatAxisLabel(row[xKey])))
  );
  const subCategories = Array.from(
    new Set(config.data.map((row) => formatAxisLabel(row[subKey])))
  );

  const lookup = new Map<string, number>();
  for (const row of config.data) {
    const key = `${formatAxisLabel(row[xKey])}::${formatAxisLabel(row[subKey])}`;
    lookup.set(key, Number(row[valueKey] ?? 0));
  }

  const series = subCategories.map((name, index) => ({
    name,
    key: name,
    color: CHART_COLORS[index % CHART_COLORS.length],
    data: xCategories.map(
      (x) => lookup.get(`${x}::${name}`) ?? 0
    ),
  }));

  return { xCategories, series };
}

export function getGaugeValue(config: ChartConfig): number {
  if (config.data.length === 0) {
    return 0;
  }
  const row = config.data[0];
  const key =
    config.value_key ??
    config.y_axis_keys[0] ??
    Object.keys(row).find((k) => typeof row[k] === "number") ??
    "";
  return Number(row[key] ?? 0);
}

export const baseChartOption = {
  toolbox: { show: false },
  tooltip: { trigger: "axis" as const },
  legend: { show: true, bottom: 0 },
  grid: { left: 48, right: 24, top: 24, bottom: 48, containLabel: true },
};
