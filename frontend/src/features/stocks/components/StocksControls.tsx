"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useState, useTransition } from "react";

type StocksControlsProps = {
  regionalOrderMin: number;
  regionalOrderTarget: number;
  positionFilter: string;
  reviewMode: boolean;
};

export function StocksControls({
  regionalOrderMin,
  regionalOrderTarget,
  positionFilter,
  reviewMode,
}: StocksControlsProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const [draftMin, setDraftMin] = useState(String(regionalOrderMin));
  const [draftTarget, setDraftTarget] = useState(String(regionalOrderTarget));
  const [draftPositionFilter, setDraftPositionFilter] = useState(positionFilter);
  const [draftReviewMode, setDraftReviewMode] = useState(reviewMode);

  function buildParams() {
    const params = new URLSearchParams(searchParams.toString());
    const nextMin = Math.max(0, Number.parseInt(draftMin || "0", 10) || 0);
    const nextTarget = Math.max(nextMin, Number.parseInt(draftTarget || "0", 10) || 0);
    params.set("stocks_regional_order_min", String(nextMin));
    params.set("stocks_regional_order_target", String(nextTarget));
    params.set("stocks_position_filter", draftPositionFilter);
    params.set("stocks_review_mode", draftReviewMode ? "1" : "0");
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

  function handleRefresh() {
    startTransition(() => {
      router.refresh();
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
      <label className="stocks-toggle">
        <span>Highlight candidates</span>
        <input
          type="checkbox"
          checked={draftReviewMode}
          onChange={(event) => setDraftReviewMode(event.target.checked)}
          disabled={isPending}
        />
      </label>
      <div className="stocks-controls-actions">
        <button type="button" className="stocks-secondary-button" onClick={handleRefresh} disabled={isPending}>
          Refresh
        </button>
        <button type="submit" className="stocks-primary-button" disabled={isPending}>
          Apply
        </button>
      </div>
    </form>
  );
}
