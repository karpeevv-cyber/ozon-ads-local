import {
  BidChangeRecord,
  CampaignCommentRecord,
  CampaignReport,
  CompanyConfig,
  FinanceSummary,
  RunningCampaign,
  StocksSnapshot,
  StorageSnapshot,
  TrendsSnapshot,
  UnitEconomicsSummary,
} from "@/shared/api/types";

type MainDashboardProps = {
  companies: CompanyConfig[];
  selectedCompany: string;
  campaigns: RunningCampaign[];
  report: CampaignReport;
  financeSummary: FinanceSummary;
  unitEconomicsSummary: UnitEconomicsSummary;
  stocksSnapshot: StocksSnapshot;
  storageSnapshot: StorageSnapshot;
  trendsSnapshot: TrendsSnapshot;
  recentBidChanges: BidChangeRecord[];
  campaignComments: CampaignCommentRecord[];
};

function formatNumber(value: unknown) {
  const numeric = Number(value ?? 0);
  if (!Number.isFinite(numeric)) {
    return "0";
  }
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(numeric);
}

function maskValue(value: string) {
  if (!value) {
    return "not set";
  }
  if (value.length <= 6) {
    return "configured";
  }
  return `${value.slice(0, 3)}...${value.slice(-3)}`;
}

export function MainDashboard({
  companies,
  selectedCompany,
  campaigns,
  report,
  financeSummary,
  unitEconomicsSummary,
  stocksSnapshot,
  storageSnapshot,
  trendsSnapshot,
  recentBidChanges,
  campaignComments,
}: MainDashboardProps) {
  const configuredCompanies = companies.filter(
    (company) =>
      company.perf_client_id ||
      company.perf_client_secret ||
      company.seller_client_id ||
      company.seller_api_key,
  );
  const grandTotal = report.rows.find((row) => row.campaign_id === "GRAND_TOTAL");
  const topCampaigns = report.rows
    .filter((row) => row.campaign_id !== "GRAND_TOTAL")
    .slice()
    .sort((left, right) => Number(right.total_revenue || 0) - Number(left.total_revenue || 0))
    .slice(0, 5);
  const financeRows = financeSummary.rows.slice(-5).reverse();
  const econRows = unitEconomicsSummary.rows.slice(-5).reverse();
  const riskRows = storageSnapshot.risk_rows.slice(0, 5);
  const stockRows = stocksSnapshot.rows.slice(0, 5);
  const nicheRows = trendsSnapshot.niches.slice(0, 3);
  const productRows = trendsSnapshot.products.slice(0, 3);
  const activityRows = [
    ...recentBidChanges.slice(0, 3).map((change) => ({
      key: `bid:${change.ts_iso}:${change.campaign_id}:${change.sku}`,
      title: `Bid ${change.reason}`,
      copy: `Campaign ${change.campaign_id} / SKU ${change.sku}`,
      meta: change.date || change.ts_iso,
    })),
    ...campaignComments.slice(0, 3).map((comment) => ({
      key: `comment:${comment.ts}:${comment.campaign_id}`,
      title: `Comment for ${comment.campaign_id}`,
      copy: comment.comment,
      meta: comment.day || comment.ts,
    })),
  ].slice(0, 6);

  return (
    <section className="dashboard-grid section-grid">
      <article className="hero-card">
        <div className="hero-copy">
          <p className="eyebrow">Main</p>
          <h2>{selectedCompany} control summary</h2>
          <p>
            One screen for the period snapshot: revenue, spend, EBITDA direction, active campaigns,
            storage risk and trend signals.
          </p>
        </div>
        <div className="hero-metrics">
          <div>
            <span className="metric-label">Revenue</span>
            <strong>{formatNumber(grandTotal?.total_revenue)}</strong>
            <small>{report.date_from} to {report.date_to}</small>
          </div>
          <div>
            <span className="metric-label">Spend / DRR</span>
            <strong>{formatNumber(grandTotal?.money_spent)}</strong>
            <small>{formatNumber(grandTotal?.total_drr_pct)}% DRR</small>
          </div>
          <div>
            <span className="metric-label">EBITDA total</span>
            <strong>{formatNumber(unitEconomicsSummary.totals.ebitda_total)}</strong>
            <small>{formatNumber(unitEconomicsSummary.totals.revenue)} revenue base</small>
          </div>
        </div>
      </article>

      <article className="panel-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Runtime</p>
            <h3>Workspace snapshot</h3>
          </div>
        </div>
        <div className="summary-grid">
          <div>
            <span>Configured companies</span>
            <strong>{configuredCompanies.length}</strong>
          </div>
          <div>
            <span>Running campaigns</span>
            <strong>{campaigns.length}</strong>
          </div>
          <div>
            <span>Stocks SKU</span>
            <strong>{stocksSnapshot.sku_count}</strong>
          </div>
          <div>
            <span>Storage risks</span>
            <strong>{storageSnapshot.risk_rows.length}</strong>
          </div>
        </div>
      </article>

      <article className="panel-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Credentials</p>
            <h3>Connected organizations</h3>
          </div>
        </div>
        <div className="list-stack">
          {companies.map((company) => (
            <div className="list-row" key={company.name}>
              <div>
                <strong>{company.name}</strong>
                <p>
                  Perf {maskValue(company.perf_client_id)} / Seller {maskValue(company.seller_client_id)}
                </p>
              </div>
              <span className="status-badge">
                {company.perf_client_id && company.seller_client_id ? "ready" : "incomplete"}
              </span>
            </div>
          ))}
        </div>
      </article>

      <article className="panel-card panel-card-wide">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Campaigns</p>
            <h3>Top revenue campaigns</h3>
          </div>
          <span className="status-badge">{topCampaigns.length} rows</span>
        </div>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Campaign</th>
                <th>Revenue</th>
                <th>Spend</th>
                <th>DRR %</th>
                <th>Clicks</th>
              </tr>
            </thead>
            <tbody>
              {topCampaigns.length === 0 ? (
                <tr>
                  <td colSpan={5} className="empty-cell">
                    No campaign rows loaded yet.
                  </td>
                </tr>
              ) : (
                topCampaigns.map((row, index) => (
                  <tr key={`${row.campaign_id}:${row.sku || "all"}:${index}`}>
                    <td>{row.title || row.campaign_id}</td>
                    <td>{formatNumber(row.total_revenue)}</td>
                    <td>{formatNumber(row.money_spent)}</td>
                    <td>{formatNumber(row.total_drr_pct)}</td>
                    <td>{formatNumber(row.clicks)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </article>

      <article className="panel-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Finance</p>
            <h3>Recent balance days</h3>
          </div>
        </div>
        <div className="list-stack">
          {financeRows.length === 0 ? (
            <p className="muted-copy">No finance data loaded yet.</p>
          ) : (
            financeRows.map((row) => (
              <div className="list-row" key={row.day}>
                <div>
                  <strong>{row.day}</strong>
                  <p>Sales {formatNumber(row.sales)} / Closing {formatNumber(row.closing_balance)}</p>
                </div>
                <span className="status-badge">{formatNumber(row.logistics_pct)}% logistics</span>
              </div>
            ))
          )}
        </div>
      </article>

      <article className="panel-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Unit economics</p>
            <h3>Recent EBITDA days</h3>
          </div>
        </div>
        <div className="list-stack">
          {econRows.length === 0 ? (
            <p className="muted-copy">No unit economics data loaded yet.</p>
          ) : (
            econRows.map((row) => (
              <div className="list-row" key={row.day}>
                <div>
                  <strong>{row.day}</strong>
                  <p>Revenue {formatNumber(row.revenue)} / EBITDA {formatNumber(row.ebitda_total)}</p>
                </div>
                <span className="status-badge">{formatNumber(row.units_sold)} units</span>
              </div>
            ))
          )}
        </div>
      </article>

      <article className="panel-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Stocks</p>
            <h3>Inventory pulse</h3>
          </div>
        </div>
        <div className="list-stack">
          {stockRows.length === 0 ? (
            <p className="muted-copy">No stocks snapshot loaded yet.</p>
          ) : (
            stockRows.map((row) => (
              <div className="list-row" key={`${row.article}:${row.cluster}`}>
                <div>
                  <strong>{row.article}</strong>
                  <p>{row.cluster} / transit {row.transit_stock_count}</p>
                </div>
                <span className="status-badge">{row.available_stock_count} available</span>
              </div>
            ))
          )}
        </div>
      </article>

      <article className="panel-card panel-card-wide">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Storage</p>
            <h3>Nearest fee risks</h3>
          </div>
          <span className="status-badge">{storageSnapshot.risk_rows.length} risk rows</span>
        </div>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Article</th>
                <th>City</th>
                <th>Fee from</th>
                <th>Qty at fee start</th>
                <th>Daily fee</th>
              </tr>
            </thead>
            <tbody>
              {riskRows.length === 0 ? (
                <tr>
                  <td colSpan={5} className="empty-cell">
                    No storage risk rows loaded yet.
                  </td>
                </tr>
              ) : (
                riskRows.map((row) => (
                  <tr key={`${row.city}:${row.article}:${row.fee_from_date}`}>
                    <td>{row.article}</td>
                    <td>{row.city}</td>
                    <td>{row.fee_from_date}</td>
                    <td>{formatNumber(row.qty_expected_at_fee_start)}</td>
                    <td>{formatNumber(row.estimated_daily_fee_rub)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </article>

      <article className="panel-card panel-card-wide">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Search trends</p>
            <h3>Top niche and product signals</h3>
          </div>
          <span className="status-badge">{String(trendsSnapshot.meta?.cache_source ?? "unknown")}</span>
        </div>
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
              {nicheRows.length + productRows.length === 0 ? (
                <tr>
                  <td colSpan={5} className="empty-cell">
                    No trend signals loaded yet.
                  </td>
                </tr>
              ) : (
                <>
                  {nicheRows.map((row) => (
                    <tr key={`niche:${row.id}`}>
                      <td>Niche</td>
                      <td>{row.title}</td>
                      <td>{formatNumber(row.trend_score)}</td>
                      <td>{formatNumber(row.confidence_score)}</td>
                      <td>{formatNumber(row.risk_score)}</td>
                    </tr>
                  ))}
                  {productRows.map((row) => (
                    <tr key={`product:${row.id}`}>
                      <td>Product</td>
                      <td>{row.title}</td>
                      <td>{formatNumber(row.trend_score)}</td>
                      <td>{formatNumber(row.confidence_score)}</td>
                      <td>{formatNumber(row.risk_score)}</td>
                    </tr>
                  ))}
                </>
              )}
            </tbody>
          </table>
        </div>
      </article>

      <article className="panel-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Tests</p>
            <h3>Recent activity</h3>
          </div>
        </div>
        <div className="list-stack">
          {activityRows.length === 0 ? (
            <p className="muted-copy">No test or bid activity loaded yet.</p>
          ) : (
            activityRows.map((row) => (
              <div className="list-row" key={row.key}>
                <div>
                  <strong>{row.title}</strong>
                  <p>{row.copy}</p>
                </div>
                <span className="status-badge">{row.meta}</span>
              </div>
            ))
          )}
        </div>
      </article>
    </section>
  );
}
