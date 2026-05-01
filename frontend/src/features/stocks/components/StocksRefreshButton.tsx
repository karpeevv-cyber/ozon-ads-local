"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { getApiBaseUrl } from "@/shared/api/client";

export function StocksRefreshButton() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [isPending, setIsPending] = useState(false);

  async function refresh() {
    if (isPending) {
      return;
    }
    setIsPending(true);
    const params = new URLSearchParams();
    const company = searchParams.get("company");
    const regionalOrderMin = searchParams.get("stocks_regional_order_min");
    const regionalOrderTarget = searchParams.get("stocks_regional_order_target");
    const positionFilter = searchParams.get("stocks_position_filter");
    if (company) {
      params.set("company", company);
    }
    if (regionalOrderMin) {
      params.set("regional_order_min", regionalOrderMin);
    }
    if (regionalOrderTarget) {
      params.set("regional_order_target", regionalOrderTarget);
    }
    if (positionFilter) {
      params.set("position_filter", positionFilter);
    }
    params.set("force_refresh", "1");
    try {
      const response = await fetch(`${getApiBaseUrl()}/stocks/workspace?${params.toString()}`, {
        cache: "no-store",
      });
      if (!response.ok) {
        throw new Error(`Stocks refresh failed: ${response.status} ${response.statusText}`);
      }
    } catch (error) {
      console.error("Stocks refresh failed", error);
    } finally {
      setIsPending(false);
      router.refresh();
    }
  }

  return (
    <button
      className={`main-refresh-button${isPending ? " main-refresh-button-pending" : ""}`}
      type="button"
      disabled={isPending}
      title="Refresh Stocks cache"
      aria-label="Refresh Stocks cache"
      onClick={refresh}
    >
      {"\u21bb"}
    </button>
  );
}
