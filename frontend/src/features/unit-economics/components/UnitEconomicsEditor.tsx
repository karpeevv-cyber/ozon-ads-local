"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import { updateUnitEconomicsProducts } from "@/shared/api/client";
import { UnitEconomicsProductRow } from "@/shared/api/types";

type UnitEconomicsEditorProps = {
  company: string;
  rows: UnitEconomicsProductRow[];
};

type EditableRow = {
  sku: string;
  article: string;
  position: string;
  tea_cost: string;
  package_cost: string;
  label_cost: string;
  packing_cost: string;
  is_active: boolean;
};

type ProductShowFilter = "ALL" | "ACTIVE" | "DISCONTINUED";

function toEditableRow(row: UnitEconomicsProductRow): EditableRow {
  return {
    sku: row.sku,
    article: row.article || row.name || row.sku,
    position: row.name,
    tea_cost: String(row.tea_cost ?? 0),
    package_cost: String(row.package_cost ?? 0),
    label_cost: String(row.label_cost ?? 0),
    packing_cost: String(row.packing_cost ?? 0),
    is_active: row.is_active ?? true,
  };
}

function parseCost(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function totalCost(row: EditableRow): number {
  return parseCost(row.tea_cost) + parseCost(row.package_cost) + parseCost(row.label_cost) + parseCost(row.packing_cost);
}

function formatCost(value: number): string {
  return new Intl.NumberFormat("ru-RU", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

export function UnitEconomicsEditor({ company, rows }: UnitEconomicsEditorProps) {
  const [draftRows, setDraftRows] = useState<EditableRow[]>(() => rows.map(toEditableRow));
  const [showFilter, setShowFilter] = useState<ProductShowFilter>("ALL");
  const [isEditing, setIsEditing] = useState(false);
  const [status, setStatus] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setDraftRows(rows.map(toEditableRow));
    setIsEditing(false);
  }, [rows]);

  function updateField(index: number, field: keyof EditableRow, value: string | boolean) {
    setDraftRows((current) =>
      current.map((row, rowIndex) => (rowIndex === index ? { ...row, [field]: value } : row)),
    );
  }

  const visibleRows = useMemo(
    () =>
      draftRows
        .map((row, index) => ({ row, index }))
        .filter(({ row }) => {
          if (showFilter === "ACTIVE") {
            return row.is_active;
          }
          if (showFilter === "DISCONTINUED") {
            return !row.is_active;
          }
          return true;
        })
        .sort((left, right) => {
          const leftArticle = left.row.article || left.row.position || left.row.sku;
          const rightArticle = right.row.article || right.row.position || right.row.sku;
          return leftArticle.localeCompare(rightArticle, "ru");
        }),
    [draftRows, showFilter],
  );

  const discontinuedCount = useMemo(() => draftRows.filter((row) => !row.is_active).length, [draftRows]);

  function exportCsv() {
    const header = [
      "sku",
      "article",
      "name",
      "tea_cost",
      "package_cost",
      "label_cost",
      "packing_cost",
      "total_cost",
      "status",
    ];
    const lines = visibleRows.map(({ row }) =>
      [
        row.sku,
        row.article,
        row.position,
        row.tea_cost,
        row.package_cost,
        row.label_cost,
        row.packing_cost,
        totalCost(row).toFixed(2),
        row.is_active ? "active" : "discontinued",
      ]
        .map((value) => `"${String(value).replaceAll('"', '""')}"`)
        .join(","),
    );
    const blob = new Blob([[header.join(","), ...lines].join("\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `unit-economics-products-${company}-${showFilter.toLowerCase()}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  function readStoredToken(): string | null {
    try {
      return window.localStorage.getItem("ozon_ads_token");
    } catch {
      return null;
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!isEditing) {
      return;
    }
    const token = readStoredToken();
    if (!token) {
      setStatus("Authentication token is missing");
      return;
    }
    setSaving(true);
    setStatus("");
    try {
      const response = await updateUnitEconomicsProducts(
        {
          company,
          rows: draftRows.map((row) => ({
            sku: row.sku,
            position: row.position,
            tea_cost: Number(row.tea_cost),
            package_cost: Number(row.package_cost),
            label_cost: Number(row.label_cost),
            packing_cost: Number(row.packing_cost),
            is_active: row.is_active,
          })),
        },
        token,
      );
      setStatus(`Saved ${response.saved_count} rows`);
      setIsEditing(false);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Failed to save unit economics rows");
    } finally {
      setSaving(false);
    }
  }

  return (
    <article className="panel-card panel-card-wide">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Unit Economics Products</p>
          <h3>Editable SKU cost matrix</h3>
        </div>
        <div className="unit-products-header-actions">
          <label className="unit-products-show-filter">
            <span>Show</span>
            <select value={showFilter} onChange={(event) => setShowFilter(event.target.value as ProductShowFilter)}>
              <option value="ALL">All</option>
              <option value="ACTIVE">Active</option>
              <option value="DISCONTINUED">Out of assortment</option>
            </select>
          </label>
          <button type="button" className="stocks-secondary-button" onClick={exportCsv}>
            Export
          </button>
          <button
            type="button"
            className="stocks-secondary-button"
            disabled={saving || isEditing}
            onClick={() => {
              setStatus("");
              setIsEditing(true);
            }}
          >
            Edit
          </button>
          <button type="submit" className="stocks-primary-button" form="unit-products-editor-form" disabled={saving || !isEditing}>
            {saving ? "Saving..." : "Save changes"}
          </button>
          <span className="status-badge">
            {visibleRows.length} SKU
            {discontinuedCount ? ` / ${discontinuedCount} out` : ""}
          </span>
        </div>
      </div>
      <form id="unit-products-editor-form" onSubmit={handleSubmit}>
        <div className="table-wrap unit-products-editor-wrap">
          <table className="data-table unit-products-editor-table">
            <thead>
              <tr>
                <th>Article</th>
                <th>Tea</th>
                <th>Package</th>
                <th>Label</th>
                <th>Packing</th>
                <th>Total cost</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.length === 0 ? (
                <tr>
                  <td colSpan={7} className="empty-cell">
                    No products matched the current filter.
                  </td>
                </tr>
              ) : null}
              {visibleRows.map(({ row, index }) => (
                <tr className={row.is_active ? undefined : "unit-products-inactive"} key={row.sku}>
                  <td className="unit-product-name-cell">
                    <strong>{row.article || row.position || row.sku}</strong>
                    <span>{row.sku}</span>
                  </td>
                  <td>
                    <input
                      type="number"
                      step="0.01"
                      value={row.tea_cost}
                      disabled={!isEditing || saving}
                      onChange={(event) => updateField(index, "tea_cost", event.target.value)}
                      placeholder="Tea"
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      step="0.01"
                      value={row.package_cost}
                      disabled={!isEditing || saving}
                      onChange={(event) => updateField(index, "package_cost", event.target.value)}
                      placeholder="Package"
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      step="0.01"
                      value={row.label_cost}
                      disabled={!isEditing || saving}
                      onChange={(event) => updateField(index, "label_cost", event.target.value)}
                      placeholder="Label"
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      step="0.01"
                      value={row.packing_cost}
                      disabled={!isEditing || saving}
                      onChange={(event) => updateField(index, "packing_cost", event.target.value)}
                      placeholder="Packing"
                    />
                  </td>
                  <td className="unit-product-total-cell">{formatCost(totalCost(row))}</td>
                  <td>
                    <select
                      className={row.is_active ? "unit-product-status-select" : "unit-product-status-select unit-product-status-out"}
                      value={row.is_active ? "ACTIVE" : "DISCONTINUED"}
                      disabled={!isEditing || saving}
                      onChange={(event) => updateField(index, "is_active", event.target.value === "ACTIVE")}
                    >
                      <option value="ACTIVE">Active</option>
                      <option value="DISCONTINUED">Out of assortment</option>
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </form>
      {status ? <p className="muted-copy">{status}</p> : null}
    </article>
  );
}
