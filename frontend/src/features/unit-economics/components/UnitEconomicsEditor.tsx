"use client";

import { FormEvent, useEffect, useState } from "react";

import { updateUnitEconomicsProducts } from "@/shared/api/client";
import { UnitEconomicsProductRow } from "@/shared/api/types";

type UnitEconomicsEditorProps = {
  company: string;
  rows: UnitEconomicsProductRow[];
};

type EditableRow = {
  sku: string;
  position: string;
  tea_cost: string;
  package_cost: string;
  label_cost: string;
  packing_cost: string;
  is_active: boolean;
};

function toEditableRow(row: UnitEconomicsProductRow): EditableRow {
  return {
    sku: row.sku,
    position: row.name,
    tea_cost: String(row.tea_cost ?? 0),
    package_cost: String(row.package_cost ?? 0),
    label_cost: String(row.label_cost ?? 0),
    packing_cost: String(row.packing_cost ?? 0),
    is_active: row.is_active ?? true,
  };
}

export function UnitEconomicsEditor({ company, rows }: UnitEconomicsEditorProps) {
  const [draftRows, setDraftRows] = useState<EditableRow[]>(() => rows.map(toEditableRow));
  const [status, setStatus] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setDraftRows(rows.map(toEditableRow));
  }, [rows]);

  function updateField(index: number, field: keyof EditableRow, value: string | boolean) {
    setDraftRows((current) =>
      current.map((row, rowIndex) => (rowIndex === index ? { ...row, [field]: value } : row)),
    );
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
          <p className="eyebrow">Unit Economics</p>
          <h3>Edit cost overrides</h3>
        </div>
      </div>
      <form onSubmit={handleSubmit}>
        <div className="table-wrap unit-products-editor-wrap">
          <table className="data-table unit-products-editor-table">
            <thead>
              <tr>
                <th>SKU</th>
                <th>Name</th>
                <th>Tea</th>
                <th>Package</th>
                <th>Label</th>
                <th>Packing</th>
                <th>Discontinued</th>
              </tr>
            </thead>
            <tbody>
              {draftRows.map((row, index) => (
                <tr className={row.is_active ? undefined : "unit-products-inactive"} key={row.sku}>
                  <td>{row.sku}</td>
                  <td>
                    <input
                      type="text"
                      value={row.position}
                      onChange={(event) => updateField(index, "position", event.target.value)}
                      placeholder="Name"
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      step="0.01"
                      value={row.tea_cost}
                      onChange={(event) => updateField(index, "tea_cost", event.target.value)}
                      placeholder="Tea"
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      step="0.01"
                      value={row.package_cost}
                      onChange={(event) => updateField(index, "package_cost", event.target.value)}
                      placeholder="Package"
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      step="0.01"
                      value={row.label_cost}
                      onChange={(event) => updateField(index, "label_cost", event.target.value)}
                      placeholder="Label"
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      step="0.01"
                      value={row.packing_cost}
                      onChange={(event) => updateField(index, "packing_cost", event.target.value)}
                      placeholder="Packing"
                    />
                  </td>
                  <td>
                    <label className="unit-products-discontinued-check">
                      <input
                        type="checkbox"
                        checked={!row.is_active}
                        onChange={(event) => updateField(index, "is_active", !event.target.checked)}
                      />
                      <span>Out</span>
                    </label>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="unit-products-editor-actions">
          <button type="submit" className="stocks-primary-button" disabled={saving}>
            {saving ? "Saving..." : "Save overrides"}
          </button>
        </div>
      </form>
      {status ? <p className="muted-copy">{status}</p> : null}
    </article>
  );
}
