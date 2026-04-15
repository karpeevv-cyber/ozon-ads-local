"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
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
        <button className="nav-pill" type="button" onClick={reset}>
          Try again
        </button>
      </article>
    </section>
  );
}
