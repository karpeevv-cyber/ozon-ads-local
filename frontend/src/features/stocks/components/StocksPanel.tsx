import type { CSSProperties } from "react";
import { StocksWorkspace } from "@/shared/api/types";
import { StocksControls } from "@/features/stocks/components/StocksControls";
import { StocksRefreshButton } from "@/features/stocks/components/StocksRefreshButton";

type StocksPanelProps = {
  workspace: StocksWorkspace;
  highlightLevels: string[];
  reviewMode: boolean;
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
    timeZone: "Europe/Moscow",
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

function formatMs(value: number | undefined) {
  if (value === undefined || Number.isNaN(value)) {
    return "-";
  }
  if (value >= 1000) {
    return `${(value / 1000).toFixed(2)}s`;
  }
  return `${Math.round(value)}ms`;
}

export function StocksPanel({ workspace, highlightLevels, reviewMode }: StocksPanelProps) {
  function qtyToBucket(quantity: number): number {
    if (quantity <= 0) return 0;
    if (quantity <= 5) return 1;
    if (quantity <= 10) return 2;
    if (quantity <= 15) return 3;
    if (quantity <= 20) return 4;
    return 5;
  }

  function bucketToFill(bucket: number): string {
    if (bucket <= 0) return "transparent";
    if (bucket === 1) return "rgba(224, 224, 224, 0.45)";
    if (bucket === 2) return "rgba(173, 231, 180, 0.62)";
    if (bucket === 3) return "rgba(255, 237, 168, 0.66)";
    if (bucket === 4) return "rgba(255, 189, 189, 0.68)";
    return "rgba(241, 106, 106, 0.72)";
  }

  function storageHighlightStyle(cell: StocksWorkspace["rows"][number]["cells"][number]): CSSProperties {
    if (highlightLevels.length === 0) {
      return {};
    }
    const nowQty = Math.max(0, cell.paid_storage_qty || 0);
    const in30Qty = Math.max(0, cell.paid_storage_soon_30_qty || 0);
    // "60 days" is treated as the 31-60 day window to avoid double counting with 30-day level.
    const in60Qty = Math.max(0, (cell.paid_storage_soon_60_qty || 0) - in30Qty);
    let totalByActiveFilters = 0;
    if (highlightLevels.includes("paid_now")) {
      totalByActiveFilters += nowQty;
    }
    if (highlightLevels.includes("paid_30")) {
      totalByActiveFilters += in30Qty;
    }
    if (highlightLevels.includes("paid_60")) {
      totalByActiveFilters += in60Qty;
    }
    const bucket = qtyToBucket(totalByActiveFilters);
    const fill = bucketToFill(bucket);
    return {
      backgroundColor: fill,
    };
  }

  function rowTotals(row: StocksWorkspace["rows"][number]) {
    return row.cells.reduce(
      (acc, cell) => ({
        stock: acc.stock + (cell.stock || 0),
        need60: acc.need60 + (cell.need60 || 0),
        inTransit: acc.inTransit + (cell.in_transit || 0),
      }),
      { stock: 0, need60: 0, inTransit: 0 },
    );
  }

  return (
    <section className="section-grid stocks-panel-section">
      <article className="panel-card section-card stocks-panel-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Stocks</p>
            <h3>Inventory matrix by city</h3>
          </div>
          <div className="main-header-actions">
            <StocksRefreshButton />
          </div>
        </div>

        <StocksControls
          regionalOrderMin={workspace.settings.regional_order_min}
          regionalOrderTarget={workspace.settings.regional_order_target}
          positionFilter={workspace.settings.position_filter}
          highlightLevels={highlightLevels}
          reviewMode={reviewMode}
        />

        <div className="stocks-meta">
          <span>Stocks cache: {formatTimestamp(workspace.stocks_updated_at)}</span>
          <span>Shipments cache: {formatTimestamp(workspace.shipments_updated_at)}</span>
          <span title="Total backend build time for this Stocks workspace">
            Build: {formatMs(workspace.timings?.total_ms)}
          </span>
        </div>

        <div className="stocks-timing-strip">
          <span>stocks {formatMs(workspace.timings?.stocks_cache_ms)}</span>
          <span>shipments {formatMs(workspace.timings?.shipment_pairs_ms)}</span>
          <span>events {formatMs(workspace.timings?.shipment_events_ms)}</span>
          <span>matrix {formatMs(workspace.timings?.matrix_ms)}</span>
        </div>

        {workspace.rows.length === 0 || workspace.columns.length === 0 ? (
          <p className="muted-copy">No stocks data matched the current filters.</p>
        ) : (
          <div className="table-wrap stocks-matrix-wrap">
            <table className="data-table stocks-matrix-table">
              <thead>
                <tr>
                  <th>Article</th>
                  <th title="Total by all cities: stock | need 60 days | in transit">Total</th>
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
                    <td className="stocks-row-total-cell">
                      {(() => {
                        const total = rowTotals(row);
                        return `${total.stock} | ${total.need60} | ${total.inTransit}`;
                      })()}
                    </td>
                    {row.cells.map((cell) => {
                      const style: CSSProperties = {
                        ...storageHighlightStyle(cell),
                        ...(reviewMode && cell.is_candidate
                          ? {
                              boxShadow: "inset 0 0 0 2px rgba(184, 92, 56, 0.44)",
                              fontWeight: 700,
                            }
                          : {}),
                      };
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
                          <span>{cell.display_value}</span>
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
