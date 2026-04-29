import { CampaignReport, CompanyConfig, RunningCampaign } from "@/shared/api/types";

type CampaignOverviewProps = {
  companies: CompanyConfig[];
  campaigns: RunningCampaign[];
  report: CampaignReport;
};

export function CampaignOverview({ companies, campaigns, report }: CampaignOverviewProps) {
  const reportRows = report.rows.filter((row) => row.campaign_id !== "GRAND_TOTAL");
  const grandTotal = report.rows.find((row) => row.campaign_id === "GRAND_TOTAL");

  return (
    <section className="dashboard-grid">
      <article className="hero-card">
        <div className="hero-copy">
          <p className="eyebrow">Migration Dashboard</p>
          <h2>Campaign control is the first end-to-end slice.</h2>
          <p>
            This screen is intentionally opinionated: campaign summary first, then credentials
            visibility, then the active runtime status of the new backend.
          </p>
        </div>
        <div className="hero-metrics">
          <div>
            <span className="metric-label">Companies</span>
            <strong>{companies.length}</strong>
          </div>
          <div>
            <span className="metric-label">Running campaigns</span>
            <strong>{campaigns.length}</strong>
          </div>
          <div>
            <span className="metric-label">Period</span>
            <strong>{report.date_from}</strong>
            <small>{report.date_to}</small>
          </div>
        </div>
      </article>

      <article className="panel-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Summary</p>
            <h3>Grand total</h3>
          </div>
        </div>
        {grandTotal ? (
          <div className="summary-grid">
            <div>
              <span>Spend</span>
              <strong>{grandTotal.money_spent}</strong>
            </div>
            <div>
              <span>Revenue</span>
              <strong>{grandTotal.total_revenue}</strong>
            </div>
            <div>
              <span>DRR %</span>
              <strong>{grandTotal.total_drr_pct}</strong>
            </div>
            <div>
              <span>Units</span>
              <strong>{grandTotal.ordered_units}</strong>
            </div>
          </div>
        ) : (
          <p className="muted-copy">No aggregate row returned yet.</p>
        )}
      </article>

      <article className="panel-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Organizations</p>
            <h3>Company list</h3>
          </div>
        </div>
        <div className="list-stack">
          {companies.map((company) => (
            <div className="list-row" key={company.name}>
              <div>
                <strong>{company.display_name || company.name}</strong>
                <p>{company.name}</p>
              </div>
              <span className="status-badge">available</span>
            </div>
          ))}
        </div>
      </article>

      <article className="panel-card panel-card-wide">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Campaigns</p>
            <h3>Campaign report for the selected period</h3>
          </div>
          <span className="status-badge">{reportRows.length} rows</span>
        </div>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Title</th>
                <th>Spend</th>
                <th>Revenue</th>
                <th>DRR %</th>
                <th>Clicks</th>
              </tr>
            </thead>
            <tbody>
              {reportRows.length === 0 ? (
                <tr>
                  <td colSpan={6} className="empty-cell">
                    No report rows returned by the backend yet.
                  </td>
                </tr>
              ) : (
                reportRows.map((campaign) => (
                  <tr key={campaign.campaign_id}>
                    <td>{campaign.campaign_id}</td>
                    <td>{campaign.title || "Untitled campaign"}</td>
                    <td>{campaign.money_spent}</td>
                    <td>{campaign.total_revenue}</td>
                    <td>{campaign.total_drr_pct}</td>
                    <td>{campaign.clicks}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </article>
    </section>
  );
}
