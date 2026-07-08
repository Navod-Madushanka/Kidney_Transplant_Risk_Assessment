// src/components/ui/Table.jsx

/**
 * Usage:
 *   <Table
 *     columns={[
 *       { key: "antigen", label: "Antigen" },
 *       { key: "mfi_value", label: "MFI value", align: "right" },
 *       { key: "confidence", label: "Confidence", align: "right" },
 *     ]}
 *     rows={extractedRows}
 *     getRowId={(row) => row.id}
 *     isRowFlagged={(row) => row.confidence < 0.8}
 *     renderCell={(row, col) =>
 *       col.key === "confidence" ? `${Math.round(row.confidence * 100)}%` : row[col.key]
 *     }
 *   />
 *
 * Flagged rows (e.g. low-confidence OCR extractions) get a subtle amber left
 * border and background tint — visible at a glance without a full row of
 * warning color, so a reviewer can scan for the ones that need a second look.
 */
export default function Table({
  columns,
  rows,
  getRowId,
  renderCell,
  isRowFlagged,
  emptyMessage = "No data to display.",
  className = "",
}) {
  if (!rows || rows.length === 0) {
    return (
      <div className="border border-border rounded-lg p-8 text-center text-[15px] text-text-muted bg-surface">
        {emptyMessage}
      </div>
    )
  }

  return (
    <div className={["overflow-x-auto border border-border rounded-lg bg-surface", className].join(" ")}>
      <table className="w-full border-collapse text-[14px]">
        <thead>
          <tr className="border-b border-border">
            {columns.map((col) => (
              <th
                key={col.key}
                className={[
                  "px-4 py-3 font-semibold text-text-muted text-[13px] whitespace-nowrap",
                  col.align === "right" ? "text-right" : "text-left",
                ].join(" ")}
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const flagged = isRowFlagged?.(row)
            return (
              <tr
                key={getRowId(row)}
                className={[
                  "border-b border-border last:border-b-0",
                  flagged ? "bg-moderate-subtle border-l-4 border-l-moderate" : "",
                ].join(" ")}
              >
                {columns.map((col) => (
                  <td
                    key={col.key}
                    className={[
                      "px-4 py-3 text-text tabular-nums",
                      col.align === "right" ? "text-right" : "text-left",
                    ].join(" ")}
                  >
                    {renderCell ? renderCell(row, col) : row[col.key]}
                  </td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}