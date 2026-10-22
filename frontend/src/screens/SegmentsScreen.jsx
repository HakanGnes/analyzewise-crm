import { useEffect, useMemo, useState } from "react";
import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";
import { getSegments } from "../api";
import BarList from "../charts/BarList";
import ChartCard from "../charts/ChartCard";
import Heatmap from "../charts/Heatmap";
import { C, axisTick, cap, fmt, niceTicks, tooltipStyle } from "../charts/theme";
import DataTable from "../components/DataTable";
import SegmentFilter, { ALL_VALUE } from "../components/SegmentFilter";

const COLUMNS = [
  { key: "CustomerNo", label: "Müşteri No" },
  { key: "recency", label: "Son alışverişten gün" },
  { key: "frequency", label: "Alışveriş sayısı" },
  { key: "monetary", label: "Toplam harcama" },
  { key: "segment", label: "Segment" },
];

function ScatterTip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div style={{ ...tooltipStyle, padding: "8px 10px" }}>
      <strong>Müşteri {p.CustomerNo}</strong>
      <div>{p.segment}</div>
      <div>
        {fmt.int(p.recency)} gün önce, {fmt.int(p.frequency)} alışveriş, {fmt.money(p.monetary)} harcama
      </div>
    </div>
  );
}

export default function SegmentsScreen({ sessionId, settings, onSettingsChange }) {
  const auto = settings?.auto ?? false;
  const k = settings?.k ?? 6;
  const setAuto = (v) => onSettingsChange?.({ ...settings, auto: v });
  const setK = (v) => onSettingsChange?.({ ...settings, k: v });

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(ALL_VALUE);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setSelected(ALL_VALUE);
    getSegments(sessionId, { k, auto })
      .then((res) => !cancelled && setData(res))
      .catch((err) => !cancelled && setError(err.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [sessionId, k, auto]);

  const derived = useMemo(() => {
    if (!data) return null;
    const total = data.rows.length;
    const sizes = Object.entries(data.segment_counts)
      .map(([segment, count]) => ({ key: segment, label: segment, value: count }))
      .sort((a, b) => b.value - a.value);
    const means = [...data.segment_means].sort((a, b) => b.monetary - a.monetary);
    const top = means[0];
    const counts = data.segment_counts;
    const heatRows = means.map((m) => ({
      key: m.segment,
      label: m.segment,
      values: { size: counts[m.segment], recency: m.recency, frequency: m.frequency, monetary: m.monetary },
    }));
    return { total, sizes, top, heatRows };
  }, [data]);

  const filteredRows = useMemo(() => {
    if (!data) return [];
    return selected === ALL_VALUE ? data.rows : data.rows.filter((r) => r.segment === selected);
  }, [data, selected]);

  const scatter = useMemo(() => {
    if (!data) return { focus: [], context: [] };
    const rows = data.rows.filter((r) => r.monetary > 0);
    if (selected === ALL_VALUE) return { focus: rows, context: [] };
    return { focus: rows.filter((r) => r.segment === selected), context: rows.filter((r) => r.segment !== selected) };
  }, [data, selected]);

  const recencyTicks = useMemo(
    () => niceTicks(data ? Math.max(...data.rows.map((r) => r.recency), 1) : 1, 6),
    [data]
  );

  const toggle = (seg) => setSelected((cur) => (cur === seg ? ALL_VALUE : seg));

  return (
    <div>
      <div className="screen-header">
        <h1 className="screen-title">Müşteri Segmentasyonu</h1>
        <p className="screen-subtitle">
          K-Means, müşterileri son alışveriş zamanı, alışveriş sayısı ve toplam harcamaya göre gruplar. Bir segmente
          tıklayarak bütün ekranı o gruba odaklayın.
        </p>
      </div>

      <div className="control-row">
        <div className="control-group">
          <span className="control-label">Segment sayısı</span>
          <div className="slider-row">
            <input type="range" min={2} max={10} value={k} disabled={auto} onChange={(e) => setK(Number(e.target.value))} />
            <span style={{ fontVariantNumeric: "tabular-nums" }}>{auto ? "oto" : k}</span>
          </div>
        </div>
        <div className="control-group">
          <span className="control-label">Otomatik (elbow)</span>
          <div className="radio-group">
            <button className={`radio-pill${!auto ? " active" : ""}`} onClick={() => setAuto(false)}>
              Kapalı
            </button>
            <button className={`radio-pill${auto ? " active" : ""}`} onClick={() => setAuto(true)}>
              Açık
            </button>
          </div>
        </div>
        {data && (
          <SegmentFilter
            label="Odaklanılan segment"
            options={derived.sizes.map((s) => s.key)}
            counts={data.segment_counts}
            value={selected}
            onChange={setSelected}
          />
        )}
      </div>

      {loading && <div className="loading-state">Segmentler hesaplanıyor…</div>}
      {error && <div className="error-state">{error}</div>}

      {data && !loading && derived && (
        <>
          <div className="chart-row">
            <ChartCard
              title={`En büyük grup: ${derived.sizes[0].label} (${fmt.pct(derived.sizes[0].value / derived.total)})`}
              subtitle="Segmentlere göre müşteri sayısı. Bir çubuğa tıklayınca diğer grafikler o segmente odaklanır."
            >
              <BarList
                data={derived.sizes}
                valueFormat={(v) => `${fmt.int(v)} · ${fmt.pct(v / derived.total)}`}
                selected={selected === ALL_VALUE ? null : selected}
                onSelect={toggle}
              />
            </ChartCard>

            <ChartCard
              title={`${cap(derived.top.segment)} ortalama ${fmt.money(derived.top.monetary)} harcamayla en değerli grup`}
              subtitle="Her segmentin ortalama profili. Koyu renk, o sütunda daha iyi müşteri demek (son alışverişte daha az gün daha iyidir)."
            >
              <Heatmap
                rowHeader="Segment"
                normalize="column"
                rows={derived.heatRows}
                columns={[
                  { key: "recency", label: "Son alışveriş (gün)", format: fmt.int, higherIsBetter: false },
                  { key: "frequency", label: "Alışveriş sayısı", format: (v) => fmt.dec(v, 1) },
                  { key: "monetary", label: "Harcama", format: fmt.money },
                ]}
              />
            </ChartCard>
          </div>

          <ChartCard
            title={
              selected === ALL_VALUE
                ? "Müşteriler son alışveriş zamanı ve harcamaya göre"
                : `${cap(selected)}: ${fmt.int(scatter.focus.length)} müşteri, diğerleri gri`
            }
            subtitle="Her nokta bir müşteri. Sol üst köşe yakın zamanda alışveriş yapmış ve çok harcamış müşteriler. Harcama ekseni logaritmik."
          >
            <ResponsiveContainer width="100%" height={340}>
              <ScatterChart margin={{ top: 8, right: 16, bottom: 28, left: 8 }}>
                <CartesianGrid stroke={C.grid} />
                <XAxis
                  type="number"
                  dataKey="recency"
                  name="Son alışveriş"
                  domain={[0, recencyTicks[recencyTicks.length - 1]]}
                  ticks={recencyTicks}
                  tick={axisTick}
                  stroke={C.axis}
                  label={{ value: "Son alışverişten bu yana geçen gün", position: "insideBottom", offset: -16, fill: C.inkFaint, fontSize: 12 }}
                />
                <YAxis
                  type="number"
                  dataKey="monetary"
                  name="Harcama"
                  scale="log"
                  domain={["auto", "auto"]}
                  tick={axisTick}
                  stroke={C.axis}
                  tickFormatter={(v) => fmt.money(v)}
                  width={64}
                />
                <Tooltip content={<ScatterTip />} cursor={{ stroke: C.axis }} />
                {scatter.context.length > 0 && (
                  <Scatter data={scatter.context} fill={C.muted} fillOpacity={0.45} isAnimationActive={false} shape="circle" />
                )}
                <Scatter
                  data={scatter.focus}
                  fill={C.series}
                  fillOpacity={selected === ALL_VALUE ? 0.45 : 0.8}
                  isAnimationActive={false}
                  shape="circle"
                />
              </ScatterChart>
            </ResponsiveContainer>
          </ChartCard>

          <DataTable
            key={`${k}-${auto}-${selected}`}
            columns={COLUMNS}
            rows={filteredRows}
            exportFilename="musteri_segmentleri.csv"
          />
        </>
      )}
    </div>
  );
}
