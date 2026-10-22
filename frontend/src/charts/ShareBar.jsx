import { fmt } from "./theme";

// One 100% stacked bar for part-to-whole over a few *ordered* parts (Wilke
// ch. 10: stacked bars suit ordered parts better than a pie when the order
// carries meaning). 2px surface gaps between segments, labels below rather
// than inside so short segments are never clipped.
export default function ShareBar({ parts, selected, onSelect }) {
  const total = parts.reduce((s, p) => s + p.value, 0) || 1;

  return (
    <div className="sharebar">
      <div className="sharebar-track" role="img" aria-label={parts.map((p) => `${p.label} ${fmt.pct(p.value / total)}`).join(", ")}>
        {parts.map((p) =>
          p.value > 0 ? (
            <button
              key={p.key}
              type="button"
              className="sharebar-seg"
              style={{
                flexGrow: p.value,
                background: p.color,
                opacity: selected && selected !== p.key ? 0.3 : 1,
              }}
              title={`${p.label}: ${fmt.int(p.value)} (${fmt.pct(p.value / total)})`}
              onClick={onSelect ? () => onSelect(p.key) : undefined}
            />
          ) : null
        )}
      </div>
      <ul className="sharebar-legend">
        {parts.map((p) => (
          <li key={p.key}>
            <span className="sharebar-swatch" style={{ background: p.color }} aria-hidden="true" />
            <span className="sharebar-legend-label">{p.label}</span>
            <span className="sharebar-legend-value">
              {fmt.int(p.value)} <span className="muted">({fmt.pct(p.value / total)})</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
