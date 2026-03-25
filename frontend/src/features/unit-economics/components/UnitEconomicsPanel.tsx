import { UnitEconomicsProducts, UnitEconomicsSummary } from "@/shared/api/types";
import { UnitEconomicsEditor } from "@/features/unit-economics/components/UnitEconomicsEditor";

type UnitEconomicsPanelProps = {
  summary: UnitEconomicsSummary;
  products: UnitEconomicsProducts;
};

export function UnitEconomicsPanel({ summary, products }: UnitEconomicsPanelProps) {
  const rows = summary.rows.slice(-5).reverse();
  const productRows = products.rows.slice(0, 4);

  return (
    <>
      <article className="panel-card panel-card-wide">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Unit Economics</p>
            <h3>Daily EBITDA and cost base</h3>
          </div>
          <span className="status-badge">{products.rows.length} SKUs</span>
        </div>
        <p className="muted-copy">
          Revenue total: {summary.totals.revenue ?? 0} / EBITDA total: {summary.totals.ebitda_total ?? 0}
        </p>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Day</th>
                <th>Revenue</th>
                <th>EBITDA</th>
                <th>Units</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={4} className="empty-cell">
                    No unit economics rows loaded yet.
                  </td>
                </tr>
              ) : (
                rows.map((row) => (
                  <tr key={row.day}>
                    <td>{row.day}</td>
                    <td>{row.revenue.toFixed(0)}</td>
                    <td>{row.ebitda_total.toFixed(0)}</td>
                    <td>{row.units_sold.toFixed(0)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {productRows.length > 0 ? (
          <div className="list-stack">
            {productRows.map((row) => (
              <div className="list-row" key={row.sku}>
                <div>
                  <strong>{row.name || row.sku}</strong>
                  <p>
                    Tea {row.tea_cost} / Package {row.package_cost} / Label {row.label_cost} / Packing {row.packing_cost}
                  </p>
                </div>
              </div>
            ))}
          </div>
        ) : null}
      </article>
      <UnitEconomicsEditor company={summary.company} rows={products.rows} />
    </>
  );
}
