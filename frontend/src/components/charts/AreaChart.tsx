import LineChart from "./LineChart";
import type { ChartConfig } from "../../types";

interface AreaChartProps {
  config: ChartConfig;
  hideTitle?: boolean;
}

export default function AreaChart({ config, hideTitle = false }: AreaChartProps) {
  return <LineChart config={config} withArea hideTitle={hideTitle} />;
}
