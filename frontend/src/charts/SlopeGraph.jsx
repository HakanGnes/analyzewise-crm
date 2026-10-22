import { useState } from "react";
import { C, fmt } from "./theme";

// Slopegraph for paired data (Wilke ch. 12.4): the same few products
// measured in two periods, joined by a line whose slope is the change.
// Wilke recommends it exactly for "a small number of observations" where
// "the identity of each individual case" matters — so this is capped at a
// handful of products and every line is labeled at both ends.
//
// Polarity encoding: rising lines in indigo, falling in red, changes under
// `threshold` (percentage points) recede to gray, so the eye lands on the
// pairings that actually moved.

const W = 680;
const COL_L = 250;
const COL_R = 430;
const TOP = 46;
const LABEL_GAP = 17;

function placeLabels(items, key, plotTop, plotBottom) {
  // Push overlapping labels apart while keeping their order, then clamp.
  const sorted = items.map((it, i) => ({ i, y: it[key] })).sort((a, b) => a.y - b.y);
  for (let k = 1; k < sorted.length; k++) {
    if (sorted[k].y - sorted[k - 1].y < LABEL_GAP) sorted[k].y = sorted[k - 1].y + LABEL_GAP;
  }
  const overflow = sorted.length ? sorted[sorted.length - 1].y - plotBottom : 0;
  if (overflow > 0) sorted.forEach((s) => (s.y -= overflow));
  for (let k = sorted.length - 2; k >= 0; k--) {
    if (sorted[k + 1].y - sorted[k].y < LABEL_GAP) sorted[k].y = sorted[k + 1].y - LABEL_GAP;
  }
  if (sorted.length && sorted[0].y < plotTop) {
    const shift = plotTop - sorted[0].y;
    sorted.forEach((s) => (s.y += shift));
  }
  const out = new Array(items.length);
  sorted.forEach((s) => (out[s.i] = s.y));
  return out;
}

export default function SlopeGraph({ items, periods, threshold = 0.03, leftTitle, rightTitle }) {
  const [hovered, setHovered] = useState(null);
  const plotH = Math.max(220, items.length * 30);
  const H = TOP + plotH + 24;
  const max = Math.max(...items.flatMap((d) => [d.first, d.second]), 0.01) * 1.08;
  const y = (v) => TOP + plotH - (v / max) * plotH;

  const points = items.map((d) => ({ ...d, y1: y(d.first), y2: y(d.second), delta: d.second - d.first }));
  const leftY = placeLabels(points, "y1", TOP, TOP + plotH);
  const rightY = placeLabels(points, "y2", TOP, TOP + plotH);

  const colorFor = (delta) => (delta >= threshold ? C.accentUp : delta <= -threshold ? C.accentDown : C.muted);
  const inkFor = (delta) => (Math.abs(delta) >= threshold ? C.ink : C.inkFaint);

  return (
    <div className="slopegraph">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Birlikte alınma oranının iki dönem arasındaki değişimi">
        <text x={COL_L} y={18} textAnchor="middle" className="slope-head">
          {leftTitle}
        </text>
        <text x={COL_L} y={33} textAnchor="middle" className="slope-sub">
          {periods?.[0]}
        </text>
        <text x={COL_R} y={18} textAnchor="middle" className="slope-head">
          {rightTitle}
        </text>
        <text x={COL_R} y={33} textAnchor="middle" className="slope-sub">
          {periods?.[1]}
        </text>
        <line x1={COL_L} x2={COL_L} y1={TOP - 4} y2={TOP + plotH + 4} stroke={C.grid} strokeWidth="1" />
        <line x1={COL_R} x2={COL_R} y1={TOP - 4} y2={TOP + plotH + 4} stroke={C.grid} strokeWidth="1" />

        {points.map((p, i) => {
          const color = colorFor(p.delta);
          const isDim = hovered !== null && hovered !== i;
          return (
            <g
              key={p.product_id}
              opacity={isDim ? 0.25 : 1}
              onMouseEnter={() => setHovered(i)}
              onMouseLeave={() => setHovered(null)}
              className="slope-item"
            >
              <title>{`${p.name}: ${fmt.pct(p.first, 1)} → ${fmt.pct(p.second, 1)}`}</title>
              <line x1={COL_L} y1={p.y1} x2={COL_R} y2={p.y2} stroke="transparent" strokeWidth="14" />
              <line x1={COL_L} y1={p.y1} x2={COL_R} y2={p.y2} stroke={color} strokeWidth={hovered === i ? 3 : 2} strokeLinecap="round" />
              <circle cx={COL_L} cy={p.y1} r={4.5} fill={color} stroke={C.surface} strokeWidth="2" />
              <circle cx={COL_R} cy={p.y2} r={4.5} fill={color} stroke={C.surface} strokeWidth="2" />
              <text x={COL_L - 12} y={leftY[i] + 4} textAnchor="end" className="slope-label" fill={inkFor(p.delta)}>
                {p.name}
                <tspan className="slope-value" dx="8">
                  {fmt.pct(p.first)}
                </tspan>
              </text>
              <text x={COL_R + 12} y={rightY[i] + 4} textAnchor="start" className="slope-label" fill={inkFor(p.delta)}>
                <tspan className="slope-value">{fmt.pct(p.second)}</tspan>
                <tspan dx="8">{p.name}</tspan>
              </text>
            </g>
          );
        })}
      </svg>
      <ul className="slope-legend">
        <li>
          <span style={{ background: C.accentUp }} aria-hidden="true" /> Yükselen ({`≥ ${Math.round(threshold * 100)} puan`})
        </li>
        <li>
          <span style={{ background: C.accentDown }} aria-hidden="true" /> Düşen
        </li>
        <li>
          <span style={{ background: C.muted }} aria-hidden="true" /> Belirgin değişim yok
        </li>
      </ul>
    </div>
  );
}
