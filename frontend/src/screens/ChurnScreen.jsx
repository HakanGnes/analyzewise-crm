import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getChurn, getChurnEvaluate, getValueRisk } from "../api";
import ChartCard from "../charts/ChartCard";
import ShareBar from "../charts/ShareBar";
import { C, RISK_ORDER, STATUS, axisTick, fmt, histogram, tooltipStyle } from "../charts/theme";
import DataTable from "../components/DataTable";
import MetricCard from "../components/MetricCard";
import SegmentFilter, { ALL_VALUE } from "../components/SegmentFilter";

const COLUMNS = [
  { key: "CustomerNo", label: "Müşteri No" },
  { key: "churn_probability", label: "Churn olasılığı" },
  { key: "recency", label: "Son alışverişten gün" },
  { key: "frequency", label: "Alışveriş sayısı" },
  { key: "risk_segment", label: "Risk grubu" },
];

const PRIORITY_COLUMNS = [
  { key: "CustomerNo", label: "Müşteri No" },
  { key: "historical_spend", label: "Geçmiş toplam harcama" },
  { key: "churn_probability", label: "Churn olasılığı" },
  { key: "recency", label: "Son alışverişten gün" },
  { key: "frequency", label: "Alışveriş sayısı" },
];

function aucTone(auc) {
  if (auc >= 0.7) return "teal";
  if (auc >= 0.6) return "amber";
  return "rose";
}

function ValueRiskTip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div style={{ ...tooltipStyle, padding: "8px 10px" }}>
      <strong>Müşteri {p.CustomerNo}</strong>
      <div>{p.quadrant}</div>
      <div>
        Churn {fmt.pct(p.churn_probability)}, geçmiş harcama {fmt.money(p.historical_spend)}
      </div>
    </div>
  );
}

export default function ChurnScreen({ sessionId, approach = "single" }) {
  const [data, setData] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [valueRisk, setValueRisk] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedRisk, setSelectedRisk] = useState(ALL_VALUE);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([getChurn(sessionId), getChurnEvaluate(sessionId)])
      .then(([churnRes, metricsRes]) => {
        if (cancelled) return;
        setData(churnRes);
        setMetrics(metricsRes);
      })
      .catch((err) => !cancelled && setError(err.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  useEffect(() => {
    let cancelled = false;
    getValueRisk(sessionId, approach)
      .then((res) => !cancelled && setValueRisk(res))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [sessionId, approach]);

  const derived = useMemo(() => {
    if (!data) return null;
    const parts = RISK_ORDER.map((risk) => ({
      key: risk,
      label: risk.charAt(0).toUpperCase() + risk.slice(1),
      value: data.risk_counts[risk] ?? 0,
      color: STATUS[risk],
    }));
    const total = parts.reduce((s, p) => s + p.value, 0) || 1;
    const atRisk = (data.risk_counts["yüksek risk"] ?? 0) + (data.risk_counts["çok yüksek risk"] ?? 0);
    const bins = histogram(
      data.rows.map((r) => r.churn_probability),
      20,
      { min: 0, max: 1 }
    ).map((b) => ({ ...b, mid: (b.from + b.to) / 2 }));
    return { parts, total, atRisk, bins };
  }, [data]);

  const scatter = useMemo(() => {
    if (!valueRisk) return null;
    const rows = valueRisk.rows.filter((r) => r.historical_spend > 0);
    return {
      priority: rows.filter((r) => r.quadrant === "değerli, riskte"),
      safe: rows.filter((r) => r.quadrant === "değerli, güvende"),
      rest: rows.filter((r) => !r.quadrant.startsWith("değerli")),
    };
  }, [valueRisk]);

  const filteredRows = useMemo(() => {
    if (!data) return [];
    const rows = selectedRisk === ALL_VALUE ? data.rows : data.rows.filter((r) => r.risk_segment === selectedRisk);
    return [...rows].sort((a, b) => b.churn_probability - a.churn_probability);
  }, [data, selectedRisk]);

  const toggleRisk = (risk) => setSelectedRisk((cur) => (cur === risk ? ALL_VALUE : risk));

  return (
    <div>
      <div className="screen-header">
        <h1 className="screen-title">Churn Tahmini</h1>
        <p className="screen-subtitle">
          Her müşterinin önümüzdeki 90 günde geri gelmeme olasılığı. Asıl soru en altta: geçmişte çok harcamış ama
          gitmek üzere olan kim?
        </p>
      </div>

      {data && (
        <div className="control-row">
          <SegmentFilter
            label="Risk grubu"
            options={RISK_ORDER.filter((r) => data.risk_counts[r] !== undefined)}
            counts={data.risk_counts}
            value={selectedRisk}
            onChange={setSelectedRisk}
          />
        </div>
      )}

      {loading && <div className="loading-state">Model eğitiliyor, bu biraz sürebilir…</div>}
      {error && <div className="error-state">{error}</div>}

      {metrics && derived && !loading && (
        <div className="stat-strip">
          <MetricCard
            label="Yüksek ve çok yüksek riskte"
            value={`${fmt.int(derived.atRisk)} müşteri`}
            tone="rose"
            note={`Tüm müşterilerin ${fmt.pct(derived.atRisk / derived.total)} kadarı.`}
          />
          <MetricCard
            label="Model ayırt etme gücü (ROC AUC)"
            value={fmt.dec(metrics.roc_auc, 2)}
            tone={aucTone(metrics.roc_auc)}
            note="0,50 rastgele tahmin, 1,00 kusursuz ayrım demek."
          />
          <MetricCard
            label="Geçmiş dönemlerde churn oranı"
            value={fmt.pct(metrics.positive_rate)}
            note="Modelin eğitildiği dönemlerde geri gelmeyen müşteri payı."
          />
        </div>
      )}

      {derived && !loading && (
        <div className="chart-row">
          <ChartCard
            title={`Müşterilerin ${fmt.pct(derived.atRisk / derived.total)} kadarı yüksek veya çok yüksek riskte`}
            subtitle="Risk gruplarına göre müşteri payı, düşükten yükseğe. Bir gruba tıklayınca tablo o gruba süzülür."
          >
            <ShareBar parts={derived.parts} selected={selectedRisk === ALL_VALUE ? null : selectedRisk} onSelect={toggleRisk} />
          </ChartCard>

          <ChartCard
            title="Churn olasılıklarının dağılımı"
            subtitle="Her çubuk %5 genişliğinde bir olasılık aralığındaki müşteri sayısı. Sağa yığılma, kaybedilme riski taşıyan geniş bir kitle demek."
            footnote="%100'deki çubuk, son 90 günde hiç alışveriş yapmamış müşterilerdir: tanım gereği churn sayılırlar, model onlar için ayrıca tahmin yapmaz."
          >
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={derived.bins} margin={{ top: 6, right: 12, bottom: 22, left: 4 }} barCategoryGap={2}>
                <CartesianGrid stroke={C.grid} vertical={false} />
                <XAxis
                  dataKey="mid"
                  type="number"
                  domain={[0, 1]}
                  ticks={[0, 0.25, 0.5, 0.75, 1]}
                  tickFormatter={(v) => fmt.pct(v)}
                  tick={axisTick}
                  stroke={C.axis}
                  label={{ value: "Churn olasılığı", position: "insideBottom", offset: -12, fill: C.inkFaint, fontSize: 12 }}
                />
                <YAxis tick={axisTick} stroke={C.axis} width={40} allowDecimals={false} />
                <Tooltip
                  contentStyle={tooltipStyle}
                  cursor={{ fill: C.grid }}
                  formatter={(v) => [fmt.int(v), "Müşteri"]}
                  labelFormatter={(_, p) => (p?.[0] ? `${fmt.pct(p[0].payload.from)}–${fmt.pct(p[0].payload.to)}` : "")}
                />
                <Bar dataKey="count" fill={C.series} radius={[4, 4, 0, 0]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        </div>
      )}

      {valueRisk && scatter && !loading && (
        <ChartCard
          title={
            valueRisk.priority_count
              ? `${fmt.int(valueRisk.priority_count)} değerli müşteri gitmek üzere; geçmişte toplam ${fmt.money(valueRisk.priority_total_value)} harcamışlar`
              : "Şu an gitmek üzere olan değerli müşteri yok"
          }
          subtitle={`Yatay eksen churn olasılığı, dikey eksen geçmiş toplam harcama (logaritmik). Kırmızı köşe: harcaması en üst %25'te ve churn olasılığı %${Math.round(valueRisk.thresholds.risk * 100)} ve üzeri.`}
          footnote="Değer ekseni bilerek geçmiş harcamadır, tahmini CLTV değil: CLTV tahmini gitme ihtimalini zaten içerdiği için riskli müşterilerin tahmini değeri hep düşük çıkar ve bu köşe boş kalırdı."
        >
          <ResponsiveContainer width="100%" height={360}>
            <ScatterChart margin={{ top: 10, right: 20, bottom: 28, left: 8 }}>
              <CartesianGrid stroke={C.grid} />
              <XAxis
                type="number"
                dataKey="churn_probability"
                domain={[0, 1]}
                ticks={[0, 0.25, 0.5, 0.75, 1]}
                tickFormatter={(v) => fmt.pct(v)}
                tick={axisTick}
                stroke={C.axis}
                label={{ value: "Churn olasılığı", position: "insideBottom", offset: -16, fill: C.inkFaint, fontSize: 12 }}
              />
              <YAxis
                type="number"
                dataKey="historical_spend"
                scale="log"
                domain={["auto", "auto"]}
                tickFormatter={(v) => fmt.money(v)}
                tick={axisTick}
                stroke={C.axis}
                width={64}
              />
              <ReferenceLine x={valueRisk.thresholds.risk} stroke={C.axis} />
              <ReferenceLine y={valueRisk.thresholds.value} stroke={C.axis} />
              <Tooltip content={<ValueRiskTip />} cursor={{ stroke: C.axis }} />
              <Scatter data={scatter.rest} fill={C.muted} fillOpacity={0.5} isAnimationActive={false} />
              <Scatter data={scatter.safe} fill={C.series} fillOpacity={0.7} isAnimationActive={false} />
              <Scatter data={scatter.priority} fill={C.accentDown} fillOpacity={0.95} isAnimationActive={false} />
            </ScatterChart>
          </ResponsiveContainer>
          <div className="chart-legend-inline">
            <span>
              <i style={{ background: C.accentDown }} /> Değerli, riskte ({fmt.int(scatter.priority.length)})
            </span>
            <span>
              <i style={{ background: C.series }} /> Değerli, güvende ({fmt.int(scatter.safe.length)})
            </span>
            <span>
              <i style={{ background: C.muted }} /> Diğer müşteriler ({fmt.int(scatter.rest.length)})
            </span>
          </div>
        </ChartCard>
      )}

      {valueRisk?.priority?.length > 0 && !loading && (
        <ChartCard
          title="Öncelikli geri kazanım listesi"
          subtitle="Kırmızı köşedeki müşteriler, geçmiş harcamaya göre sıralı. CSV olarak indirip kampanyanıza bağlayabilirsiniz."
        >
          <DataTable columns={PRIORITY_COLUMNS} rows={valueRisk.priority} pageSize={10} exportFilename="geri_kazanim_listesi.csv" />
        </ChartCard>
      )}

      {data && !loading && (
        <DataTable key={selectedRisk} columns={COLUMNS} rows={filteredRows} exportFilename="churn_tahminleri.csv" />
      )}
    </div>
  );
}
