// Chart tokens — one place for every color a chart is allowed to use.
//
// Roles, not hues (see dataviz method):
//   series      single-series marks (bars, lines, histograms) — brand indigo
//   accentUp /  polarity on the slopegraph: rising vs falling pairings
//   accentDown
//   muted       de-emphasis gray for "context" marks (emphasis technique)
//   status      ordered good → critical; only for churn-risk bands, always
//               shipped with a text label, never color alone
//
// Validated with scripts/validate_palette.js (--pairs all, light, #fff):
//   #4f46e5 vs #d03b3b — CVD ΔE 27.5, normal-vision ΔE 34.4, both >= 3:1.
//   The muted gray is intentionally low-chroma; every chart that uses it
//   also has a table view, which is the required relief for its contrast.

export const C = {
  series: "#4f46e5",
  seriesSoft: "#a5b4fc",
  accentUp: "#4f46e5",
  accentDown: "#d03b3b",
  muted: "#c4c8d8",
  mutedInk: "#8a8fab",
  grid: "#eceef5",
  axis: "#d5d8e4",
  ink: "#111827",
  inkSoft: "#4b5563",
  inkFaint: "#6b7280",
  surface: "#ffffff",
};

export const STATUS = {
  "düşük risk": "#0ca30c",
  "orta risk": "#fab219",
  "yüksek risk": "#ec835a",
  "çok yüksek risk": "#d03b3b",
};

export const RISK_ORDER = ["düşük risk", "orta risk", "yüksek risk", "çok yüksek risk"];

// Continuous sequential ramp (one hue, light → dark) for heatmaps.
const RAMP_LO = [238, 242, 255]; // #eef2ff
const RAMP_HI = [49, 46, 129]; // #312e81

export function rampColor(t) {
  const x = Math.max(0, Math.min(1, t));
  const c = RAMP_LO.map((lo, i) => Math.round(lo + (RAMP_HI[i] - lo) * x));
  return `rgb(${c[0]}, ${c[1]}, ${c[2]})`;
}

// Text on a ramp cell: dark ink on the light half, white on the dark half.
export function rampTextColor(t) {
  return t > 0.5 ? "#ffffff" : C.ink;
}

export const axisTick = { fill: C.inkFaint, fontSize: 11 };

export const tooltipStyle = {
  background: C.surface,
  border: `1px solid ${C.axis}`,
  borderRadius: 8,
  color: C.ink,
  fontSize: 12,
  boxShadow: "0 4px 14px rgba(17, 24, 39, 0.08)",
};

export const fmt = {
  int: (v) => Math.round(v).toLocaleString("tr-TR"),
  money: (v) => Math.round(v).toLocaleString("tr-TR"),
  pct: (v, digits = 0) => `%${(v * 100).toLocaleString("tr-TR", { maximumFractionDigits: digits, minimumFractionDigits: digits })}`,
  dec: (v, digits = 2) => v.toLocaleString("tr-TR", { maximumFractionDigits: digits, minimumFractionDigits: digits }),
};

// Equal-width histogram bins for a numeric array.
export function histogram(values, binCount = 20, { min, max } = {}) {
  const finite = values.filter((v) => Number.isFinite(v));
  if (finite.length === 0) return [];
  const lo = min ?? Math.min(...finite);
  const hi = max ?? Math.max(...finite);
  const width = (hi - lo) / binCount || 1;
  const bins = Array.from({ length: binCount }, (_, i) => ({
    from: lo + i * width,
    to: lo + (i + 1) * width,
    count: 0,
  }));
  for (const v of finite) {
    const idx = Math.min(binCount - 1, Math.max(0, Math.floor((v - lo) / width)));
    bins[idx].count += 1;
  }
  return bins;
}

// Sentence-case a label at the start of a title, Turkish-aware (i → İ).
export const cap = (s) => (s ? s.charAt(0).toLocaleUpperCase("tr-TR") + s.slice(1) : s);

// A "nice" step (1, 2, 2.5, 5 × 10^n) so bin edges and ticks land on round
// numbers instead of 147, 293, …
export function niceStep(range, targetCount) {
  const raw = range / Math.max(1, targetCount);
  const mag = 10 ** Math.floor(Math.log10(raw || 1));
  const norm = raw / mag;
  const nice = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10;
  return nice * mag;
}

export function niceHistogram(values, targetBins = 20, maxValue) {
  const finite = values.filter((v) => Number.isFinite(v));
  if (!finite.length) return { bins: [], step: 1 };
  const hi = maxValue ?? Math.max(...finite);
  const step = niceStep(hi, targetBins);
  const count = Math.max(1, Math.ceil(hi / step));
  return { bins: histogram(finite, count, { min: 0, max: count * step }), step };
}

export function niceTicks(max, targetCount = 5) {
  const step = niceStep(max, targetCount);
  const out = [];
  const top = Math.ceil(max / step - 1e-9) * step;
  for (let v = 0; v <= top + step * 0.001; v += step) out.push(Math.round(v * 1000) / 1000);
  return out;
}
