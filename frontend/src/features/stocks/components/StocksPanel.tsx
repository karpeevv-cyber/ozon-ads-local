import { StocksWorkspace } from "@/shared/api/types";
import { StocksControls } from "@/features/stocks/components/StocksControls";

type StocksPanelProps = {
  workspace: StocksWorkspace;
  reviewMode: boolean;
};

const TURNOVER_GRADE_COLORS: Record<string, string> = {
  DEFICIT: "#83ffb3",
  POPULAR: "#d5ffe5",
  ACTUAL: "#a2d8ff",
  SURPLUS: "#ffcaca",
  NO_SALES: "#ff7d7d",
};

function formatTimestamp(value: string | null) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function StocksPanel({ workspace, reviewMode }: StocksPanelProps) {
  return (
    <section className="dashboard-grid section-grid">
      <article className="panel-card panel-card-wide section-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Stocks</p>
            <h3>Inventory matrix by city</h3>
          </div>
          <span className="status-badge">{workspace.sku_count} sku</span>
        </div>

        <StocksControls
          regionalOrderMin={workspace.settings.regional_order_min}
          regionalOrderTarget={workspace.settings.regional_order_target}
          positionFilter={workspace.settings.position_filter}
          reviewMode={reviewMode}
        />

        <div className="summary-grid stocks-summary-grid">
          <div>
            <span>Articles</span>
            <strong>{workspace.summary.article_count}</strong>
          </div>
          <div>
            <span>Cities</span>
            <strong>{workspace.summary.city_count}</strong>
          </div>
          <div>
            <span>Candidates</span>
            <strong>{workspace.summary.candidate_count}</strong>
          </div>
          <div>
            <span>Approved</span>
            <strong>{workspace.summary.approved_count}</strong>
          </div>
        </div>

        <div className="stocks-meta">
          <span>Stocks cache: {formatTimestamp(workspace.stocks_updated_at)}</span>
          <span>Shipments cache: {formatTimestamp(workspace.shipments_updated_at)}</span>
        </div>

        <p className="muted-copy">
          Cell format: <strong>Stock / Need60 / InTransit</strong>
        </p>

        <div className="stocks-legend">
          <span><i style={{ backgroundColor: "#83ffb3" }} /> Deficit</span>
          <span><i style={{ backgroundColor: "#d5ffe5" }} /> Popular</span>
          <span><i style={{ backgroundColor: "#a2d8ff" }} /> Actual</span>
          <span><i style={{ backgroundColor: "#ffcaca" }} /> Surplus</span>
          <span><i style={{ backgroundColor: "#ff7d7d" }} /> No sales</span>
        </div>

        {workspace.rows.length === 0 || workspace.columns.length === 0 ? (
          <p className="muted-copy">No stocks data matched the current filters.</p>
        ) : (
          <div className="table-wrap stocks-matrix-wrap">
            <table className="data-table stocks-matrix-table">
              <thead>
                <tr>
                  <th>Article</th>
                  {workspace.columns.map((column) => (
                    <th key={column}>{column}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {workspace.rows.map((row) => (
                  <tr key={row.article}>
                    <td className="stocks-sticky-cell">
                      <strong>{row.article}</strong>
                      <p>{row.title || row.article}</p>
                    </td>
                    {row.cells.map((cell) => {
                      const backgroundColor = TURNOVER_GRADE_COLORS[cell.turnover_grade] || "transparent";
                      const className = reviewMode && cell.is_candidate ? "stocks-candidate-cell" : "";
                      return (
                        <td
                          key={`${row.article}:${cell.city}`}
                          className={className}
                          style={{ backgroundColor }}
                          title={`Stock ${cell.stock}, Need60 ${cell.need60}, InTransit ${cell.in_transit}`}
                        >
                          {cell.display_value}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </article>
    </section>
  );
}
