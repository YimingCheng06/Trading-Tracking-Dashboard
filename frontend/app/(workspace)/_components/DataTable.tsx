import type { ReactNode } from "react";

export type Column = {
  key: string;
  label: string;
  /** 右对齐(用于数字列) */
  numeric?: boolean;
};

/**
 * 轻量表格。rows 是已渲染好的单元格内容数组,顺序与 columns 对齐。
 * 表体可滚动 —— 适合成交流水这类长列表。
 */
export function DataTable({
  columns,
  rows,
}: {
  columns: Column[];
  rows: { id: string; cells: ReactNode[] }[];
}) {
  return (
    <div className="overflow-hidden rounded-2xl border border-border bg-surface/60">
      <div className="max-h-[68vh] overflow-y-auto">
        <table className="w-full border-collapse text-sm">
          <thead className="sticky top-0 z-10 bg-rail/95 backdrop-blur">
            <tr>
              {columns.map((c) => (
                <th
                  key={c.key}
                  className={`border-b border-border px-4 py-3 text-xs font-medium uppercase tracking-[0.14em] text-muted ${
                    c.numeric ? "text-right" : "text-left"
                  }`}
                >
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.id}
                className="border-b border-border/40 transition-colors last:border-0 hover:bg-surface-elevated/60"
              >
                {row.cells.map((cell, i) => (
                  <td
                    key={columns[i].key}
                    className={`tabular px-4 py-3 ${
                      columns[i].numeric ? "text-right" : "text-left"
                    }`}
                  >
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
