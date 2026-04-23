"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useState, useTransition } from "react";

type StocksControlsProps = {
  regionalOrderMin: number;
  regionalOrderTarget: number;
  positionFilter: string;
  highlightLevels: string[];
};

export function StocksControls({
  regionalOrderMin,
  regionalOrderTarget,
  positionFilter,
  highlightLevels,
}: StocksControlsProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const [draftMin, setDraftMin] = useState(String(regionalOrderMin));
  const [draftTarget, setDraftTarget] = useState(String(regionalOrderTarget));
  const [draftPositionFilter, setDraftPositionFilter] = useState(positionFilter);
  const [draftHighlightLevels, setDraftHighlightLevels] = useState<string[]>(highlightLevels);

  function toggleHighlightLevel(level: string, checked: boolean) {
    setDraftHighlightLevels((prev) => {
      if (checked) {
        return prev.includes(level) ? prev : [...prev, level];
      }
      return prev.filter((item) => item !== level);
    });
  }

  function buildParams() {
    const params = new URLSearchParams(searchParams.toString());
    const nextMin = Math.max(0, Number.parseInt(draftMin || "0", 10) || 0);
    const nextTarget = Math.max(nextMin, Number.parseInt(draftTarget || "0", 10) || 0);
    params.set("stocks_regional_order_min", String(nextMin));
    params.set("stocks_regional_order_target", String(nextTarget));
    params.set("stocks_position_filter", draftPositionFilter);
    if (draftHighlightLevels.length > 0) {
      params.set("stocks_highlight_levels", draftHighlightLevels.join(","));
    } else {
      params.delete("stocks_highlight_levels");
    }
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
      <fieldset className="stocks-highlight-group" disabled={isPending}>
        <legend>Highlight levels</legend>
        <label className="stocks-check">
          <input
            type="checkbox"
            checked={draftHighlightLevels.includes("paid_now")}
            onChange={(event) => toggleHighlightLevel("paid_now", event.target.checked)}
          />
          <span>Paid now</span>
        </label>
        <label className="stocks-check">
          <input
            type="checkbox"
            checked={draftHighlightLevels.includes("paid_30")}
            onChange={(event) => toggleHighlightLevel("paid_30", event.target.checked)}
          />
          <span>Paid in 30d</span>
        </label>
        <label className="stocks-check">
          <input
            type="checkbox"
            checked={draftHighlightLevels.includes("paid_60")}
            onChange={(event) => toggleHighlightLevel("paid_60", event.target.checked)}
          />
          <span>Paid in 60d</span>
        </label>
      </fieldset>
      <div className="stocks-controls-actions">
        <button type="submit" className="stocks-primary-button" disabled={isPending}>
          Apply
        </button>
      </div>
    </form>
  );
}
