"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useTransition } from "react";

export function MainRefreshButton() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();

  function refresh() {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", "main");
    params.set("main_refresh", String(Date.now()));
    startTransition(() => {
      router.push(`/?${params.toString()}`);
    });
  }

  return (
    <button
      className={`main-refresh-button${isPending ? " main-refresh-button-pending" : ""}`}
      type="button"
      title="Refresh Main cache"
      aria-label="Refresh Main cache"
      onClick={refresh}
    >
      ↻
    </button>
  );
}
