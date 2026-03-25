"use client";

import { FormEvent, useState } from "react";

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
};

function toEditableRow(row: UnitEconomicsProductRow): EditableRow {
  return {
    sku: row.sku,
    position: row.name,
    tea_cost: String(row.tea_cost ?? 0),
    package_cost: String(row.package_cost ?? 0),
    label_cost: String(row.label_cost ?? 0),
    packing_cost: String(row.packing_cost ?? 0),
  };
}

export function UnitEconomicsEditor({ company, rows }: UnitEconomicsEditorProps) {
  const [draftRows, setDraftRows] = useState<EditableRow[]>(() => rows.slice(0, 6).map(toEditableRow));
  const [status, setStatus] = useState("");
  const [saving, setSaving] = useState(false);

  function updateField(index: number, field: keyof EditableRow, value: string) {
    setDraftRows((current) =>
      current.map((row, rowIndex) => (rowIndex === index ? { ...row, [field]: value } : row)),
    );
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const token = window.localStorage.getItem("ozon_ads_token");
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
      <form className="bid-form" onSubmit={handleSubmit}>
        {draftRows.map((row, index) => (
          <div className="list-row" key={row.sku}>
            <div style={{ width: "100%" }}>
              <strong>{row.sku}</strong>
              <div className="bid-form">
                <input
                  type="text"
                  value={row.position}
                  onChange={(event) => updateField(index, "position", event.target.value)}
                  placeholder="Name"
                />
                <input
                  type="number"
                  step="0.01"
                  value={row.tea_cost}
                  onChange={(event) => updateField(index, "tea_cost", event.target.value)}
                  placeholder="Tea"
                />
                <input
                  type="number"
                  step="0.01"
                  value={row.package_cost}
                  onChange={(event) => updateField(index, "package_cost", event.target.value)}
                  placeholder="Package"
                />
                <input
                  type="number"
                  step="0.01"
                  value={row.label_cost}
                  onChange={(event) => updateField(index, "label_cost", event.target.value)}
                  placeholder="Label"
                />
                <input
                  type="number"
                  step="0.01"
                  value={row.packing_cost}
                  onChange={(event) => updateField(index, "packing_cost", event.target.value)}
                  placeholder="Packing"
                />
              </div>
            </div>
          </div>
        ))}
        <button type="submit" disabled={saving}>
          {saving ? "Saving..." : "Save overrides"}
        </button>
      </form>
      {status ? <p className="muted-copy">{status}</p> : null}
    </article>
  );
}
