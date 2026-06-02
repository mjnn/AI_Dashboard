import { useChartTheme } from "../../context/ChartThemeContext";
import type { ChartConfig } from "../../types";
import { ChartContainer } from "./ChartContainer";
import { colorAt, parseSeries } from "./chartUtils";

interface DataTableProps {
  config: ChartConfig;
  hideTitle?: boolean;
}

export default function DataTable({ config, hideTitle = false }: DataTableProps) {
  const { colors } = useChartTheme();
  const seriesMeta = parseSeries(config, colors);
  const columns = [
    { key: config.x_axis_key, label: config.x_axis_key },
    ...seriesMeta.map((item) => ({ key: item.key, label: item.name })),
  ];

  return (
    <ChartContainer title={config.title} hideTitle={hideTitle}>
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs text-slate-500">
              {columns.map((col) => (
                <th key={col.key} className="px-3 py-2 font-medium">
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {config.data.map((row, rowIndex) => (
              <tr key={rowIndex} className="border-b border-slate-50">
                <td className="px-3 py-2 text-slate-700">{String(row[config.x_axis_key] ?? "")}</td>
                {seriesMeta.map((item, colIndex) => (
                  <td key={item.key} className="px-3 py-2 font-medium" style={{ color: colorAt(colors, colIndex) }}>
                    {String(row[item.key] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </ChartContainer>
  );
}
