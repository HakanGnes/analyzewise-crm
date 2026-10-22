import { C } from "./theme";

// Horizontal bar chart for amounts across a few named categories (Wilke
// ch. 6): one hue, sorted, value at the bar end. Horizontal so long Turkish
// labels never rotate. Optionally clickable to drive a filter, in which
// case the non-selected bars recede to the muted gray (emphasis).
export default function BarList({ data, valueFormat = (v) => v, selected, onSelect, color = C.series }) {
  const max = Math.max(...data.map((d) => d.value), 0) || 1;
  const interactive = Boolean(onSelect);

  return (
    <div className="barlist" role="list">
      {data.map((d) => {
        const dimmed = selected && selected !== d.key;
        const Tag = interactive ? "button" : "div";
        return (
          <Tag
            key={d.key}
            role="listitem"
            className={`barlist-row${interactive ? " is-interactive" : ""}${selected === d.key ? " is-selected" : ""}`}
            onClick={interactive ? () => onSelect(d.key) : undefined}
            title={`${d.label}: ${valueFormat(d.value)}`}
            type={interactive ? "button" : undefined}
          >
            <span className="barlist-label">{d.label}</span>
            <span className="barlist-track">
              <span
                className="barlist-bar"
                style={{ width: `${Math.max(1.5, (d.value / max) * 100)}%`, background: dimmed ? C.muted : d.color ?? color }}
              />
            </span>
            <span className="barlist-value">{valueFormat(d.value)}</span>
          </Tag>
        );
      })}
    </div>
  );
}
