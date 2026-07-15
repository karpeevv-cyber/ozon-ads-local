"use client";

import { useRouter, useSearchParams } from "next/navigation";
import type { CampaignHourlyReport } from "@/shared/api/types";

function formatInt(value: number): string {
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(value);
}

function formatMoney(value: number): string {
  return `${new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(value)} RUB`;
}

function shiftDay(day: string, offset: number): string {
  const [year, month, date] = day.split("-").map((part) => Number.parseInt(part, 10));
  if (!year || !month || !date) {
    return day;
  }
  const shifted = new Date(Date.UTC(year, month - 1, date + offset));
  const shiftedYear = shifted.getUTCFullYear();
  const shiftedMonth = String(shifted.getUTCMonth() + 1).padStart(2, "0");
  const shiftedDate = String(shifted.getUTCDate()).padStart(2, "0");
  return `${shiftedYear}-${shiftedMonth}-${shiftedDate}`;
}

function dateLabel(day: string): string {
  const [year, month, date] = day.split("-");
  return `${date}.${month}.${year}`;
}

export function CampaignHourlyPanel({ report }: { report: CampaignHourlyReport }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const scaleMax = Math.max(1, ...report.rows.flatMap((row) => [row.views, row.clicks, row.orders]));
  const axisTicks = [1, 0.75, 0.5, 0.25, 0].map((factor) => Math.round(scaleMax * factor));
  const totalViews = report.rows.reduce((sum, row) => sum + row.views, 0);
  const totalClicks = report.rows.reduce((sum, row) => sum + row.clicks, 0);
  const totalOrders = report.rows.reduce((sum, row) => sum + row.orders, 0);
  const totalSpend = report.rows.reduce((sum, row) => sum + row.money_spent, 0);
  const sampledHours = report.rows.filter((row) => row.has_data).length;

  function barHeight(value: number): string {
    if (value <= 0) {
      return "0%";
    }
    return `${Math.max(3, (value / scaleMax) * 100)}%`;
  }

  function updateParams(next: { day?: string; campaignId?: string }) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", "campaign-hours");
    params.set("campaign_hourly_day", next.day ?? report.day);
    const campaignId = next.campaignId ?? report.selected_campaign_id;
    if (campaignId) {
      params.set("campaign_hourly_id", campaignId);
    } else {
      params.delete("campaign_hourly_id");
    }
    router.push(`/?${params.toString()}`);
  }

  return (
    <section className="dashboard-grid section-grid campaign-hours-dashboard">
      <article className="panel-card panel-card-wide section-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Campaign hours</p>
            <h3>Clicks and views by hour</h3>
          </div>
          <span className="status-badge">{sampledHours}/24 hours</span>
        </div>

        <div className="campaign-hours-controls">
          <label>
            <span>Date</span>
            <div className="campaign-hours-date-row">
              <button type="button" onClick={() => updateParams({ day: shiftDay(report.day, -1) })}>
                Prev
              </button>
              <input
                type="date"
                value={report.day}
                onChange={(event) => updateParams({ day: event.target.value })}
              />
              <button type="button" onClick={() => updateParams({ day: shiftDay(report.day, 1) })}>
                Next
              </button>
            </div>
          </label>
          <label>
            <span>Campaign</span>
            <select
              value={report.selected_campaign_id}
              onChange={(event) => updateParams({ campaignId: event.target.value })}
            >
              {report.campaigns.length === 0 ? <option value="">No running campaigns</option> : null}
              {report.campaigns.map((campaign) => (
                <option key={campaign.campaign_id} value={campaign.campaign_id}>
                  {campaign.title || campaign.campaign_id}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="chart-summary-grid campaign-hours-summary">
          <div>
            <span>day</span>
            <strong>{dateLabel(report.day)}</strong>
          </div>
          <div>
            <span>spend tracked</span>
            <strong>{formatMoney(totalSpend)}</strong>
          </div>
          <div>
            <span>views tracked</span>
            <strong>{formatInt(totalViews)}</strong>
          </div>
          <div>
            <span>clicks tracked</span>
            <strong>{formatInt(totalClicks)}</strong>
          </div>
          <div>
            <span>orders tracked</span>
            <strong>{formatInt(totalOrders)}</strong>
          </div>
        </div>

        <div className="campaign-hours-chart-shell">
          <div className="campaign-hours-y-axis" aria-hidden="true">
            {axisTicks.map((tick, index) => (
              <span key={`${tick}-${index}`}>{formatInt(tick)}</span>
            ))}
          </div>
          <div className="campaign-hours-chart" aria-label="Hourly clicks, views and orders chart">
            {report.rows.map((row) => (
              <div className={`campaign-hours-slot${row.has_data ? "" : " campaign-hours-slot-empty"}`} key={row.hour}>
                <div className="campaign-hours-bars">
                  <span
                    className="campaign-hours-bar campaign-hours-bar-views"
                    style={{ height: barHeight(row.views) }}
                    title={`${row.label}: ${row.views} views`}
                  />
                  <span
                    className="campaign-hours-bar campaign-hours-bar-clicks"
                    style={{ height: barHeight(row.clicks) }}
                    title={`${row.label}: ${row.clicks} clicks`}
                  />
                  <span
                    className="campaign-hours-bar campaign-hours-bar-orders"
                    style={{ height: barHeight(row.orders) }}
                    title={`${row.label}: ${row.orders} orders`}
                  />
                </div>
                <span className="campaign-hours-hour">{row.hour}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="campaign-hours-legend">
          <span><i className="campaign-hours-legend-views" />views</span>
          <span><i className="campaign-hours-legend-clicks" />clicks</span>
          <span><i className="campaign-hours-legend-orders" />orders</span>
          <span className="muted-copy">Empty hours mean the collector does not yet have two boundary samples.</span>
        </div>
      </article>
    </section>
  );
}
