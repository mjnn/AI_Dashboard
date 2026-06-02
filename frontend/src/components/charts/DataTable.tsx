import type { ChartConfig } from "../../types";
import { ChartContainer } from "./ChartContainer";
import { formatAxisLabel, parseSeries } from "./chartUtils";

interface DataTableProps {
  config: ChartConfig;
  hideTitle?: boolean;
}

export default function DataTable({ config, hideTitle = false }: DataTableProps) {
  const seriesMeta = parseSeries(config);
  const columns = [
    { key: config.x_axis_key, label: config.x_axis_key },
    ...seriesMeta.map((item) => ({ key: item.key, label: item.name })),
  ];

  return (
    <ChartContainer title={config.title} hideTitle={hideTitle}>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left text-gray-500">
              {columns.map((column) => (
                <th key={column.key} className="px-4 py-3 font-medium">
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {config.data.length === 0 ? (
              <tr>
                <td
                  colSpan={columns.length}
                  className="px-4 py-8 text-center text-sm text-gray-400"
                >
                  暂无数据
                </td>
              </tr>
            ) : (
              config.data.map((row, rowIndex) => (
                <tr
                  key={`${rowIndex}-${String(row[config.x_axis_key])}`}
                  className={rowIndex % 2 === 0 ? "bg-white" : "bg-gray-50"}
                >
                  {columns.map((column) => (
                    <td key={column.key} className="px-4 py-3 text-gray-700">
                      {column.key === config.x_axis_key
                        ? formatAxisLabel(row[column.key])
                        : String(row[column.key] ?? "")}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </ChartContainer>
  );
}
