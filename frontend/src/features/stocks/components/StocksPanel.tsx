import { StocksSnapshot } from "@/shared/api/types";

type StocksPanelProps = {
  snapshot: StocksSnapshot;
};

export function StocksPanel({ snapshot }: StocksPanelProps) {
  const rows = snapshot.rows.slice(0, 12);

  return (
    <article className="panel-card panel-card-wide">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Stocks</p>
          <h3>Inventory snapshot</h3>
        </div>
        <span className="status-badge">{snapshot.sku_count} sku</span>
      </div>
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Article</th>
              <th>Cluster</th>
              <th>Available</th>
              <th>Transit</th>
              <th>Ads</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={5} className="empty-cell">
                  No stocks snapshot loaded yet.
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={`${row.article}:${row.cluster}`}>
                  <td>{row.article}</td>
                  <td>{row.cluster}</td>
                  <td>{row.available_stock_count}</td>
                  <td>{row.transit_stock_count}</td>
                  <td>{row.ads_cluster}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </article>
  );
}
