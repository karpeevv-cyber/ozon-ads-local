import type { CSSProperties } from "react";
import { StocksWorkspace } from "@/shared/api/types";
import { StocksControls } from "@/features/stocks/components/StocksControls";

type StocksPanelProps = {
  workspace: StocksWorkspace;
  highlightMode: string;
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

export function StocksPanel({ workspace, highlightMode }: StocksPanelProps) {
  function quantifyByMode(cell: StocksWorkspace["rows"][number]["cells"][number]): number {
    if (highlightMode === "paid_now") {
      return cell.paid_storage_qty || 0;
    }
    if (highlightMode === "paid_30") {
      return cell.paid_storage_soon_30_qty || 0;
    }
    if (highlightMode === "paid_60") {
      return cell.paid_storage_soon_60_qty || 0;
    }
    return 0;
  }

  function gradientStyle(quantity: number): CSSProperties {
    if (quantity <= 0) {
      return {};
    }
    const step = Math.max(1, Math.ceil(quantity / 5));
    const alpha = Math.min(0.62, 0.16 + step * 0.06);
    return {
      backgroundImage: `linear-gradient(135deg, rgba(184, 92, 56, ${alpha}) 0%, rgba(184, 92, 56, ${Math.max(0.12, alpha - 0.08)}) 100%)`,
    };
  }

  function candidateStyle(isCandidate: boolean): CSSProperties {
    if (!isCandidate) {
      return {};
    }
    return {
      backgroundImage: "linear-gradient(135deg, rgba(53, 94, 59, 0.28) 0%, rgba(53, 94, 59, 0.18) 100%)",
      fontWeight: 700,
    };
  }

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
          highlightMode={highlightMode}
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
                      let style: CSSProperties = {};
                      if (highlightMode === "candidates") {
                        style = candidateStyle(cell.is_candidate);
                      } else if (highlightMode !== "none") {
                        style = gradientStyle(quantifyByMode(cell));
                      }
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
                          style={style}
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
