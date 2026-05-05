"use client";

import { useState } from "react";
import { CampaignReport, CampaignReportRow } from "@/shared/api/types";

type SortKey = keyof CampaignReportRow;
type SortDirection = "asc" | "desc";

type CampaignColumn = {
  key: SortKey;
  label: string;
  numeric?: boolean;
  className?: string;
};

const columns: CampaignColumn[] = [
  { key: "article", label: "article" },
  { key: "views", label: "views", numeric: true },
  { key: "clicks", label: "clicks", numeric: true },
  { key: "click_price", label: "click_price", numeric: true },
  { key: "money_spent", label: "money_spent", numeric: true },
  { key: "total_revenue", label: "revenue", numeric: true },
  { key: "total_drr_pct", label: "drr", numeric: true },
  { key: "orders_money_ads", label: "orders", numeric: true },
  { key: "ordered_units", label: "ordered", numeric: true },
  { key: "ctr", label: "ctr", numeric: true },
  { key: "cr", label: "cr", numeric: true },
  { key: "bid", label: "bid", numeric: true },
  { key: "bid_change", label: "Bid change", className: "comment-cell" },
  { key: "test", label: "Test" },
  { key: "comment", label: "comment", className: "comment-cell" },
  { key: "comment_all", label: "comment_all", className: "comment-cell" },
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

export function AllCampaignsPanel({ report }: { report: CampaignReport }) {
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("total_drr_pct");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");

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

  function toggleSort(nextKey: SortKey) {
    if (nextKey === sortKey) {
      setSortDirection(sortDirection === "asc" ? "desc" : "asc");
      return;
    }
    setSortKey(nextKey);
    setSortDirection(columns.find((column) => column.key === nextKey)?.numeric ? "desc" : "asc");
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
              <strong>{grandTotal.total_drr_pct}</strong>
            </div>
            <div>
              <span>ctr</span>
              <strong>{grandTotal.ctr}</strong>
            </div>
            <div>
              <span>cr</span>
              <strong>{grandTotal.cr}</strong>
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
                  <tr key={`${row.campaign_id}:${row.sku || "all"}:${index}`}>
                    {columns.map((column) => (
                      <td
                        key={column.key}
                        className={[
                          column.className || "",
                          column.numeric ? "campaign-number-cell" : "",
                          column.key === "total_drr_pct" ? drrClass(row.total_drr_pct) : "",
                        ]
                          .filter(Boolean)
                          .join(" ")}
                      >
                        {formatValue(row, column)}
                      </td>
                    ))}
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
