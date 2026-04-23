"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useState, useTransition } from "react";

type StocksControlsProps = {
  regionalOrderMin: number;
  regionalOrderTarget: number;
  positionFilter: string;
  highlightMode: string;
};

export function StocksControls({
  regionalOrderMin,
  regionalOrderTarget,
  positionFilter,
  highlightMode,
}: StocksControlsProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const [draftMin, setDraftMin] = useState(String(regionalOrderMin));
  const [draftTarget, setDraftTarget] = useState(String(regionalOrderTarget));
  const [draftPositionFilter, setDraftPositionFilter] = useState(positionFilter);
  const [draftHighlightMode, setDraftHighlightMode] = useState(highlightMode);

  function buildParams() {
    const params = new URLSearchParams(searchParams.toString());
    const nextMin = Math.max(0, Number.parseInt(draftMin || "0", 10) || 0);
    const nextTarget = Math.max(nextMin, Number.parseInt(draftTarget || "0", 10) || 0);
    params.set("stocks_regional_order_min", String(nextMin));
    params.set("stocks_regional_order_target", String(nextTarget));
    params.set("stocks_position_filter", draftPositionFilter);
    params.set("stocks_highlight_mode", draftHighlightMode);
    params.set("tab", "stocks");
    return params;
  }

  function handleApply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const params = buildParams();
    startTransition(() => {
      router.push(`/?${params.toString()}`);
    });
  }

  return (
    <form className="stocks-controls" onSubmit={handleApply}>
      <label>
        <span>Position filter</span>
        <select
          value={draftPositionFilter}
          onChange={(event) => setDraftPositionFilter(event.target.value)}
          disabled={isPending}
        >
          <option value="ALL">All</option>
          <option value="CORE">Core</option>
          <option value="ADDITIONAL">Additional</option>
        </select>
      </label>
      <label>
        <span>Regional min</span>
        <input
          type="number"
          min="0"
          step="1"
          value={draftMin}
          onChange={(event) => setDraftMin(event.target.value)}
          disabled={isPending}
        />
      </label>
      <label>
        <span>Regional target</span>
        <input
          type="number"
          min="0"
          step="1"
          value={draftTarget}
          onChange={(event) => setDraftTarget(event.target.value)}
          disabled={isPending}
        />
      </label>
      <label>
        <span>Highlight mode</span>
        <select
          value={draftHighlightMode}
          onChange={(event) => setDraftHighlightMode(event.target.value)}
          disabled={isPending}
        >
          <option value="none">None</option>
          <option value="candidates">Candidates for order</option>
          <option value="paid_now">Paid storage now</option>
          <option value="paid_30">Paid storage in 30 days</option>
          <option value="paid_60">Paid storage in 60 days</option>
        </select>
      </label>
      <div className="stocks-controls-actions">
        <button type="submit" className="stocks-primary-button" disabled={isPending}>
          Apply
        </button>
      </div>
    </form>
  );
}
