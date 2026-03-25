import { StorageSnapshot } from "@/shared/api/types";

type StoragePanelProps = {
  snapshot: StorageSnapshot;
};

export function StoragePanel({ snapshot }: StoragePanelProps) {
  const rows = snapshot.risk_rows.slice(0, 10);

  return (
    <article className="panel-card panel-card-wide">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Storage</p>
          <h3>Fee risk forecast</h3>
        </div>
        <span className="status-badge">{rows.length} risk rows</span>
      </div>
      <p className="muted-copy">
        Orders: {snapshot.order_count} / Shipment lots: {snapshot.ship_lot_count} / Stock articles:{" "}
        {snapshot.stock_articles_count}
      </p>
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>City</th>
              <th>Article</th>
              <th>Fee from</th>
              <th>Qty at fee start</th>
              <th>Daily fee</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={5} className="empty-cell">
                  No storage risk rows loaded yet.
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={`${row.city}:${row.article}:${row.fee_from_date}`}>
                  <td>{row.city}</td>
                  <td>{row.article}</td>
                  <td>{row.fee_from_date}</td>
                  <td>{row.qty_expected_at_fee_start}</td>
                  <td>{row.estimated_daily_fee_rub}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </article>
  );
}
