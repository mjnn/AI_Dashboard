import type { ChartConfig, ChartType } from "../../types";
import AreaChart from "./AreaChart";
import BarChart from "./BarChart";
import DataTable from "./DataTable";
import DualAxisChart from "./DualAxisChart";
import FunnelChart from "./FunnelChart";
import GaugeChart from "./GaugeChart";
import HeatmapChart from "./HeatmapChart";
import HorizontalBarChart from "./HorizontalBarChart";
import LineChart from "./LineChart";
import PieChart from "./PieChart";
import StackedBarChart from "./StackedBarChart";

interface ChartRouterProps {
  config: ChartConfig;
  chartType: ChartType | string;
  compact?: boolean;
  hideTitle?: boolean;
}

export default function ChartRouter({
  config,
  chartType,
  compact = false,
  hideTitle = false,
}: ChartRouterProps) {
  if (config.data.length === 0) {
    return (
      <div
        className={`flex items-center justify-center rounded-lg bg-gray-50 ${
          compact ? "min-h-[200px]" : "min-h-[320px]"
        }`}
      >
        <p className="text-sm text-gray-400">暂无数据</p>
      </div>
    );
  }

  switch (chartType) {
    case "line":
    case "multi_line":
      return <LineChart config={config} withArea={false} hideTitle={hideTitle} />;
    case "area":
      return <AreaChart config={config} hideTitle={hideTitle} />;
    case "bar":
      return <BarChart config={config} hideTitle={hideTitle} />;
    case "horizontal_bar":
      return <HorizontalBarChart config={config} hideTitle={hideTitle} />;
    case "stacked_bar":
      return <StackedBarChart config={config} hideTitle={hideTitle} />;
    case "pie":
      return <PieChart config={config} hideTitle={hideTitle} />;
    case "dual_axis":
      return <DualAxisChart config={config} hideTitle={hideTitle} />;
    case "heatmap":
      return <HeatmapChart config={config} hideTitle={hideTitle} />;
    case "gauge":
      return <GaugeChart config={config} hideTitle={hideTitle} />;
    case "funnel_chart":
      return <FunnelChart config={config} hideTitle={hideTitle} />;
    case "table":
      return <DataTable config={config} hideTitle={hideTitle} />;
    default:
      return <LineChart config={config} withArea={false} hideTitle={hideTitle} />;
  }
}

// height prop unused in child components - they use fixed height internally
// compact mode could be enhanced later via ChartContainer
