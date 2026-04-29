import type { CSSProperties } from "react";
import type { MainOverview } from "@/shared/api/types";
import { MainRefreshButton } from "@/features/main/components/MainRefreshButton";

type MainDashboardProps = {
  overview: MainOverview;
};

type MetricDirection = "higher" | "lower" | "neutral";
type MetricTone = "good" | "warn" | "bad" | "neutral";
type MetricDomain = Record<string, { min: number; max: number }>;
type DailyRow = MainOverview["daily_rows"][number];
type WeeklyRow = MainOverview["weekly_rows"][number];

const DAILY_METRIC_KEYS = [
  "total_revenue",
  "total_drr_pct",
  "money_spent",
  "views",
  "clicks",
  "ordered_units",
  "ctr",
  "cr",
  "organic_pct",
  "bid_changes_cnt",
] satisfies Array<keyof DailyRow>;

const WEEKLY_METRIC_KEYS = [
  "total_revenue",
  "total_drr_pct",
  "ebitda",
  "ebitda_pct",
  "total_revenue_per_day",
  "money_spent_per_day",
  "views_per_day",
  "clicks_per_day",
  "ordered_units_per_day",
  "ctr",
  "cr",
  "organic_pct",
  "bid_changes_cnt",
] satisfies Array<keyof WeeklyRow>;

const LOWER_IS_BETTER = new Set<string>(["total_drr_pct", "money_spent", "money_spent_per_day", "bid_changes_cnt"]);

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

function buildMetricDomain<T extends Record<string, unknown>>(rows: T[], keys: readonly (keyof T & string)[]): MetricDomain {
  return keys.reduce<MetricDomain>((acc, key) => {
    const values = rows.map((row) => Number(row[key] ?? 0)).filter(Number.isFinite);
    acc[key] = {
      min: values.length > 0 ? Math.min(...values) : 0,
      max: values.length > 0 ? Math.max(...values) : 0,
    };
    return acc;
  }, {});
}

function getMetricDirection(key: string): MetricDirection {
  return LOWER_IS_BETTER.has(key) ? "lower" : "higher";
}

function getIntensity(value: number, domain?: { min: number; max: number }) {
  if (!domain || domain.max === domain.min) {
    return 0;
  }
  return Math.min(1, Math.max(0, (Number(value || 0) - domain.min) / (domain.max - domain.min)));
}

function getMetricTone(intensity: number, direction: MetricDirection): MetricTone {
  if (direction === "neutral") {
    return "neutral";
  }
  const score = direction === "lower" ? 1 - intensity : intensity;
  if (score >= 0.67) {
    return "good";
  }
  if (score >= 0.34) {
    return "warn";
  }
  return "bad";
}

function MetricCell({
  metric,
  value,
  formatted,
  domain,
}: {
  metric: string;
  value: number;
  formatted: string;
  domain: MetricDomain;
}) {
  const direction = getMetricDirection(metric);
  const intensity = getIntensity(value, domain[metric]);
  const tone = getMetricTone(intensity, direction);
  const style = {
    "--metric-fill": `${Math.max(6, Math.round(intensity * 100))}%`,
    "--metric-alpha": (0.16 + intensity * 0.24).toFixed(2),
  } as CSSProperties;

  return (
    <td className={`metric-cell metric-cell-${tone}`} style={style} title={formatted}>
      <span>{formatted}</span>
    </td>
  );
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
  const labelStep = rows.length > 28 ? 6 : rows.length > 21 ? 5 : rows.length > 14 ? 3 : rows.length > 8 ? 2 : 1;
  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((ratio) => {
    const value = minRevenue + (maxRevenue - minRevenue) * (1 - ratio);
    const y = topPad + innerHeight * ratio;
    return { value, y };
  });

  const points = rows.map((row, index) => {
    const revenue = Number(row.total_revenue || 0);
    const x = leftPad + stepX * index;
    const y = topPad + (1 - (revenue - minRevenue) / range) * innerHeight;
    const tooltipWidth = 150;
    const tooltipHeight = 58;
    const tooltipX = Math.min(Math.max(x - tooltipWidth / 2, leftPad), chartWidth - rightPad - tooltipWidth);
    const tooltipY = y - tooltipHeight - 16 < topPad ? y + 16 : y - tooltipHeight - 16;
    return { day: row.day, revenue, x, y, tooltipX, tooltipY, tooltipWidth, tooltipHeight };
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
              <g className="line-chart-point" key={point.day}>
                <circle className="line-chart-hit-area" cx={point.x} cy={point.y} r="13" />
                <circle className="line-chart-dot" cx={point.x} cy={point.y} r="4" />
                <g className="line-chart-tooltip" transform={`translate(${point.tooltipX} ${point.tooltipY})`}>
                  <rect width={point.tooltipWidth} height={point.tooltipHeight} rx="14" />
                  <text x="14" y="22">
                    {formatDay(point.day)}
                  </text>
                  <text className="line-chart-tooltip-value" x="14" y="43">
                    {formatMoney(point.revenue)}
                  </text>
                </g>
                {showLabel ? (
                  <text
                    className="line-chart-label"
                    x={point.x}
                    y={chartHeight - 18}
                    textAnchor="middle"
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
  const metricDomain = buildMetricDomain(rows, WEEKLY_METRIC_KEYS);

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
                  <MetricCell metric="total_revenue" value={row.total_revenue} formatted={formatMoney(row.total_revenue)} domain={metricDomain} />
                  <MetricCell metric="total_drr_pct" value={row.total_drr_pct} formatted={formatPct(row.total_drr_pct)} domain={metricDomain} />
                  <MetricCell metric="ebitda" value={row.ebitda} formatted={formatMoney(row.ebitda)} domain={metricDomain} />
                  <MetricCell metric="ebitda_pct" value={row.ebitda_pct} formatted={formatPct(row.ebitda_pct)} domain={metricDomain} />
                  <MetricCell metric="total_revenue_per_day" value={row.total_revenue_per_day} formatted={formatMoney(row.total_revenue_per_day)} domain={metricDomain} />
                  <MetricCell metric="money_spent_per_day" value={row.money_spent_per_day} formatted={formatMoney(row.money_spent_per_day)} domain={metricDomain} />
                  <MetricCell metric="views_per_day" value={row.views_per_day} formatted={formatInt(row.views_per_day)} domain={metricDomain} />
                  <MetricCell metric="clicks_per_day" value={row.clicks_per_day} formatted={formatInt(row.clicks_per_day)} domain={metricDomain} />
                  <MetricCell metric="ordered_units_per_day" value={row.ordered_units_per_day} formatted={formatInt(row.ordered_units_per_day)} domain={metricDomain} />
                  <MetricCell metric="ctr" value={row.ctr} formatted={formatPct(row.ctr)} domain={metricDomain} />
                  <MetricCell metric="cr" value={row.cr} formatted={formatPct(row.cr)} domain={metricDomain} />
                  <MetricCell metric="organic_pct" value={row.organic_pct} formatted={formatPct(row.organic_pct)} domain={metricDomain} />
                  <MetricCell metric="bid_changes_cnt" value={row.bid_changes_cnt} formatted={formatInt(row.bid_changes_cnt)} domain={metricDomain} />
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
  const metricDomain = buildMetricDomain(rows, DAILY_METRIC_KEYS);

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
                  <MetricCell metric="total_revenue" value={row.total_revenue} formatted={formatMoney(row.total_revenue)} domain={metricDomain} />
                  <MetricCell metric="total_drr_pct" value={row.total_drr_pct} formatted={formatPct(row.total_drr_pct)} domain={metricDomain} />
                  <MetricCell metric="money_spent" value={row.money_spent} formatted={formatMoney(row.money_spent)} domain={metricDomain} />
                  <MetricCell metric="views" value={row.views} formatted={formatInt(row.views)} domain={metricDomain} />
                  <MetricCell metric="clicks" value={row.clicks} formatted={formatInt(row.clicks)} domain={metricDomain} />
                  <MetricCell metric="ordered_units" value={row.ordered_units} formatted={formatInt(row.ordered_units)} domain={metricDomain} />
                  <MetricCell metric="ctr" value={row.ctr} formatted={formatPct(row.ctr)} domain={metricDomain} />
                  <MetricCell metric="cr" value={row.cr} formatted={formatPct(row.cr)} domain={metricDomain} />
                  <MetricCell metric="organic_pct" value={row.organic_pct} formatted={formatPct(row.organic_pct)} domain={metricDomain} />
                  <MetricCell metric="bid_changes_cnt" value={row.bid_changes_cnt} formatted={formatInt(row.bid_changes_cnt)} domain={metricDomain} />
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
