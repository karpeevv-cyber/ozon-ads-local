"use client";

import type { CSSProperties, FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { addCampaignComment, applyBid } from "@/shared/api/client";
import type { CurrentCampaignDetail, CurrentCampaignMetricRow } from "@/shared/api/types";

type MetricTone = "good" | "warn" | "bad" | "neutral";

const weeklyColumns: Array<keyof CurrentCampaignMetricRow> = [
  "week",
  "days_in_period",
  "views",
  "clicks",
  "ctr",
  "cr",
  "money_spent",
  "click_price",
  "total_revenue",
  "ordered_units",
  "total_drr_pct",
  "bid_change",
  "comment",
  "comment_all",
];

const dailyColumns: Array<keyof CurrentCampaignMetricRow> = [
  "day",
  "money_spent",
  "views",
  "clicks",
  "click_price",
  "orders_money_ads",
  "total_revenue",
  "ordered_units",
  "total_drr_pct",
  "ctr",
  "cr",
  "bid_change",
  "comment",
  "comment_all",
];

const totalsColumns: Array<keyof CurrentCampaignMetricRow> = [
  "views",
  "clicks",
  "ctr",
  "cr",
  "money_spent",
  "click_price",
  "total_revenue",
  "ordered_units",
  "total_drr_pct",
];

const fillMetrics = new Set(["views", "clicks", "money_spent", "total_revenue", "ctr", "cr", "total_drr_pct"]);
const compactColumns = new Set(["bid_change", "comment", "comment_all"]);

function formatDate(value?: string | null) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("ru-RU").format(date);
}

function formatValue(key: keyof CurrentCampaignMetricRow, value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (key === "week" || key === "day") {
    return formatDate(String(value));
  }
  if (key === "ctr" || key === "cr" || key === "total_drr_pct") {
    return `${Number(value).toFixed(1)}%`;
  }
  if (typeof value === "number") {
    return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: key === "click_price" || key === "target_cpc" ? 1 : 0 }).format(value);
  }
  return String(value);
}

function columnLabel(column: keyof CurrentCampaignMetricRow) {
  if (column === "days_in_period") {
    return "days";
  }
  if (column === "orders_money_ads") {
    return "orders_ads";
  }
  return column;
}

function domain(rows: CurrentCampaignMetricRow[], key: keyof CurrentCampaignMetricRow) {
  return Math.max(0, ...rows.map((row) => Number(row[key] ?? 0)).filter(Number.isFinite));
}

function fillStyle(value: unknown, max: number): CSSProperties {
  const num = Number(value ?? 0);
  const intensity = max > 0 ? Math.min(1, Math.max(0, num / max)) : 0;
  return {
    "--metric-fill-scale": intensity.toFixed(4),
    "--metric-alpha": (0.16 + intensity * 0.24).toFixed(2),
  } as CSSProperties;
}

function tone(key: keyof CurrentCampaignMetricRow, value: unknown, max: number): MetricTone {
  if (key === "money_spent" || key === "total_revenue") {
    return "neutral";
  }
  if (key === "views" || key === "clicks") {
    return "neutral";
  }
  const num = Number(value ?? 0);
  if (key === "total_drr_pct") {
    if (num <= 15) return "good";
    if (num <= 25) return "warn";
    return "bad";
  }
  const intensity = max > 0 ? Math.min(1, Math.max(0, num / max)) : 0;
  if (intensity >= 0.67) return "good";
  if (intensity >= 0.34) return "warn";
  return "bad";
}

function MetricsTable({
  rows,
  columns,
  empty,
}: {
  rows: CurrentCampaignMetricRow[];
  columns: Array<keyof CurrentCampaignMetricRow>;
  empty: string;
}) {
  const domains = Object.fromEntries([...fillMetrics].map((key) => [key, domain(rows, key as keyof CurrentCampaignMetricRow)]));
  return (
    <div className="campaign-table-wrap">
      <table className="data-table campaign-table current-campaign-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{columnLabel(column)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="empty-cell">
                {empty}
              </td>
            </tr>
          ) : (
            rows.map((row, index) => (
              <tr key={`${row.day || row.week || "row"}:${index}`}>
                {columns.map((column) => {
                  const formatted = formatValue(column, row[column]);
                  const fill = fillMetrics.has(String(column));
                  const max = Number(domains[String(column)] ?? 0);
                  return (
                    <td
                      key={column}
                      title={compactColumns.has(String(column)) ? formatted : undefined}
                      style={fill ? fillStyle(row[column], max) : undefined}
                      className={[
                        typeof row[column] === "number" ? "campaign-number-cell" : "",
                        compactColumns.has(String(column)) ? "campaign-compact-cell" : "",
                        fill ? `metric-cell metric-cell-${tone(column, row[column], max)}` : "",
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
  );
}

function testCommentPayload(detail: CurrentCampaignDetail, targetClicks: string, essence: string, expectations: string, note: string) {
  return `__test_meta__:${JSON.stringify({
    start_date: new Date().toISOString().slice(0, 10),
    target_clicks: Number(targetClicks || 0),
    essence,
    expectations,
    note,
    company: detail.company,
  })}`;
}

export function CurrentCampaignsPanel({
  detail,
  embedded = false,
  onReload,
}: {
  detail: CurrentCampaignDetail;
  embedded?: boolean;
  onReload?: () => void | Promise<void>;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [bidRub, setBidRub] = useState(detail.current_bid_rub?.toString() || "");
  const [campaignQuery, setCampaignQuery] = useState(detail.selected_campaign_title || "");
  const [campaignListOpen, setCampaignListOpen] = useState(false);
  const [reason, setReason] = useState("Рост продаж");
  const [comment, setComment] = useState("");
  const [targetClicks, setTargetClicks] = useState("");
  const [essence, setEssence] = useState("");
  const [expectations, setExpectations] = useState("");
  const [commentDay, setCommentDay] = useState(detail.date_to);
  const [commentText, setCommentText] = useState("");
  const [commentAll, setCommentAll] = useState(false);
  const [status, setStatus] = useState("");
  const [toast, setToast] = useState("");
  const [pending, setPending] = useState(false);

  useEffect(() => {
    setCampaignQuery(detail.selected_campaign_title || "");
  }, [detail.selected_campaign_title]);

  useEffect(() => {
    setBidRub(detail.current_bid_rub?.toString() || "");
    setCommentDay(detail.date_to);
  }, [detail.current_bid_rub, detail.date_to, detail.selected_campaign_id]);

  function selectCampaign(campaignId: string) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", embedded ? "all-campaigns" : "current-campaigns");
    params.set("current_campaign_id", campaignId);
    setCampaignListOpen(false);
    router.push(`/?${params.toString()}`);
  }

  const filteredCampaigns = detail.campaigns.filter((campaign) => {
    const haystack = `${campaign.title} ${campaign.campaign_id}`.toLowerCase();
    return haystack.includes(campaignQuery.trim().toLowerCase());
  });

  function toggleCampaignList() {
    if (campaignListOpen) {
      setCampaignListOpen(false);
      return;
    }
    setCampaignQuery("");
    setCampaignListOpen(true);
  }

  async function submitBid(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!detail.is_single_sku) {
      setStatus("В выбранной кампании несколько SKU. Bid можно менять только для кампании с одним SKU.");
      return;
    }
    setPending(true);
    setStatus("");
    try {
      const payloadComment =
        reason === "Test"
          ? testCommentPayload(detail, targetClicks, essence, expectations, comment)
          : `reason=${reason}; ${comment}`.trim();
      await applyBid({
        company: detail.company,
        campaign_id: detail.selected_campaign_id,
        sku: detail.sku,
        bid_rub: Number(bidRub),
        reason,
        comment: payloadComment,
      });
      setToast("Ставка применена");
      window.setTimeout(() => setToast(""), 2600);
      if (embedded && onReload) {
        await onReload();
      } else {
        router.refresh();
      }
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Failed to apply bid");
    } finally {
      setPending(false);
    }
  }

  async function submitComment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setStatus("");
    try {
      await addCampaignComment({
        company: detail.company,
        campaign_id: commentAll ? "all" : detail.selected_campaign_id,
        day: commentDay,
        comment: commentText,
      });
      setCommentText("");
      setStatus("Comment saved");
      if (embedded && onReload) {
        await onReload();
      } else {
        router.refresh();
      }
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Failed to save comment");
    } finally {
      setPending(false);
    }
  }

  const totals = detail.totals ? [detail.totals] : [];
  const testRows = detail.test_history;
  return (
    <section className="dashboard-grid section-grid current-campaigns-dashboard">
      <article className="panel-card panel-card-wide section-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Current campaigns</p>
            <h3>{detail.selected_campaign_title || "Campaign detail"}</h3>
          </div>
        </div>
        {!detail.selected_campaign_id && embedded ? (
          <p className="muted-copy">Select a campaign in the table above to view bids, comments, tests and detail rows.</p>
        ) : null}
        {!embedded ? (
          <div className="campaign-combobox current-search-row">
            <div className="campaign-combobox-control">
              <input
                className="campaign-select"
                value={campaignQuery}
                onFocus={() => {
                  if (campaignQuery.trim()) {
                    setCampaignListOpen(true);
                  }
                }}
                onChange={(event) => {
                  setCampaignQuery(event.target.value);
                  setCampaignListOpen(true);
                }}
                placeholder="Search campaign by title or ID"
              />
              <button
                className="campaign-combobox-toggle"
                type="button"
                aria-label={campaignListOpen ? "Hide campaigns" : "Show campaigns"}
                onClick={toggleCampaignList}
              >
                ▾
              </button>
            </div>
            {campaignListOpen ? (
              <div className="campaign-combobox-list">
                {filteredCampaigns.slice(0, 40).map((campaign) => (
                  <button key={campaign.campaign_id} type="button" onClick={() => selectCampaign(campaign.campaign_id)}>
                    {campaign.title || `Campaign ${campaign.campaign_id}`} <span>{campaign.campaign_id}</span>
                  </button>
                ))}
                {filteredCampaigns.length === 0 ? <p>No campaigns found.</p> : null}
              </div>
            ) : null}
          </div>
        ) : null}

        {detail.selected_campaign_id ? (
          <div className={embedded ? "current-actions-grid" : "current-top-grid"}>
          <form className="current-form current-form-compact" onSubmit={submitBid}>
            <strong>Bids</strong>
            <input type="number" step="0.01" value={bidRub} onChange={(event) => setBidRub(event.target.value)} placeholder="Bid RUB" required />
            <select value={reason} onChange={(event) => setReason(event.target.value)}>
              <option value="Рост продаж">Рост продаж</option>
              <option value="Снижение остатков">Снижение остатков</option>
              <option value="Снижение ДРР">Снижение ДРР</option>
              <option value="Test">Test</option>
            </select>
            {reason === "Test" ? (
              <>
                <input type="number" min="1" value={targetClicks} onChange={(event) => setTargetClicks(event.target.value)} placeholder="target_clicks" required />
                <input value={essence} onChange={(event) => setEssence(event.target.value)} placeholder="test_essence" required />
                <textarea value={expectations} onChange={(event) => setExpectations(event.target.value)} placeholder="test_expectations" required />
              </>
            ) : null}
            <input value={comment} onChange={(event) => setComment(event.target.value)} placeholder="comment" />
            <button type="submit" disabled={pending || !detail.is_single_sku}>
              {pending ? "Saving..." : "Apply bid"}
            </button>
          </form>

          <form className="current-form current-form-compact" onSubmit={submitComment}>
            <strong>Comments</strong>
            <input type="date" value={commentDay} onChange={(event) => setCommentDay(event.target.value)} required />
            <label className="current-checkbox">
              <input type="checkbox" checked={commentAll} onChange={(event) => setCommentAll(event.target.checked)} />
              all campaigns
            </label>
            <textarea value={commentText} onChange={(event) => setCommentText(event.target.value)} placeholder="Комментарий" required />
            <button type="submit" disabled={pending || (!detail.selected_campaign_id && !commentAll)}>
              {pending ? "Saving..." : "Add comment"}
            </button>
          </form>

          {embedded ? (
            <div className="current-form current-test-card">
              <strong>Test history</strong>
              <div className="campaign-table-wrap current-test-wrap">
                <table className="data-table current-test-table">
                  <thead>
                    <tr>
                      <th>started_at</th>
                      <th>target_clicks</th>
                      <th>status</th>
                      <th>completion_day</th>
                    </tr>
                  </thead>
                  <tbody>
                    {testRows.length === 0 ? (
                      <tr>
                        <td colSpan={4} className="empty-cell">
                          No test history.
                        </td>
                      </tr>
                    ) : (
                      testRows.map((test, index) => (
                        <tr key={`${test.started_at}:${index}`}>
                          <td>{formatDate(test.started_at)}</td>
                          <td>{test.target_clicks}</td>
                          <td>{test.status}</td>
                          <td>{test.completion_day ? formatDate(test.completion_day) : "-"}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}
        </div>
        ) : null}
        {status ? <p className="muted-copy">{status}</p> : null}
      </article>
      {toast ? <div className="current-toast" role="status">{toast}</div> : null}

      {!detail.selected_campaign_id ? null : (
        <>

      {!embedded ? (
        <article className="panel-card panel-card-wide section-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Current campaigns</p>
            <h3>Totals</h3>
          </div>
        </div>
        <MetricsTable
          rows={totals}
          columns={totalsColumns}
          empty="No totals for selected campaign."
        />
      </article>
      ) : null}

      <article className="panel-card panel-card-wide section-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Current campaigns</p>
            <h3>Weekly detail</h3>
          </div>
        </div>
        <MetricsTable rows={detail.weekly_rows} columns={weeklyColumns} empty="No weekly rows." />
      </article>

      <article className="panel-card panel-card-wide section-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Current campaigns</p>
            <h3>Daily detail</h3>
          </div>
        </div>
        <MetricsTable rows={detail.daily_rows} columns={dailyColumns} empty="No daily rows." />
      </article>

      {!embedded ? (
        <article className="panel-card panel-card-wide section-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Tests</p>
            <h3>Test history</h3>
          </div>
        </div>
        <div className="campaign-table-wrap">
          <table className="data-table current-campaign-table">
            <thead>
              <tr>
                <th>started_at</th>
                <th>target_clicks</th>
                <th>status</th>
                <th>completion_day</th>
                <th>essence</th>
                <th>expectations</th>
                <th>note</th>
              </tr>
            </thead>
            <tbody>
              {testRows.length === 0 ? (
                <tr>
                  <td colSpan={7} className="empty-cell">
                    No test history.
                  </td>
                </tr>
              ) : (
                testRows.map((test, index) => (
                  <tr key={`${test.started_at}:${index}`}>
                    <td>{formatDate(test.started_at)}</td>
                    <td>{test.target_clicks}</td>
                    <td>{test.status}</td>
                    <td>{test.completion_day ? formatDate(test.completion_day) : "-"}</td>
                    <td className="campaign-compact-cell" title={test.essence}><span>{test.essence || "-"}</span></td>
                    <td className="campaign-compact-cell" title={test.expectations}><span>{test.expectations || "-"}</span></td>
                    <td className="campaign-compact-cell" title={test.note}><span>{test.note || "-"}</span></td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </article>
      ) : null}
        </>
      )}
    </section>
  );
}
