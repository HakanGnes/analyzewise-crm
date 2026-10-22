import { rampColor, rampTextColor } from "./theme";

// Heatmap for amounts across two sets of categories (Wilke ch. 6.3): one
// continuous hue, every cell labeled with its value so color is never the
// only carrier.
//
// normalize="column" scales each column on its own range — needed when
// columns are different units (days vs. counts vs. money); the label still
// shows the raw value. higherIsBetter lets a column flip so "darker"
// consistently means "better customer" (low recency is good).
export default function Heatmap({ rows, columns, normalize = "all", rowHeader = "" }) {
  const ranges = {};
  if (normalize === "column") {
    for (const col of columns) {
      const vals = rows.map((r) => r.values[col.key]).filter(Number.isFinite);
      ranges[col.key] = [Math.min(...vals), Math.max(...vals)];
    }
  } else {
    const all = rows.flatMap((r) => columns.map((c) => r.values[c.key])).filter(Number.isFinite);
    const range = [Math.min(...all), Math.max(...all)];
    for (const col of columns) ranges[col.key] = range;
  }

  return (
    <div className="heatmap-wrap">
      <table className="heatmap">
        <thead>
          <tr>
            <th scope="col">{rowHeader}</th>
            {columns.map((c) => (
              <th key={c.key} scope="col">
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key}>
              <th scope="row">{r.label}</th>
              {columns.map((c) => {
                const v = r.values[c.key];
                const [lo, hi] = ranges[c.key];
                let t = hi > lo ? (v - lo) / (hi - lo) : 0.5;
                if (c.higherIsBetter === false) t = 1 - t;
                return (
                  <td
                    key={c.key}
                    style={{ background: rampColor(0.08 + t * 0.84), color: rampTextColor(0.08 + t * 0.84) }}
                    title={`${r.label} · ${c.label}: ${c.format ? c.format(v) : v}`}
                  >
                    {Number.isFinite(v) ? (c.format ? c.format(v) : v) : "—"}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
