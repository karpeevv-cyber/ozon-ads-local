"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useTransition } from "react";

export function StocksRefreshButton() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();

  function refresh() {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", "stocks");
    params.set("stocks_refresh", String(Date.now()));
    startTransition(() => {
      router.push(`/?${params.toString()}`);
    });
  }

  return (
    <button
      className={`main-refresh-button${isPending ? " main-refresh-button-pending" : ""}`}
      type="button"
      title="Refresh Stocks cache"
      aria-label="Refresh Stocks cache"
      onClick={refresh}
    >
      {"\u21bb"}
    </button>
  );
}
