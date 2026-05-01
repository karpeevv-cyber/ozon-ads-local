import { FinanceSummary } from "@/shared/api/types";

type FinancePanelProps = {
  summary: FinanceSummary;
};

const columns: { key: keyof FinanceSummary["rows"][number]; label: string; isPercent?: boolean }[] = [
  { key: "day", label: "day" },
  { key: "opening_balance", label: "start" },
  { key: "closing_balance", label: "end" },
  { key: "change", label: "delta" },
  { key: "sales", label: "sales" },
  { key: "fee", label: "fee" },
  { key: "acquiring", label: "acq." },
  { key: "payments", label: "pays" },
  { key: "logistics", label: "log." },
  { key: "reverse_logistics", label: "rev. log." },
  { key: "returns", label: "ret." },
  { key: "cross_docking", label: "cross" },
  { key: "acceptance", label: "accept" },
  { key: "errors", label: "errors" },
  { key: "storage", label: "storage" },
  { key: "marketing", label: "ads" },
  { key: "promotion_with_cpo", label: "cpo" },
  { key: "points_for_reviews", label: "reviews" },
  { key: "seller_bonuses", label: "bonuses" },
  { key: "check", label: "check" },
  { key: "logistics_pct", label: "log. %", isPercent: true },
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
                      : column.key === "opening_balance" || column.key === "closing_balance"
                        ? ""
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
