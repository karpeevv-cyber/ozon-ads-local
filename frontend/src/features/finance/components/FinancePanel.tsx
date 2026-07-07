import { FinanceSummary } from "@/shared/api/types";

type FinancePanelProps = {
  summary: FinanceSummary;
};

type FinanceRow = FinanceSummary["rows"][number];
type FinanceColumn = {
  key: keyof FinanceRow | string;
  keys: (keyof FinanceRow)[];
  label: string;
  title: string;
  isPercent?: boolean;
};

const column = (
  key: keyof FinanceRow,
  label: string,
  title: string,
  isPercent?: boolean,
): FinanceColumn => ({ key, keys: [key], label, title, isPercent });

const columns: FinanceColumn[] = [
  column("day", "day", "день"),
  column("opening_balance", "start", "на начало дня"),
  column("closing_balance", "end", "на конец дня"),
  column("change", "delta", "изменение"),
  column("sales", "sales", "продажи"),
  { key: "fee_acquiring", keys: ["fee", "acquiring"], label: "fee + acq.", title: "комиссия + эквайринг" },
  column("payments", "pays", "выплаты"),
  column("payment_commission", "pay comm.", "комиссия за выплату"),
  column("logistics", "log.", "логистика"),
  {
    key: "reverse_logistics_returns",
    keys: ["reverse_logistics", "returns"],
    label: "rev. log. + ret.",
    title: "обратная логистика + возвраты",
  },
  {
    key: "cross_docking_acceptance",
    keys: ["cross_docking", "acceptance"],
    label: "cross + accept",
    title: "кросс-докинг + приемка",
  },
  column("export", "export", "вывоз со склада"),
  column("pickup_point_storage", "pp storage", "хранение товаров в ПВЗ"),
  column("errors", "errors", "ошибки"),
  column("defects", "defects", "обработка брака"),
  column("mutual_offset", "offset", "взаимозачет"),
  column("decompensation", "decomp.", "декомпенсация"),
  column("disposal", "disposal", "утилизация"),
  column("storage", "storage", "Хранение"),
  column("marketing", "ads", "реклама"),
  column("promotion_with_cpo", "cpo", "реклама - за заказ"),
  column("points_for_reviews", "reviews", "баллы за отзывы"),
  column("seller_bonuses", "bonuses", "бонусы продавца"),
  column("check", "check", "проверка"),
  column("logistics_pct", "log. %", "% логистики", true),
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

function getFinanceValue(source: FinanceRow | FinanceSummary["totals"], column: FinanceColumn) {
  if (column.keys.length === 1) {
    return source[column.keys[0]] ?? 0;
  }
  return column.keys.reduce((sum, key) => sum + Number(source[key] ?? 0), 0);
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
                      : formatValue(getFinanceValue(summary.totals, column), column.isPercent)}
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
                        : formatValue(getFinanceValue(row, column), column.isPercent)}
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
