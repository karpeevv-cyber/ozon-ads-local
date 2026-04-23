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

function formatShipmentDate(value: string | null) {
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
  }).format(date);
}

export function StocksPanel({ workspace, reviewMode }: StocksPanelProps) {
  return (
    <section className="section-grid stocks-panel-section">
      <article className="panel-card section-card stocks-panel-card">
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

        <div className="stocks-kpi-row">
          <span className="stocks-kpi-chip">
            Articles <strong>{workspace.summary.article_count}</strong>
          </span>
          <span className="stocks-kpi-chip">
            Cities <strong>{workspace.summary.city_count}</strong>
          </span>
          <span className="stocks-kpi-chip">
            Candidates <strong>{workspace.summary.candidate_count}</strong>
          </span>
          <span className="stocks-kpi-chip">
            Approved <strong>{workspace.summary.approved_count}</strong>
          </span>
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
                    <th key={column} title={column}>
                      <span className="stocks-city-head">{column}</span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {workspace.rows.map((row) => (
                  <tr key={row.article}>
                    <td className="stocks-sticky-cell">
                      <strong>{row.article}</strong>
                    </td>
                    {row.cells.map((cell) => {
                      const backgroundColor = TURNOVER_GRADE_COLORS[cell.turnover_grade] || "transparent";
                      const className = reviewMode && cell.is_candidate ? "stocks-candidate-cell" : "";
                      const shipmentTooltip = cell.shipment_events.length
                        ? cell.shipment_events
                            .map((event) => {
                              if (event.paid_qty > 0) {
                                return `- ${formatShipmentDate(event.event_at)}: ${event.quantity} шт, из них ${event.paid_qty} хранятся платно`;
                              }
                              if (event.unsold_qty > 0) {
                                return `- ${formatShipmentDate(event.event_at)}: ${event.quantity} шт, из них ${event.unsold_qty} бесплатно до ${formatShipmentDate(event.free_storage_until)}`;
                              }
                              return `- ${formatShipmentDate(event.event_at)}: ${event.quantity} шт`;
                            })
                            .join("\n")
                        : "- нет отгрузок";
                      const title = ["Отгрузки", shipmentTooltip].join("\n");
                      return (
                        <td
                          key={`${row.article}:${cell.city}`}
                          className={className}
                          style={{ backgroundColor }}
                          title={title}
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
