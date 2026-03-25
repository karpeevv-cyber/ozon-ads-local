import { MainOverview } from "@/shared/api/types";

type MainDashboardProps = {
  overview: MainOverview;
};

function formatDay(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("ru-RU").format(date);
}

function formatInt(value: number) {
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(value ?? 0);
}

function formatMoney(value: number) {
  return `${formatInt(value)} ₽`;
}

function formatPct(value: number) {
  return `${Number(value ?? 0).toFixed(1)}%`;
}

function RevenueChart({ overview }: MainDashboardProps) {
  const rows = overview.chart_rows;
  if (rows.length === 0) {
    return (
      <article className="panel-card panel-card-wide section-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Main</p>
            <h3>Выручка по дням</h3>
          </div>
        </div>
        <p className="muted-copy">Нет данных для графика.</p>
      </article>
    );
  }

  const maxRevenue = Math.max(...rows.map((row) => Number(row.total_revenue || 0)), 1);
  const compactClassName = rows.length > 18 ? " revenue-chart-compact" : rows.length > 12 ? " revenue-chart-tight" : "";

  return (
    <article className="panel-card panel-card-wide section-card">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Main</p>
          <h3>Выручка по дням</h3>
        </div>
        <span className="status-badge">{overview.date_from} to {overview.date_to}</span>
      </div>
      <div
        className={`revenue-chart${compactClassName}`}
        style={{ gridTemplateColumns: `repeat(${rows.length}, minmax(0, 1fr))` }}
      >
        {rows.map((row) => {
          const revenue = Number(row.total_revenue || 0);
          const height = Math.max(8, (revenue / maxRevenue) * 180);
          return (
            <div className="chart-col" key={row.day}>
              <div className="chart-value">{formatMoney(revenue)}</div>
              <div className="chart-bar-wrap">
                <div className="chart-bar" style={{ height: `${height}px` }} />
              </div>
              <div className="chart-label">{formatDay(row.day)}</div>
            </div>
          );
        })}
      </div>
    </article>
  );
}

function WeeklyTable({ overview }: MainDashboardProps) {
  const rows = overview.weekly_rows;
  return (
    <article className="panel-card panel-card-wide section-card">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Main</p>
          <h3>Итоги по неделям (за период)</h3>
        </div>
        <span className="status-badge">{rows.length} weeks</span>
      </div>
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>week</th>
              <th>revenue</th>
              <th>drr</th>
              <th>ebitda</th>
              <th>ebitda_pct</th>
              <th>revenue/day</th>
              <th>spent/day</th>
              <th>views/day</th>
              <th>clicks/day</th>
              <th>units/day</th>
              <th>ctr</th>
              <th>cr</th>
              <th>organic_pct</th>
              <th>bid_changes_cnt</th>
              <th>comment</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={15} className="empty-cell">
                  Нет weekly-данных.
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={row.week}>
                  <td>{formatDay(row.week)}</td>
                  <td>{formatMoney(row.total_revenue)}</td>
                  <td>{formatPct(row.total_drr_pct)}</td>
                  <td>{formatMoney(row.ebitda)}</td>
                  <td>{formatPct(row.ebitda_pct)}</td>
                  <td>{formatMoney(row.total_revenue_per_day)}</td>
                  <td>{formatMoney(row.money_spent_per_day)}</td>
                  <td>{formatInt(row.views_per_day)}</td>
                  <td>{formatInt(row.clicks_per_day)}</td>
                  <td>{formatInt(row.ordered_units_per_day)}</td>
                  <td>{formatPct(row.ctr)}</td>
                  <td>{formatPct(row.cr)}</td>
                  <td>{formatPct(row.organic_pct)}</td>
                  <td>{formatInt(row.bid_changes_cnt)}</td>
                  <td className="comment-cell">{row.comment || ""}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </article>
  );
}

function DailyTable({ overview }: MainDashboardProps) {
  const rows = overview.daily_rows;
  return (
    <article className="panel-card panel-card-wide section-card">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Main</p>
          <h3>Итоги по дням (за период)</h3>
        </div>
        <span className="status-badge">{rows.length} days</span>
      </div>
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>day</th>
              <th>total_revenue</th>
              <th>total_drr_pct</th>
              <th>money_spent</th>
              <th>views</th>
              <th>clicks</th>
              <th>ordered_units</th>
              <th>ctr</th>
              <th>cr</th>
              <th>organic_pct</th>
              <th>bid_changes_cnt</th>
              <th>comment</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={12} className="empty-cell">
                  Нет daily-данных.
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={row.day}>
                  <td>{formatDay(row.day)}</td>
                  <td>{formatMoney(row.total_revenue)}</td>
                  <td>{formatPct(row.total_drr_pct)}</td>
                  <td>{formatMoney(row.money_spent)}</td>
                  <td>{formatInt(row.views)}</td>
                  <td>{formatInt(row.clicks)}</td>
                  <td>{formatInt(row.ordered_units)}</td>
                  <td>{formatPct(row.ctr)}</td>
                  <td>{formatPct(row.cr)}</td>
                  <td>{formatPct(row.organic_pct)}</td>
                  <td>{formatInt(row.bid_changes_cnt)}</td>
                  <td className="comment-cell">{row.comment || ""}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </article>
  );
}

export function MainDashboard({ overview }: MainDashboardProps) {
  return (
    <section className="dashboard-grid section-grid">
      <RevenueChart overview={overview} />
      <WeeklyTable overview={overview} />
      <DailyTable overview={overview} />
    </section>
  );
}
