// A chart's title states its finding ("En değerli %20, değerin %58'ini
// getiriyor"); the subtitle says what is plotted. Following Wilke ch. 22:
// the title is the point, the caption is the method.
export default function ChartCard({ title, subtitle, children, footnote, actions }) {
  return (
    <section className="chart-card">
      <header className="chart-card-head">
        <div>
          <h3 className="chart-card-title">{title}</h3>
          {subtitle && <p className="chart-card-subtitle">{subtitle}</p>}
        </div>
        {actions && <div className="chart-card-actions">{actions}</div>}
      </header>
      <div className="chart-card-body">{children}</div>
      {footnote && <p className="chart-card-footnote">{footnote}</p>}
    </section>
  );
}
