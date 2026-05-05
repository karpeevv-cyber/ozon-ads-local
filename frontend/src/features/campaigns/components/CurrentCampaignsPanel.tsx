"use client";

import type { CSSProperties, FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

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
  "ipo",
  "money_spent",
  "click_price",
  "cpm",
  "target_cpc",
  "total_revenue",
  "ordered_units",
  "total_drr_pct",
  "bid_change",
  "comment",
  "comment_all",
];

const dailyColumns: Array<keyof CurrentCampaignMetricRow> = [
  "day",
  "article",
  "money_spent",
  "views",
  "clicks",
  "click_price",
  "orders_money_ads",
  "cpm",
  "total_revenue",
  "ordered_units",
  "total_drr_pct",
  "ctr",
  "cr",
  "ipo",
  "bid_change",
  "comment",
  "comment_all",
];

const fillMetrics = new Set(["money_spent", "total_revenue", "ctr", "cr", "total_drr_pct"]);
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
              <th key={column}>{column}</th>
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

export function CurrentCampaignsPanel({ detail }: { detail: CurrentCampaignDetail }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [bidRub, setBidRub] = useState(detail.current_bid_rub?.toString() || "");
  const [reason, setReason] = useState("Рост продаж");
  const [comment, setComment] = useState("");
  const [targetClicks, setTargetClicks] = useState("");
  const [essence, setEssence] = useState("");
  const [expectations, setExpectations] = useState("");
  const [commentDay, setCommentDay] = useState(detail.date_to);
  const [commentText, setCommentText] = useState("");
  const [commentAll, setCommentAll] = useState(false);
  const [status, setStatus] = useState("");
  const [pending, setPending] = useState(false);

  function selectCampaign(campaignId: string) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", "current-campaigns");
    params.set("current_campaign_id", campaignId);
    router.push(`/?${params.toString()}`);
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
      const result = await applyBid({
        company: detail.company,
        campaign_id: detail.selected_campaign_id,
        sku: detail.sku,
        bid_rub: Number(bidRub),
        reason,
        comment: payloadComment,
      });
      setStatus(`Bid applied: ${result.old_bid_micro ?? "n/a"} -> ${result.new_bid_micro}`);
      router.refresh();
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
      router.refresh();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Failed to save comment");
    } finally {
      setPending(false);
    }
  }

  const totals = detail.totals ? [detail.totals] : [];
  const cpcRange = detail.parameters.cpc_econ
    ? `${detail.parameters.cpc_econ_min ?? "-"} - ${detail.parameters.cpc_econ} - ${detail.parameters.cpc_econ_max ?? "-"}`
    : "-";

  return (
    <section className="dashboard-grid section-grid current-campaigns-dashboard">
      <article className="panel-card panel-card-wide section-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Current campaigns</p>
            <h3>Campaign detail</h3>
          </div>
          <select className="campaign-select" value={detail.selected_campaign_id} onChange={(event) => selectCampaign(event.target.value)}>
            {detail.campaigns.map((campaign) => (
              <option key={campaign.campaign_id} value={campaign.campaign_id}>
                {campaign.title || `Campaign ${campaign.campaign_id}`} | {campaign.campaign_id}
              </option>
            ))}
          </select>
        </div>
        <div className="current-campaign-meta">
          <span>article: {detail.article || "-"}</span>
          <span>sku: {detail.sku || "-"}</span>
          <span>current bid: {detail.current_bid_rub ?? "-"}</span>
          <span>CPC econ: {cpcRange}</span>
        </div>
      </article>

      <article className="panel-card panel-card-wide section-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Current campaigns</p>
            <h3>Totals</h3>
          </div>
        </div>
        <MetricsTable
          rows={totals}
          columns={["days_in_period", "views", "clicks", "ctr", "cr", "ipo", "money_spent", "click_price", "cpm", "target_cpc", "total_revenue", "ordered_units", "total_drr_pct"]}
          empty="No totals for selected campaign."
        />
      </article>

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

      <article className="panel-card panel-card-wide section-card current-actions-card">
        <div>
          <div className="panel-header">
            <div>
              <p className="eyebrow">Bids</p>
              <h3>Apply bid</h3>
            </div>
          </div>
          <form className="current-form" onSubmit={submitBid}>
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
        </div>

        <div>
          <div className="panel-header">
            <div>
              <p className="eyebrow">Comments</p>
              <h3>Campaign comments</h3>
            </div>
          </div>
          <form className="current-form" onSubmit={submitComment}>
            <input type="date" value={commentDay} onChange={(event) => setCommentDay(event.target.value)} required />
            <label className="current-checkbox">
              <input type="checkbox" checked={commentAll} onChange={(event) => setCommentAll(event.target.checked)} />
              all campaigns
            </label>
            <textarea value={commentText} onChange={(event) => setCommentText(event.target.value)} placeholder="Комментарий" required />
            <button type="submit" disabled={pending}>
              {pending ? "Saving..." : "Add comment"}
            </button>
          </form>
          <div className="current-comments-list">
            {detail.comments.length === 0 ? (
              <p className="muted-copy">No comments.</p>
            ) : (
              detail.comments.map((item, index) => (
                <p key={`${item.ts}:${index}`}>
                  <strong>{formatDate(item.day)}</strong> {item.comment}
                </p>
              ))
            )}
          </div>
        </div>
      </article>

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
              {detail.test_history.length === 0 ? (
                <tr>
                  <td colSpan={7} className="empty-cell">
                    No test history.
                  </td>
                </tr>
              ) : (
                detail.test_history.map((test, index) => (
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
        {status ? <p className="muted-copy">{status}</p> : null}
      </article>
    </section>
  );
}
