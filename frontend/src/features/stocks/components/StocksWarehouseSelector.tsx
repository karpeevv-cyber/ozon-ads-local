"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { updateStocksWarehousePreferences } from "@/shared/api/client";
import type { StocksWorkspaceColumn } from "@/shared/api/types";

type StocksWarehouseSelectorProps = {
  company: string;
  columns: StocksWorkspaceColumn[];
};

export function StocksWarehouseSelector({ company, columns }: StocksWarehouseSelectorProps) {
  const router = useRouter();
  const [selectedKeys, setSelectedKeys] = useState(
    () => new Set(columns.filter((column) => column.is_used_for_shipments).map((column) => column.city_key)),
  );
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isPending, startTransition] = useTransition();

  function toggleCity(cityKey: string) {
    setSaved(false);
    setError(null);
    setSelectedKeys((current) => {
      const next = new Set(current);
      if (next.has(cityKey)) {
        next.delete(cityKey);
      } else {
        next.add(cityKey);
      }
      return next;
    });
  }

  async function save() {
    setError(null);
    setSaved(false);
    setIsSaving(true);
    try {
      const response = await updateStocksWarehousePreferences({
        company,
        city_keys: Array.from(selectedKeys),
      });
      setSelectedKeys(new Set(response.used_city_keys));
      setSaved(true);
      startTransition(() => {
        router.refresh();
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save warehouse settings");
    } finally {
      setIsSaving(false);
    }
  }

  if (columns.length === 0) {
    return null;
  }

  return (
    <div className="stocks-warehouse-selector">
      <div className="stocks-warehouse-selector-header">
        <div>
          <p className="eyebrow">Shipping warehouses</p>
          <h4>Used for shipments</h4>
        </div>
        <button className="stocks-primary-button" type="button" onClick={save} disabled={isSaving || isPending}>
          {isSaving || isPending ? "Saving..." : "Save warehouses"}
        </button>
      </div>
      <div className="stocks-warehouse-grid">
        {columns.map((column) => (
          <label className="stocks-warehouse-check" key={`${column.city_key}:${column.city}`}>
            <input
              type="checkbox"
              checked={selectedKeys.has(column.city_key)}
              onChange={() => toggleCity(column.city_key)}
            />
            <span>{column.city}</span>
            <small>{column.shipment_total_qty}</small>
          </label>
        ))}
      </div>
      {saved ? <p className="stocks-warehouse-status">Saved. Table order will update after refresh.</p> : null}
      {error ? <p className="stocks-warehouse-error">{error}</p> : null}
    </div>
  );
}
