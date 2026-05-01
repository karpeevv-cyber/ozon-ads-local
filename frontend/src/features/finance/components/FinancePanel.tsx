import { FinanceSummary } from "@/shared/api/types";

type FinancePanelProps = {
  summary: FinanceSummary;
};

const columns: { key: keyof FinanceSummary["rows"][number]; label: string; title: string; isPercent?: boolean }[] = [
  { key: "day", label: "day", title: "день" },
  { key: "opening_balance", label: "start", title: "на начало дня" },
  { key: "closing_balance", label: "end", title: "на конец дня" },
  { key: "change", label: "delta", title: "изменение" },
  { key: "sales", label: "sales", title: "продажи" },
  { key: "fee", label: "fee", title: "комиссия" },
  { key: "acquiring", label: "acq.", title: "эквайринг" },
  { key: "payments", label: "pays", title: "выплаты" },
  { key: "logistics", label: "log.", title: "логистика" },
  { key: "reverse_logistics", label: "rev. log.", title: "обратная логистика" },
  { key: "returns", label: "ret.", title: "возвраты" },
  { key: "cross_docking", label: "cross", title: "кросс-докинг" },
  { key: "export", label: "export", title: "вывоз со склада" },
  { key: "acceptance", label: "accept", title: "приемка" },
  { key: "errors", label: "errors", title: "ошибки" },
  { key: "storage", label: "storage", title: "Хранение" },
  { key: "marketing", label: "ads", title: "реклама" },
  { key: "promotion_with_cpo", label: "cpo", title: "реклама - за заказ" },
  { key: "points_for_reviews", label: "reviews", title: "баллы за отзывы" },
  { key: "seller_bonuses", label: "bonuses", title: "бонусы продавца" },
  { key: "check", label: "check", title: "проверка" },
  { key: "logistics_pct", label: "log. %", title: "% логистики", isPercent: true },
];

const highlightedColumns = new Set(["opening_balance", "closing_balance", "change", "sales"]);

function formatValue(value: string | number, isPercent?: boolean) {
  if (typeof value === "string") {
    return value;
  }
  return isPercent ? `${value.toFixed(1)}%` : value;
}

function formatDate(value: string) {
  const [year, month, day] = value.split("-");
  return year && month && day ? `${day}.${month}.${year}` : value;
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
      <div className="table-wrap finance-table-wrap">
        <table className="data-table finance-table">
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column.key} title={column.title}>{column.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Object.keys(summary.totals).length > 0 ? (
              <tr className="finance-total-row">
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
                      {column.key === "day"
                        ? formatDate(row.day)
                        : formatValue(row[column.key], column.isPercent)}
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
