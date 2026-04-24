import { MainOverview } from "@/shared/api/types";
import { MainRefreshButton } from "@/features/main/components/MainRefreshButton";

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

  const revenues = rows.map((row) => Number(row.total_revenue || 0));
  const maxRevenue = Math.max(...revenues, 1);
  const minRevenue = Math.min(...revenues, 0);
  const totalRevenue = revenues.reduce((sum, value) => sum + value, 0);
  const averageRevenue = totalRevenue / rows.length;

  const chartWidth = 1200;
  const chartHeight = 340;
  const leftPad = 76;
  const rightPad = 26;
  const topPad = 22;
  const bottomPad = 66;
  const innerWidth = chartWidth - leftPad - rightPad;
  const innerHeight = chartHeight - topPad - bottomPad;
  const stepX = rows.length > 1 ? innerWidth / (rows.length - 1) : 0;
  const range = maxRevenue - minRevenue || 1;
  const labelStep = rows.length > 28 ? 5 : rows.length > 21 ? 4 : rows.length > 14 ? 3 : rows.length > 8 ? 2 : 1;
  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((ratio) => {
    const value = minRevenue + (maxRevenue - minRevenue) * (1 - ratio);
    const y = topPad + innerHeight * ratio;
    return { value, y };
  });

  const points = rows.map((row, index) => {
    const revenue = Number(row.total_revenue || 0);
    const x = leftPad + stepX * index;
    const y = topPad + (1 - (revenue - minRevenue) / range) * innerHeight;
    return { day: row.day, revenue, x, y };
  });

  const linePath = points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`)
    .join(" ");
  const floorY = chartHeight - bottomPad;
  const areaPath = `${linePath} L ${points[points.length - 1].x.toFixed(1)} ${floorY.toFixed(1)} L ${points[0].x.toFixed(1)} ${floorY.toFixed(1)} Z`;

  return (
    <article className="panel-card panel-card-wide section-card">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Main</p>
          <h3>Выручка по дням</h3>
        </div>
        <div className="main-header-actions">
          <MainRefreshButton />
        </div>
      </div>
      <div className="chart-summary-grid">
        <div>
          <span className="metric-label">За период</span>
          <strong>{formatMoney(totalRevenue)}</strong>
        </div>
        <div>
          <span className="metric-label">В среднем в день</span>
          <strong>{formatMoney(averageRevenue)}</strong>
        </div>
        <div>
          <span className="metric-label">Пиковый день</span>
          <strong>{formatMoney(maxRevenue)}</strong>
        </div>
      </div>
      <div className="line-chart-card">
        <svg
          className="line-chart"
          viewBox={`0 0 ${chartWidth} ${chartHeight}`}
          preserveAspectRatio="none"
          role="img"
          aria-label="Выручка по дням"
        >
          <defs>
            <linearGradient id="revenueArea" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="#ff7d61" stopOpacity="0.30" />
              <stop offset="100%" stopColor="#ff7d61" stopOpacity="0.02" />
            </linearGradient>
          </defs>
          {yTicks.map((tick) => (
            <g key={tick.y}>
              <line className="line-chart-grid" x1={leftPad} x2={chartWidth - rightPad} y1={tick.y} y2={tick.y} />
              <text className="line-chart-y-label" x={leftPad - 12} y={tick.y + 4} textAnchor="end">
                {formatInt(tick.value)}
              </text>
            </g>
          ))}
          <line className="line-chart-axis" x1={leftPad} x2={chartWidth - rightPad} y1={floorY} y2={floorY} />
          <line className="line-chart-axis" x1={leftPad} x2={leftPad} y1={topPad} y2={floorY} />
          <path className="line-chart-area" d={areaPath} />
          <path className="line-chart-path" d={linePath} />
          {points.map((point, index) => {
            const showLabel = index % labelStep === 0 || index === points.length - 1;
            return (
              <g key={point.day}>
                <circle className="line-chart-dot" cx={point.x} cy={point.y} r="4">
                  <title>{`${formatDay(point.day)}: ${formatMoney(point.revenue)}`}</title>
                </circle>
                {showLabel ? (
                  <text
                    className="line-chart-label"
                    x={point.x}
                    y={chartHeight - 18}
                    textAnchor="end"
                    transform={`rotate(-35 ${point.x} ${chartHeight - 18})`}
                  >
                    {formatDay(point.day)}
                  </text>
                ) : null}
              </g>
            );
          })}
        </svg>
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
    <section className="dashboard-grid section-grid main-dashboard">
      <RevenueChart overview={overview} />
      <WeeklyTable overview={overview} />
      <DailyTable overview={overview} />
    </section>
  );
}
