import { TrendsSnapshot } from "@/shared/api/types";

type TrendsPanelProps = {
  snapshot: TrendsSnapshot;
};

export function TrendsPanel({ snapshot }: TrendsPanelProps) {
  const niches = snapshot.niches.slice(0, 5);
  const products = snapshot.products.slice(0, 5);
  const cacheSource = String(snapshot.meta?.cache_source ?? "unknown");

  return (
    <article className="panel-card panel-card-wide">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Trends</p>
          <h3>Niche and product signals</h3>
        </div>
        <span className="status-badge">{cacheSource}</span>
      </div>
      {snapshot.errors.length > 0 ? (
        <p className="muted-copy">{snapshot.errors.join(" | ")}</p>
      ) : (
        <p className="muted-copy">
          Niches: {snapshot.niches.length} / Products: {snapshot.products.length}
        </p>
      )}
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Type</th>
              <th>Title</th>
              <th>Trend</th>
              <th>Confidence</th>
              <th>Risk</th>
            </tr>
          </thead>
          <tbody>
            {niches.length + products.length === 0 ? (
              <tr>
                <td colSpan={5} className="empty-cell">
                  No trend candidates loaded yet.
                </td>
              </tr>
            ) : (
              <>
                {niches.map((item) => (
                  <tr key={`niche:${item.id}`}>
                    <td>Niche</td>
                    <td>{item.title}</td>
                    <td>{item.trend_score}</td>
                    <td>{item.confidence_score}</td>
                    <td>{item.risk_score}</td>
                  </tr>
                ))}
                {products.map((item) => (
                  <tr key={`product:${item.id}`}>
                    <td>Product</td>
                    <td>{item.title}</td>
                    <td>{item.trend_score}</td>
                    <td>{item.confidence_score}</td>
                    <td>{item.risk_score}</td>
                  </tr>
                ))}
              </>
            )}
          </tbody>
        </table>
      </div>
    </article>
  );
}
