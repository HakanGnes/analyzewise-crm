import { useEffect, useMemo, useState } from "react";
import { getCltv, getCltvEvaluate } from "../api";
import DataTable from "../components/DataTable";
import MetricCard from "../components/MetricCard";
import SegmentFilter, { ALL_VALUE } from "../components/SegmentFilter";

const SEGMENT_ORDER = ["low", "mid", "high", "very high"];

const COLUMNS = [
  { key: "CustomerNo", label: "Müşteri No" },
  { key: "predicted_cltv", label: "Tahmini CLTV" },
  { key: "frequency", label: "Sıklık" },
  { key: "monetary", label: "Toplam Harcama" },
  { key: "segment", label: "Segment" },
];

export default function CltvScreen({ sessionId }) {
  const [approach, setApproach] = useState("single");
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

  const segmentCounts = useMemo(() => {
    if (!data) return {};
    const counts = {};
    for (const row of data.rows) counts[row.segment] = (counts[row.segment] ?? 0) + 1;
    return counts;
  }, [data]);

  const segmentOptions = useMemo(
    () => SEGMENT_ORDER.filter((s) => segmentCounts[s] !== undefined),
    [segmentCounts]
  );

  const filteredRows = useMemo(() => {
    if (!data) return [];
    const rows = selectedSegment === ALL_VALUE ? data.rows : data.rows.filter((r) => r.segment === selectedSegment);
    return [...rows].sort((a, b) => b.predicted_cltv - a.predicted_cltv);
  }, [data, selectedSegment]);

  return (
    <div>
      <div className="screen-header">
        <h1 className="screen-title">CLTV Tahmini</h1>
        <p className="screen-subtitle">XGBoost regresyon ile müşteri yaşam boyu değeri tahmini.</p>
      </div>

      <div className="control-row">
        <div className="control-group">
          <span className="control-label">Yaklaşım</span>
          <div className="radio-group">
            <button className={`radio-pill${approach === "single" ? " active" : ""}`} onClick={() => setApproach("single")}>
              Tek aşamalı
            </button>
            <button className={`radio-pill${approach === "hurdle" ? " active" : ""}`} onClick={() => setApproach("hurdle")}>
              İki aşamalı (hurdle)
            </button>
          </div>
        </div>
        {data && (
          <SegmentFilter
            label="Segment filtrele"
            options={segmentOptions}
            counts={segmentCounts}
            value={selectedSegment}
            onChange={setSelectedSegment}
          />
        )}
      </div>

      {loading && <div className="loading-state">Model eğitiliyor, bu biraz sürebilir…</div>}
      {error && <div className="error-state">{error}</div>}

      {metrics && !loading && (
        <div className="card-grid">
          <MetricCard label="Held-out MAE" value={metrics.mae.toFixed(2)} tone="teal" />
          <MetricCard label="Naive Baseline MAE" value={metrics.baseline_mae.toFixed(2)} />
          <MetricCard
            label="Baseline'a Göre İyileşme"
            value={`%${(metrics.improvement_over_baseline * 100).toFixed(1)}`}
            tone={metrics.improvement_over_baseline > 0.2 ? "teal" : "amber"}
            note={
              metrics.improvement_over_baseline > 0.2
                ? "Model gerçek sinyal yakalıyor."
                : "Baseline'a yakın — dikkatli yorumlayın."
            }
          />
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
