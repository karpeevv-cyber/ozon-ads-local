"use client";

import { useEffect } from "react";

function isReloadableDeploymentError(error: Error & { digest?: string }): boolean {
  const message = String(error.message || "").toLowerCase();
  return (
    message.includes("network error") ||
    message.includes("failed to fetch") ||
    message.includes("server action") ||
    message.includes("older or newer deployment")
  );
}

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    if (!isReloadableDeploymentError(error)) {
      return;
    }
    const reloadKey = `ozon_ads_reload_once:${window.location.pathname}${window.location.search}`;
    if (window.sessionStorage.getItem(reloadKey)) {
      return;
    }
    window.sessionStorage.setItem(reloadKey, "1");
    window.location.reload();
  }, [error]);

  function handleRetry() {
    try {
      const reloadKey = `ozon_ads_reload_once:${window.location.pathname}${window.location.search}`;
      window.sessionStorage.removeItem(reloadKey);
    } catch {
      // Ignore storage issues and still retry the route.
    }
    reset();
    window.location.reload();
  }

  return (
    <section className="dashboard-grid section-grid">
      <article className="panel-card panel-card-wide section-card">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Frontend error</p>
            <h3>Вкладка упала при загрузке</h3>
          </div>
          <span className="status-badge">retry</span>
        </div>
        <p className="muted-copy">{error.message || "Unexpected client error"}</p>
        <button className="nav-pill" type="button" onClick={handleRetry}>
          Try again
        </button>
      </article>
    </section>
  );
}
