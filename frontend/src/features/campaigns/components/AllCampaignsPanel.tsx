"use client";

import type { CSSProperties } from "react";
import { useState } from "react";
import { getCurrentCampaignDetail } from "@/shared/api/client";
import { CurrentCampaignsPanel } from "@/features/campaigns/components/CurrentCampaignsPanel";
import { CampaignReport, CampaignReportRow, CurrentCampaignDetail } from "@/shared/api/types";

type SortKey = keyof CampaignReportRow;
type SortDirection = "asc" | "desc";

type CampaignColumn = {
  key: SortKey;
  label: string;
  numeric?: boolean;
  className?: string;
  compact?: boolean;
};

const columns: CampaignColumn[] = [
  { key: "article", label: "article" },
  { key: "views", label: "views", numeric: true },
  { key: "clicks", label: "clicks", numeric: true },
  { key: "money_spent", label: "money_spent", numeric: true },
  { key: "total_revenue", label: "revenue", numeric: true },
  { key: "total_drr_pct", label: "drr", numeric: true },
  { key: "orders_money_ads", label: "orders", numeric: true },
  { key: "ordered_units", label: "ordered", numeric: true },
  { key: "ctr", label: "ctr", numeric: true },
  { key: "cr", label: "cr", numeric: true },
  { key: "bid", label: "bid", numeric: true },
  { key: "bid_change", label: "Bid change", compact: true },
  { key: "test", label: "Test", compact: true },
  { key: "comment", label: "comment", compact: true },
  { key: "comment_all", label: "comment_all", compact: true },
];

function asNumber(value: unknown): number {
  if (typeof value === "number") {
    return value;
  }
  const parsed = Number(String(value ?? "").replace(/\s/g, "").replace(",", "."));
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatValue(row: CampaignReportRow, column: CampaignColumn): string {
  const value = row[column.key];
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return String(value);
}

function drrClass(value: string): string {
  const drr = asNumber(value);
  if (drr <= 0) {
    return "campaign-drr-neutral";
  }
  if (drr <= 15) {
    return "campaign-drr-good";
  }
  if (drr <= 25) {
    return "campaign-drr-warn";
  }
  return "campaign-drr-bad";
}

function buildDomain(rows: CampaignReportRow[], key: SortKey): { max: number } {
  return {
    max: Math.max(0, ...rows.map((row) => asNumber(row[key])).filter(Number.isFinite)),
  };
}

function fillStyle(value: unknown, max: number): CSSProperties {
  const intensity = max > 0 ? Math.min(1, Math.max(0, asNumber(value) / max)) : 0;
  return {
    "--metric-fill-scale": intensity.toFixed(4),
    "--metric-alpha": (0.16 + intensity * 0.24).toFixed(2),
  } as CSSProperties;
}

function metricTone(key: SortKey, value: unknown, max: number): string {
  if (key === "money_spent" || key === "total_revenue" || key === "views" || key === "clicks") {
    return "neutral";
  }
  const intensity = max > 0 ? Math.min(1, Math.max(0, asNumber(value) / max)) : 0;
  if (intensity >= 0.67) {
    return "good";
  }
  if (intensity >= 0.34) {
    return "warn";
  }
  return "bad";
}

export function AllCampaignsPanel({ report, currentDetail }: { report: CampaignReport; currentDetail: CurrentCampaignDetail }) {
  const [selectedDetail, setSelectedDetail] = useState(currentDetail);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("article");
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");

  const grandTotal = report.rows.find((row) => row.campaign_id === "GRAND_TOTAL");
  const query = search.trim().toLowerCase();
  const reportRows = report.rows
    .filter((row) => row.campaign_id !== "GRAND_TOTAL")
    .filter((row) => {
      if (!query) {
        return true;
      }
      return [row.campaign_id, row.sku, row.article, row.title, row.comment, row.comment_all]
        .join(" ")
        .toLowerCase()
        .includes(query);
    })
    .sort((left, right) => {
      const column = columns.find((item) => item.key === sortKey);
      const multiplier = sortDirection === "asc" ? 1 : -1;
      if (column?.numeric) {
        return (asNumber(left[sortKey]) - asNumber(right[sortKey])) * multiplier;
      }
      return String(left[sortKey] ?? "").localeCompare(String(right[sortKey] ?? ""), "ru") * multiplier;
    });
  const fillDomains = {
    views: buildDomain(reportRows, "views"),
    clicks: buildDomain(reportRows, "clicks"),
    money_spent: buildDomain(reportRows, "money_spent"),
    total_revenue: buildDomain(reportRows, "total_revenue"),
    ctr: buildDomain(reportRows, "ctr"),
    cr: buildDomain(reportRows, "cr"),
  };

  function toggleSort(nextKey: SortKey) {
    if (nextKey === sortKey) {
      setSortDirection(sortDirection === "asc" ? "desc" : "asc");
      return;
    }
    setSortKey(nextKey);
    setSortDirection(columns.find((column) => column.key === nextKey)?.numeric ? "desc" : "asc");
  }

  async function loadCampaignDetail(campaignId: string) {
    setDetailLoading(true);
    setDetailError("");
    try {
      const nextDetail = await getCurrentCampaignDetail({
        company: report.company,
        dateFrom: report.date_from,
        dateTo: report.date_to,
        campaignId,
        targetDrrPct: report.target_drr_pct,
      });
      setSelectedDetail(nextDetail);
    } catch (error) {
      setDetailError(error instanceof Error ? error.message : "Failed to load campaign detail");
    } finally {
      setDetailLoading(false);
    }
  }

  function selectCampaign(campaignId: string) {
    if (campaignId === selectedDetail.selected_campaign_id || detailLoading) {
      return;
    }
    void loadCampaignDetail(campaignId);
  }

  return (
    <section className="dashboard-grid section-grid all-campaigns-dashboard">
      <article className="panel-card panel-card-wide section-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">All campaigns</p>
            <h3>Grand total</h3>
          </div>
        </div>
        {grandTotal ? (
          <div className="summary-grid campaign-summary-grid">
            <div>
              <span>drr</span>
              <strong>{grandTotal.total_drr_pct}%</strong>
            </div>
            <div>
              <span>ctr</span>
              <strong>{grandTotal.ctr}%</strong>
            </div>
            <div>
              <span>cr</span>
              <strong>{grandTotal.cr}%</strong>
            </div>
          </div>
        ) : (
          <p className="muted-copy">Grand total is empty for selected period.</p>
        )}
      </article>

      <article className="panel-card panel-card-wide section-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">All campaigns</p>
            <h3>Campaigns by period</h3>
          </div>
          <div className="campaign-toolbar">
            <input
              aria-label="Search campaigns"
              placeholder="Search ID, SKU, article, comment"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
        </div>
        <div className="campaign-table-wrap">
          <table className="data-table campaign-table">
            <thead>
              <tr>
                {columns.map((column) => (
                  <th key={column.key}>
                    <button type="button" onClick={() => toggleSort(column.key)}>
                      {column.label}
                      {sortKey === column.key ? <span>{sortDirection === "asc" ? " ↑" : " ↓"}</span> : null}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {reportRows.length === 0 ? (
                <tr>
                  <td colSpan={columns.length} className="empty-cell">
                    No report rows returned by the backend for selected filters.
                  </td>
                </tr>
              ) : (
                reportRows.map((row, index) => (
                  <tr
                    key={`${row.campaign_id}:${row.sku || "all"}:${index}`}
                    className={row.campaign_id === selectedDetail.selected_campaign_id ? "campaign-row-selected" : "campaign-row-clickable"}
                    onClick={() => selectCampaign(row.campaign_id)}
                  >
                    {columns.map((column) => {
                      const formatted = formatValue(row, column);
                      const isFillMetric =
                        column.key === "money_spent" ||
                        column.key === "total_revenue" ||
                        column.key === "views" ||
                        column.key === "clicks" ||
                        column.key === "ctr" ||
                        column.key === "cr";
                      const domain = isFillMetric ? fillDomains[column.key as keyof typeof fillDomains] : undefined;
                      return (
                        <td
                          key={column.key}
                          title={column.compact ? formatted : undefined}
                          style={domain ? fillStyle(row[column.key], domain.max) : undefined}
                          className={[
                            column.className || "",
                            column.numeric ? "campaign-number-cell" : "",
                            column.compact ? "campaign-compact-cell" : "",
                            isFillMetric && domain ? `metric-cell metric-cell-${metricTone(column.key, row[column.key], domain.max)}` : "",
                            column.key === "total_drr_pct" ? drrClass(row.total_drr_pct) : "",
                          ]
                            .filter(Boolean)
                            .join(" ")}
                        >
                          <span>{formatted}</span>
                        </td>
                      );
                    })}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </article>
      {detailLoading ? (
        <article className="panel-card panel-card-wide section-card skeleton-card">
          <div className="skeleton-line skeleton-line-lg" />
          <div className="skeleton-grid">
            {Array.from({ length: 6 }).map((_, idx) => (
              <span className="skeleton-cell" key={idx} />
            ))}
          </div>
        </article>
      ) : null}
      {detailError ? (
        <article className="panel-card panel-card-wide section-card">
          <p className="muted-copy">{detailError}</p>
        </article>
      ) : null}
      <CurrentCampaignsPanel
        detail={selectedDetail}
        embedded
        onReload={() => selectedDetail.selected_campaign_id ? loadCampaignDetail(selectedDetail.selected_campaign_id) : undefined}
      />
    </section>
  );
}
