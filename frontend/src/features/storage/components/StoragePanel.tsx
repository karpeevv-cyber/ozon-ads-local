"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useMemo, useState, useTransition } from "react";
import type { StorageLotRow, StorageRiskRow, StorageSnapshot } from "@/shared/api/types";

type StoragePanelProps = {
  snapshot: StorageSnapshot;
};

function formatDate(value: string | null | undefined) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ru-RU", {
    timeZone: "Europe/Moscow",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatDay(value: string | null | undefined) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(date);
}

function formatNumber(value: unknown, digits = 0) {
  const num = Number(value ?? 0);
  if (!Number.isFinite(num)) return "-";
  return new Intl.NumberFormat("ru-RU", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(num);
}

function boolLabel(value: unknown) {
  return value ? "yes" : "no";
}

function buildRiskRows(lotRows: StorageLotRow[]): StorageRiskRow[] {
  const groups = new Map<string, StorageLotRow[]>();
  for (const row of lotRows) {
    const qty = Number(row.qty_remaining_from_lot ?? 0);
    const days = Number(row.days_until_fee_start ?? 0);
    if (qty <= 0 || days > 90) continue;
    const key = `${row.city || ""}\u0000${row.article || ""}`;
    groups.set(key, [...(groups.get(key) || []), row]);
  }

  const out: StorageRiskRow[] = [];
  for (const rows of groups.values()) {
    const sorted = [...rows].sort((a, b) =>
      String(a.arrival_date || "").localeCompare(String(b.arrival_date || "")) ||
      String(a.fee_from_date || "").localeCompare(String(b.fee_from_date || "")),
    );
    const salesPerDay = Math.max(0, Number((sorted[0] as Record<string, unknown>).sales_per_day ?? 0));
    let prefix = 0;
    sorted.forEach((row, index) => {
      const lotQty = Math.max(0, Number(row.qty_remaining_from_lot ?? 0));
      prefix += lotQty;
      const prevPrefix = prefix - lotQty;
      const days = Math.max(0, Number(row.days_until_fee_start ?? 0));
      const soldUntilFee = salesPerDay * days;
      const remUpToCurrent = Math.max(0, prefix - soldUntilFee);
      const remUpToPrev = Math.max(0, prevPrefix - soldUntilFee);
      const qtyExpected = Math.max(0, Math.min(lotQty, remUpToCurrent - remUpToPrev));
      if (qtyExpected <= 0) return;
      const volume = Math.max(0, Number(row.item_volume_liters ?? 0)) * qtyExpected;
      out.push({
        city: String(row.city || ""),
        article: String(row.article || ""),
        fee_from_date: String(row.fee_from_date || ""),
        days_until_fee_start: Math.round(days),
        sales_per_day: Number(salesPerDay.toFixed(3)),
        qty_remaining_now: Math.round(lotQty),
        qty_expected_at_fee_start: Math.round(qtyExpected),
        volume_expected_liters: Number(volume.toFixed(3)),
        estimated_daily_fee_rub: Number((volume * 2.5).toFixed(2)),
      });
    });
  }
  return out.sort((a, b) =>
    a.fee_from_date.localeCompare(b.fee_from_date) ||
    a.city.localeCompare(b.city) ||
    a.article.localeCompare(b.article),
  );
}

function StorageRefreshButton() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();

  function refresh() {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", "storage");
    params.set("storage_refresh", String(Date.now()));
    startTransition(() => router.push(`/?${params.toString()}`));
  }

  return (
    <button type="button" className="icon-button" onClick={refresh} disabled={isPending} title="Reload Storage cache">
      ↻
    </button>
  );
}

export function StoragePanel({ snapshot }: StoragePanelProps) {
  const [city, setCity] = useState("ALL");
  const [article, setArticle] = useState("ALL");
  const [stockState, setStockState] = useState("ALL");
  const [feeState, setFeeState] = useState("ALL");

  const cityOptions = useMemo(
    () => ["ALL", ...Array.from(new Set(snapshot.lot_rows.map((row) => String(row.city || "")).filter(Boolean))).sort()],
    [snapshot.lot_rows],
  );
  const articleOptions = useMemo(
    () => ["ALL", ...Array.from(new Set(snapshot.lot_rows.map((row) => String(row.article || "")).filter(Boolean))).sort()],
    [snapshot.lot_rows],
  );

  const filteredLots = useMemo(() => {
    return snapshot.lot_rows
      .filter((row) => city === "ALL" || String(row.city || "") === city)
      .filter((row) => article === "ALL" || String(row.article || "") === article)
      .filter((row) => {
        if (stockState === "ALL") return true;
        return stockState === "IN_STOCK" ? Boolean(row.in_current_stock) : !row.in_current_stock;
      })
      .filter((row) => {
        if (feeState === "ALL") return true;
        return feeState === "STARTED" ? Boolean(row.fee_started) : !row.fee_started;
      })
      .sort((a, b) =>
        String(a.fee_from_date || "").localeCompare(String(b.fee_from_date || "")) ||
        String(a.arrival_date || "").localeCompare(String(b.arrival_date || "")) ||
        String(a.city || "").localeCompare(String(b.city || "")) ||
        String(a.article || "").localeCompare(String(b.article || "")),
      );
  }, [article, city, feeState, snapshot.lot_rows, stockState]);

  const riskRows = useMemo(() => buildRiskRows(filteredLots), [filteredLots]);
  const totalDailyFee = filteredLots.reduce((sum, row) => sum + Number(row.daily_storage_fee_rub ?? 0), 0);
  const projectedDailyFee = riskRows.reduce((sum, row) => sum + Number(row.estimated_daily_fee_rub ?? 0), 0);

  function resetFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCity("ALL");
    setArticle("ALL");
    setStockState("ALL");
    setFeeState("ALL");
  }

  return (
    <section className="section-grid storage-panel-section">
      <article className="panel-card section-card storage-panel-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Storage</p>
            <h3>Storage (shipments, FIFO, 120 days)</h3>
          </div>
          <div className="main-header-actions">
            <StorageRefreshButton />
          </div>
        </div>

        <div className="storage-meta">
          <span>As of: {formatDate(snapshot.cache_updated_at)}</span>
          {snapshot.cache_source ? <span>Source: {snapshot.cache_source.split(/[\\/]/).pop()}</span> : null}
          <span>FIFO: sales consume oldest lots first; fee starts after 120 days.</span>
        </div>

        <div className="storage-summary-grid">
          <div><span>SKUs checked</span><strong>{formatNumber(snapshot.sku_count)}</strong></div>
          <div><span>Supply orders</span><strong>{formatNumber(snapshot.order_count)}</strong></div>
          <div><span>Shipment lots</span><strong>{formatNumber(snapshot.ship_lot_count)}</strong></div>
          <div><span>Stock articles</span><strong>{formatNumber(snapshot.stock_articles_count)}</strong></div>
          <div><span>Daily fee now</span><strong>{formatNumber(totalDailyFee, 2)}</strong></div>
          <div><span>Risk daily fee</span><strong>{formatNumber(projectedDailyFee, 2)}</strong></div>
        </div>

        {snapshot.lot_rows.length === 0 ? (
          <p className="muted-copy">Storage cache is empty. Use reload after backend cache is rebuilt.</p>
        ) : (
          <>
            <form className="storage-controls" onSubmit={resetFilters}>
              <label>
                <span>City</span>
                <select value={city} onChange={(event) => setCity(event.target.value)}>
                  {cityOptions.map((item) => <option key={item} value={item}>{item}</option>)}
                </select>
              </label>
              <label>
                <span>Article</span>
                <select value={article} onChange={(event) => setArticle(event.target.value)}>
                  {articleOptions.map((item) => <option key={item} value={item}>{item}</option>)}
                </select>
              </label>
              <label>
                <span>In current stock</span>
                <select value={stockState} onChange={(event) => setStockState(event.target.value)}>
                  <option value="ALL">ALL</option>
                  <option value="IN_STOCK">IN_STOCK</option>
                  <option value="OUT_OF_STOCK">OUT_OF_STOCK</option>
                </select>
              </label>
              <label>
                <span>Fee started</span>
                <select value={feeState} onChange={(event) => setFeeState(event.target.value)}>
                  <option value="ALL">ALL</option>
                  <option value="STARTED">STARTED</option>
                  <option value="NOT_STARTED">NOT_STARTED</option>
                </select>
              </label>
              <button type="submit" className="stocks-primary-button">Reset filters</button>
            </form>

            <h4 className="storage-table-title">Shipments Table</h4>
            <div className="table-wrap storage-table-wrap">
              <table className="data-table storage-data-table">
                <thead>
                  <tr>
                    <th>city</th>
                    <th>warehouse</th>
                    <th>article</th>
                    <th>liters</th>
                    <th>shipped</th>
                    <th>remaining</th>
                    <th>daily fee</th>
                    <th>projected fee</th>
                    <th>in stock</th>
                    <th>days</th>
                    <th>fee started</th>
                    <th>fee from</th>
                    <th>arrival</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredLots.map((row, index) => (
                    <tr key={`${row.order_id}:${row.bundle_id}:${row.article}:${row.arrival_date}:${index}`}>
                      <td>{row.city}</td>
                      <td>{row.storage_warehouse_name || row.warehouse || "-"}</td>
                      <td>{row.article}</td>
                      <td>{formatNumber(row.item_volume_liters, 3)}</td>
                      <td>{formatNumber(row.shipped_qty)}</td>
                      <td>{formatNumber(row.qty_remaining_from_lot)}</td>
                      <td>{formatNumber(row.daily_storage_fee_rub, 2)}</td>
                      <td>{formatNumber(row.projected_storage_fee_rub, 2)}</td>
                      <td>{boolLabel(row.in_current_stock)}</td>
                      <td>{formatNumber(row.days_until_fee_start)}</td>
                      <td>{boolLabel(row.fee_started)}</td>
                      <td>{formatDay(row.fee_from_date)}</td>
                      <td>{formatDay(row.arrival_date)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <h4 className="storage-table-title">Risk Forecast (not sold by fee start)</h4>
            <div className="table-wrap storage-table-wrap storage-risk-wrap">
              <table className="data-table storage-data-table">
                <thead>
                  <tr>
                    <th>city</th>
                    <th>article</th>
                    <th>fee from</th>
                    <th>days</th>
                    <th>sales/day</th>
                    <th>remaining now</th>
                    <th>expected qty</th>
                    <th>expected liters</th>
                    <th>daily fee</th>
                  </tr>
                </thead>
                <tbody>
                  {riskRows.length === 0 ? (
                    <tr><td colSpan={9} className="empty-cell">No risky lots for current filters.</td></tr>
                  ) : riskRows.map((row, index) => (
                    <tr key={`${row.city}:${row.article}:${row.fee_from_date}:${index}`}>
                      <td>{row.city}</td>
                      <td>{row.article}</td>
                      <td>{formatDay(row.fee_from_date)}</td>
                      <td>{row.days_until_fee_start}</td>
                      <td>{formatNumber(row.sales_per_day, 3)}</td>
                      <td>{formatNumber(row.qty_remaining_now)}</td>
                      <td>{formatNumber(row.qty_expected_at_fee_start)}</td>
                      <td>{formatNumber(row.volume_expected_liters, 3)}</td>
                      <td>{formatNumber(row.estimated_daily_fee_rub, 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}

        {snapshot.unknown_stock_rows.length > 0 ? (
          <>
            <h4 className="storage-table-title">Unknown Stock</h4>
            <div className="table-wrap storage-table-wrap">
              <table className="data-table storage-data-table">
                <thead>
                  <tr>
                    {Object.keys(snapshot.unknown_stock_rows[0]).map((key) => <th key={key}>{key}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {snapshot.unknown_stock_rows.map((row, rowIndex) => (
                    <tr key={rowIndex}>
                      {Object.keys(snapshot.unknown_stock_rows[0]).map((key) => (
                        <td key={key}>{String(row[key] ?? "")}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : null}
      </article>
    </section>
  );
}
