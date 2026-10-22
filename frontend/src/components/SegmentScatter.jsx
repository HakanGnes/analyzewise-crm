import { useEffect, useMemo, useState } from "react";

// Illustrative only: a seeded scatter that mirrors what the K-Means screen
// produces (recency on x, spend on y), so the hero shows the product's core
// idea at a glance. Not real customer data.
const W = 520;
const H = 400;
const PAD = { left: 36, right: 16, top: 16, bottom: 36 };

const SEGMENTS = [
  { id: "champ", label: "Şampiyonlar", color: "#4F46E5", cx: 0.16, cy: 0.2, sx: 0.07, sy: 0.08, n: 26, labelPos: [0.04, 0.06] },
  { id: "loyal", label: "Sadık müşteriler", color: "#059669", cx: 0.38, cy: 0.42, sx: 0.08, sy: 0.08, n: 32, labelPos: [0.42, 0.25] },
  { id: "new", label: "Yeni müşteriler", color: "#0891B2", cx: 0.14, cy: 0.8, sx: 0.07, sy: 0.06, n: 26, labelPos: [0.03, 0.97] },
  { id: "risk", label: "Riskte olanlar", color: "#D97706", cx: 0.72, cy: 0.32, sx: 0.08, sy: 0.09, n: 24, labelPos: [0.66, 0.1] },
  { id: "sleep", label: "Kış uykusundakiler", color: "#64748B", cx: 0.8, cy: 0.78, sx: 0.09, sy: 0.07, n: 36, labelPos: [0.58, 0.97] },
];

function mulberry32(seed) {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function gaussian(rand) {
  const u = 1 - rand();
  const v = rand();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

const innerW = W - PAD.left - PAD.right;
const innerH = H - PAD.top - PAD.bottom;
const toX = (f) => PAD.left + f * innerW;
const toY = (f) => PAD.top + f * innerH;

export default function SegmentScatter() {
  const [settled, setSettled] = useState(false);
  const [hovered, setHovered] = useState(null);

  const points = useMemo(() => {
    const rand = mulberry32(42);
    const out = [];
    SEGMENTS.forEach((seg) => {
      for (let i = 0; i < seg.n; i++) {
        const fx = Math.min(0.98, Math.max(0.02, seg.cx + gaussian(rand) * seg.sx));
        const fy = Math.min(0.98, Math.max(0.02, seg.cy + gaussian(rand) * seg.sy));
        out.push({ seg: seg.id, color: seg.color, x: toX(fx), y: toY(fy), r: 3.2 + rand() * 2.6, order: rand() });
      }
    });
    return out;
  }, []);

  useEffect(() => {
    const id = requestAnimationFrame(() => setSettled(true));
    return () => cancelAnimationFrame(id);
  }, []);

  const midX = PAD.left + innerW / 2;
  const midY = PAD.top + innerH / 2;

  return (
    <figure className="lp-scatter" aria-label="Müşterilerin son alışveriş zamanı ve harcamaya göre segmentlere ayrıldığı örnek dağılım grafiği">
      <svg viewBox={`0 0 ${W} ${H}`} role="img">
        <line x1={PAD.left} y1={H - PAD.bottom} x2={W - PAD.right} y2={H - PAD.bottom} className="lp-axis" />
        <line x1={PAD.left} y1={PAD.top} x2={PAD.left} y2={H - PAD.bottom} className="lp-axis" />
        <text x={W - PAD.right} y={H - 12} textAnchor="end" className="lp-axis-label">
          Son alışverişten bu yana geçen süre
        </text>
        <text x={14} y={PAD.top} textAnchor="end" transform={`rotate(-90 14 ${PAD.top})`} className="lp-axis-label">
          Toplam harcama
        </text>

        {points.map((p, i) => {
          const dimmed = hovered && hovered !== p.seg;
          return (
            <circle
              key={i}
              cx={p.x}
              cy={p.y}
              r={p.r}
              fill={p.color}
              className="lp-dot"
              style={{
                opacity: settled ? (dimmed ? 0.15 : 0.85) : 0,
                transform: settled ? "translate(0px, 0px)" : `translate(${midX - p.x}px, ${midY - p.y}px)`,
                transitionDelay: settled && !hovered ? `${Math.round(p.order * 700)}ms` : "0ms",
              }}
            />
          );
        })}

        {SEGMENTS.map((seg) => (
          <g
            key={seg.id}
            className="lp-seg-label"
            onMouseEnter={() => setHovered(seg.id)}
            onMouseLeave={() => setHovered(null)}
            style={{ opacity: settled ? 1 : 0 }}
          >
            <rect
              x={toX(seg.labelPos[0]) - 4}
              y={toY(seg.labelPos[1]) - 15}
              width={seg.label.length * 7.4 + 22}
              height={22}
              rx={11}
              fill="#fff"
              stroke={hovered === seg.id ? seg.color : "#E3E5EF"}
            />
            <circle cx={toX(seg.labelPos[0]) + 7} cy={toY(seg.labelPos[1]) - 4} r={4} fill={seg.color} />
            <text x={toX(seg.labelPos[0]) + 16} y={toY(seg.labelPos[1])} className="lp-seg-text">
              {seg.label}
            </text>
          </g>
        ))}
      </svg>
      <figcaption>Her nokta bir müşteri. K-Means, benzer davranan müşterileri aynı gruba koyar.</figcaption>
    </figure>
  );
}
