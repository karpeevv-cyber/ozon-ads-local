import { FinanceSummary } from "@/shared/api/types";

type FinancePanelProps = {
  summary: FinanceSummary;
};

export function FinancePanel({ summary }: FinancePanelProps) {
  const rows = summary.rows.slice(0, 7);

  return (
    <article className="panel-card panel-card-wide">
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
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Day</th>
              <th>Opening</th>
              <th>Closing</th>
              <th>Sales</th>
              <th>Logistics %</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={5} className="empty-cell">
                  No finance rows loaded yet.
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={row.day}>
                  <td>{row.day}</td>
                  <td>{row.opening_balance}</td>
                  <td>{row.closing_balance}</td>
                  <td>{row.sales}</td>
                  <td>{row.logistics_pct}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </article>
  );
}
