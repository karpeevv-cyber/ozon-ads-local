export default function Loading() {
  return (
    <section className="dashboard-grid section-grid">
      <article className="panel-card panel-card-wide section-card skeleton-card">
        <div className="skeleton-line skeleton-line-lg" />
        <div className="skeleton-line" />
        <div className="skeleton-line" />
      </article>
      <article className="panel-card panel-card-wide section-card skeleton-card">
        <div className="skeleton-line skeleton-line-lg" />
        <div className="skeleton-grid">
          {Array.from({ length: 8 }).map((_, idx) => (
            <span className="skeleton-cell" key={idx} />
          ))}
        </div>
      </article>
    </section>
  );
}
