import type { SqlResult } from "../../lib/types";

interface Props {
  data: SqlResult;
}

export function SqlTable({ data }: Props) {
  const { columns, rows } = data;
  const shown = rows.slice(0, 8);

  if (columns.length === 0) {
    return <p className="text-[12px] text-fg-dim">No results.</p>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-line-soft">
      <table className="w-full border-collapse font-mono text-[11px]">
        <thead>
          <tr className="bg-surface-2">
            {columns.map((col) => (
              <th
                key={col}
                className="border-b border-line-soft px-2.5 py-1.5 text-left font-medium uppercase tracking-wide text-fg-faint"
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {shown.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                className="px-2.5 py-3 text-center text-fg-faint"
              >
                No rows returned.
              </td>
            </tr>
          ) : (
            shown.map((row, i) => (
              <tr key={i} className="odd:bg-surface/40">
                {row.map((cell, j) => (
                  <td
                    key={j}
                    className="border-b border-line-soft px-2.5 py-1.5 tabular-nums text-fg-dim"
                  >
                    {cell === null ? "—" : String(cell)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
      {rows.length > shown.length && (
        <p className="px-2.5 py-1.5 font-mono text-[10.5px] text-fg-faint">
          +{rows.length - shown.length} more rows
        </p>
      )}
    </div>
  );
}
