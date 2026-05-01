import { FinanceSummary } from "@/shared/api/types";

type FinancePanelProps = {
  summary: FinanceSummary;
};

const columns: { key: keyof FinanceSummary["rows"][number]; label: string; isPercent?: boolean }[] = [
  { key: "day", label: "Day" },
  { key: "opening_balance", label: "Start" },
  { key: "closing_balance", label: "End" },
  { key: "change", label: "Delta" },
  { key: "sales", label: "Sales" },
  { key: "fee", label: "Fee" },
  { key: "acquiring", label: "Acq." },
  { key: "payments", label: "Pays" },
  { key: "logistics", label: "Log." },
  { key: "reverse_logistics", label: "Rev. log." },
  { key: "returns", label: "Ret." },
  { key: "cross_docking", label: "Cross" },
  { key: "acceptance", label: "Accept" },
  { key: "errors", label: "Errors" },
  { key: "storage", label: "Storage" },
  { key: "marketing", label: "Ads" },
  { key: "promotion_with_cpo", label: "CPO" },
  { key: "points_for_reviews", label: "Reviews" },
  { key: "seller_bonuses", label: "Bonuses" },
  { key: "check", label: "Check" },
  { key: "logistics_pct", label: "Log. %", isPercent: true },
];

const highlightedColumns = new Set(["opening_balance", "closing_balance", "change", "sales"]);

function formatValue(value: string | number, isPercent?: boolean) {
  if (typeof value === "string") {
    return value;
  }
  return isPercent ? `${value.toFixed(1)}%` : value;
}

export function FinancePanel({ summary }: FinancePanelProps) {
  const rows = summary.rows;

  return (
    <article className="panel-card panel-card-wide finance-panel-card">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Finance</p>
          <h3>Balance by day</h3>
        </div>
        <span className="status-badge">{rows.length} days</span>
      </div>
      <p className="muted-copy">
        Sales total: {summary.totals.sales ?? 0} / Logistics total: {summary.totals.logistics ?? 0}
      </p>
      <div className="table-wrap finance-table-wrap">
        <table className="data-table finance-table">
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column.key}>{column.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Object.keys(summary.totals).length > 0 ? (
              <tr>
                {columns.map((column) => (
                  <td
                    className={highlightedColumns.has(column.key) ? "finance-highlight-cell" : undefined}
                    key={column.key}
                  >
                    {column.key === "day"
                      ? "Total"
                      : formatValue(summary.totals[column.key] ?? 0, column.isPercent)}
                  </td>
                ))}
              </tr>
            ) : null}
            {rows.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="empty-cell">
                  No finance rows loaded yet.
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={row.day}>
                  {columns.map((column) => (
                    <td
                      className={highlightedColumns.has(column.key) ? "finance-highlight-cell" : undefined}
                      key={column.key}
                    >
                      {formatValue(row[column.key], column.isPercent)}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </article>
  );
}
