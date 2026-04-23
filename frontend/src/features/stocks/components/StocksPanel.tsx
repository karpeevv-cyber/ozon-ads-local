import type { CSSProperties } from "react";
import { StocksWorkspace } from "@/shared/api/types";
import { StocksControls } from "@/features/stocks/components/StocksControls";

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
    const nowQty = cell.paid_storage_qty || 0;
    const in30Qty = cell.paid_storage_soon_30_qty || 0;
    const in60Qty = cell.paid_storage_soon_60_qty || 0;
    let bucket = 0;
    if (highlightLevels.length === 1) {
      const mode = highlightLevels[0];
      const qty = mode === "paid_now" ? nowQty : mode === "paid_30" ? in30Qty : in60Qty;
      bucket = qtyToBucket(qty);
    } else {
      const score = qtyToBucket(nowQty) * 3 + qtyToBucket(in30Qty) * 2 + qtyToBucket(in60Qty);
      if (score >= 15) bucket = 5;
      else if (score >= 10) bucket = 4;
      else if (score >= 6) bucket = 3;
      else if (score >= 3) bucket = 2;
      else if (score >= 1) bucket = 1;
      else bucket = 0;
    }
    const fill = bucketToFill(bucket);
    return {
      backgroundColor: fill,
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
                      const title = [
                        "Отгрузки",
                        `Платно сейчас: ${cell.paid_storage_qty} шт`,
                        `Платно в 30 дней: ${cell.paid_storage_soon_30_qty} шт`,
                        `Платно в 60 дней: ${cell.paid_storage_soon_60_qty} шт`,
                        shipmentTooltip,
                      ].join("\n");
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
