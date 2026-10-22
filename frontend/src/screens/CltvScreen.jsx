import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getCltv, getCltvEvaluate } from "../api";
import ChartCard from "../charts/ChartCard";
import { C, axisTick, fmt, niceHistogram, tooltipStyle } from "../charts/theme";
import DataTable from "../components/DataTable";
import MetricCard from "../components/MetricCard";
import SegmentFilter, { ALL_VALUE } from "../components/SegmentFilter";

const SEGMENT_ORDER = ["low", "mid", "high", "very high"];

const COLUMNS = [
  { key: "CustomerNo", label: "Müşteri No" },
  { key: "predicted_cltv", label: "Tahmini CLTV (90 gün)" },
  { key: "frequency", label: "Alışveriş sayısı" },
  { key: "monetary", label: "Harcama" },
  { key: "segment", label: "Değer dilimi" },
];

// Cumulative share of predicted value held by the top x% of customers.
function paretoCurve(values) {
  const sorted = [...values].sort((a, b) => b - a);
  const total = sorted.reduce((s, v) => s + v, 0) || 1;
  const n = sorted.length;
  const out = [{ customers: 0, value: 0 }];
  let acc = 0;
  const step = Math.max(1, Math.floor(n / 100));
  for (let i = 0; i < n; i++) {
    acc += sorted[i];
    if ((i + 1) % step === 0 || i === n - 1) out.push({ customers: (i + 1) / n, value: acc / total });
  }
  return out;
}

function shareAt(curve, x) {
  const hit = curve.find((p) => p.customers >= x);
  return hit ? hit.value : 1;
}

export default function CltvScreen({ sessionId, approach = "single", onApproachChange }) {
  const [data, setData] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedSegment, setSelectedSegment] = useState(ALL_VALUE);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setSelectedSegment(ALL_VALUE);
    Promise.all([getCltv(sessionId, approach), getCltvEvaluate(sessionId, approach)])
      .then(([cltvRes, metricsRes]) => {
        if (cancelled) return;
        setData(cltvRes);
        setMetrics(metricsRes);
      })
      .catch((err) => !cancelled && setError(err.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [sessionId, approach]);

  const derived = useMemo(() => {
    if (!data) return null;
    const values = data.rows.map((r) => r.predicted_cltv);
    const positive = values.filter((v) => v > 0.5);
    const zeroCount = values.length - positive.length;
    const curve = paretoCurve(values);
    const top20 = shareAt(curve, 0.2);
    const hiCap = positive.length ? [...positive].sort((a, b) => a - b)[Math.floor(positive.length * 0.98)] : 1;
    const { bins: rawBins } = niceHistogram(positive.filter((v) => v <= hiCap), 20, hiCap);
    const bins = rawBins.map((b) => ({ ...b, label: `${fmt.money(b.from)}–${fmt.money(b.to)}` }));
    const clipped = positive.filter((v) => v > hiCap).length;
    const total = values.reduce((s, v) => s + v, 0);
    return { curve, top20, bins, zeroCount, clipped, total, n: values.length };
  }, [data]);

  const segmentCounts = useMemo(() => {
    if (!data) return {};
    const counts = {};
    for (const row of data.rows) counts[row.segment] = (counts[row.segment] ?? 0) + 1;
    return counts;
  }, [data]);

  const filteredRows = useMemo(() => {
    if (!data) return [];
    const rows = selectedSegment === ALL_VALUE ? data.rows : data.rows.filter((r) => r.segment === selectedSegment);
    return [...rows].sort((a, b) => b.predicted_cltv - a.predicted_cltv);
  }, [data, selectedSegment]);

  return (
    <div>
      <div className="screen-header">
        <h1 className="screen-title">CLTV Tahmini</h1>
        <p className="screen-subtitle">
          Her müşterinin önümüzdeki 90 günde ne kadar harcayacağının XGBoost tahmini. Seçtiğiniz yaklaşım CRM raporuna
          da yansır.
        </p>
      </div>

      <div className="control-row">
        <div className="control-group">
          <span className="control-label">Yaklaşım</span>
          <div className="radio-group">
            <button className={`radio-pill${approach === "single" ? " active" : ""}`} onClick={() => onApproachChange?.("single")}>
              Tek aşamalı
            </button>
            <button className={`radio-pill${approach === "hurdle" ? " active" : ""}`} onClick={() => onApproachChange?.("hurdle")}>
              İki aşamalı (hurdle)
            </button>
          </div>
        </div>
        {data && (
          <SegmentFilter
            label="Değer dilimi"
            options={SEGMENT_ORDER.filter((s) => segmentCounts[s] !== undefined)}
            counts={segmentCounts}
            value={selectedSegment}
            onChange={setSelectedSegment}
          />
        )}
      </div>

      {loading && <div className="loading-state">Model eğitiliyor, bu biraz sürebilir…</div>}
      {error && <div className="error-state">{error}</div>}

      {metrics && derived && !loading && (
        <div className="stat-strip">
          <MetricCard label="Toplam tahmini değer (90 gün)" value={fmt.money(derived.total)} tone="teal" />
          <MetricCard
            label="Tahmin hatası (ortalama mutlak)"
            value={fmt.dec(metrics.mae, 1)}
            note={`Herkese ortalamayı söylemek ${fmt.dec(metrics.baseline_mae, 1)} hata yapardı.`}
          />
          <MetricCard
            label="Basit yaklaşıma göre iyileşme"
            value={fmt.pct(metrics.improvement_over_baseline)}
            tone={metrics.improvement_over_baseline > 0.2 ? "teal" : "amber"}
            note={metrics.improvement_over_baseline > 0.2 ? "Model gerçek bir sinyal yakalıyor." : "Basit tahmine yakın, dikkatli yorumlayın."}
          />
        </div>
      )}

      {derived && !loading && (
        <div className="chart-row">
          <ChartCard
            title={`En değerli %20 müşteri, tahmini değerin ${fmt.pct(derived.top20)} kadarını getiriyor`}
            subtitle="Müşteriler değere göre sıralandığında birikimli pay. Köşegene ne kadar uzaksa değer o kadar az müşteride toplanmış."
          >
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={derived.curve} margin={{ top: 10, right: 20, bottom: 24, left: 4 }}>
                <CartesianGrid stroke={C.grid} />
                <XAxis
                  type="number"
                  dataKey="customers"
                  domain={[0, 1]}
                  ticks={[0, 0.2, 0.4, 0.6, 0.8, 1]}
                  tickFormatter={(v) => fmt.pct(v)}
                  tick={axisTick}
                  stroke={C.axis}
                  label={{ value: "Müşterilerin payı (en değerliden başlayarak)", position: "insideBottom", offset: -14, fill: C.inkFaint, fontSize: 12 }}
                />
                <YAxis
                  type="number"
                  domain={[0, 1]}
                  ticks={[0, 0.25, 0.5, 0.75, 1]}
                  tickFormatter={(v) => fmt.pct(v)}
                  tick={axisTick}
                  stroke={C.axis}
                  width={48}
                />
                <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]} stroke={C.muted} />
                <ReferenceLine x={0.2} stroke={C.axis} />
                <ReferenceDot
                  x={0.2}
                  y={derived.top20}
                  r={5}
                  fill={C.series}
                  stroke="#fff"
                  strokeWidth={2}
                  label={{ value: fmt.pct(derived.top20), position: "right", fill: C.ink, fontSize: 12, fontWeight: 600 }}
                />
                <Tooltip
                  contentStyle={tooltipStyle}
                  formatter={(v) => [fmt.pct(v, 1), "Değerin payı"]}
                  labelFormatter={(v) => `Müşterilerin ilk ${fmt.pct(v)}`}
                />
                <Line type="monotone" dataKey="value" stroke={C.series} strokeWidth={2} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </ChartCard>

          <ChartCard
            title="Tahmini değerin müşterilere dağılımı"
            subtitle={`Tahmini değeri sıfırın üstünde olan müşteriler. ${fmt.int(derived.zeroCount)} müşteri için tahmin sıfır (son 90 günde alışveriş yok).`}
            footnote={derived.clipped ? `En uçtaki ${fmt.int(derived.clipped)} müşteri okunabilirlik için grafiğin dışında bırakıldı; tabloda yer alıyorlar.` : undefined}
          >
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={derived.bins} margin={{ top: 10, right: 12, bottom: 24, left: 4 }} barCategoryGap={2}>
                <CartesianGrid stroke={C.grid} vertical={false} />
                <XAxis
                  dataKey="from"
                  tickFormatter={(v) => fmt.money(v)}
                  tick={axisTick}
                  stroke={C.axis}
                  interval="preserveStartEnd"
                  minTickGap={24}
                  label={{ value: "Tahmini CLTV", position: "insideBottom", offset: -14, fill: C.inkFaint, fontSize: 12 }}
                />
                <YAxis tick={axisTick} stroke={C.axis} width={40} allowDecimals={false} />
                <Tooltip
                  contentStyle={tooltipStyle}
                  cursor={{ fill: C.grid }}
                  formatter={(v) => [fmt.int(v), "Müşteri"]}
                  labelFormatter={(_, p) => (p?.[0] ? p[0].payload.label : "")}
                />
                <Bar dataKey="count" fill={C.series} radius={[4, 4, 0, 0]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        </div>
      )}

      {data && !loading && (
        <DataTable
          key={`${approach}-${selectedSegment}`}
          columns={COLUMNS}
          rows={filteredRows}
          exportFilename={`cltv_tahminleri_${approach}.csv`}
        />
      )}
    </div>
  );
}
