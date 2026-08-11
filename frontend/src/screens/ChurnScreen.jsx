import { useEffect, useMemo, useState } from "react";
import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { getChurn, getChurnEvaluate } from "../api";
import DataTable from "../components/DataTable";
import MetricCard from "../components/MetricCard";
import SegmentFilter, { ALL_VALUE } from "../components/SegmentFilter";

const COLUMNS = [
  { key: "CustomerNo", label: "Müşteri No" },
  { key: "churn_probability", label: "Churn Olasılığı" },
  { key: "recency", label: "Son Alışverişten Gün" },
  { key: "frequency", label: "Sıklık" },
  { key: "risk_segment", label: "Risk Segmenti" },
];

const RISK_COLORS = {
  "düşük risk": "#059669",
  "orta risk": "#d97706",
  "yüksek risk": "#f97316",
  "çok yüksek risk": "#dc2626",
};

const tooltipStyle = {
  background: "var(--panel)",
  border: "1px solid var(--line)",
  borderRadius: 8,
  color: "var(--paper)",
  fontSize: 13,
};

function aucTone(auc) {
  if (auc >= 0.7) return "teal";
  if (auc >= 0.6) return "amber";
  return "rose";
}

export default function ChurnScreen({ sessionId }) {
  const [data, setData] = useState(null);
  const [metrics, setMetrics] = useState(null);
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

  const riskOptions = data ? Object.keys(data.risk_counts) : [];
  const chartData = data ? Object.entries(data.risk_counts).map(([risk, count]) => ({ risk, count })) : [];

  const filteredRows = useMemo(() => {
    if (!data) return [];
    const rows =
      selectedRisk === ALL_VALUE ? data.rows : data.rows.filter((r) => r.risk_segment === selectedRisk);
    return [...rows].sort((a, b) => b.churn_probability - a.churn_probability);
  }, [data, selectedRisk]);

  return (
    <div>
      <div className="screen-header">
        <h1 className="screen-title">Churn Tahmini</h1>
        <p className="screen-subtitle">Müşteri bazlı churn olasılığı — XGBoost sınıflandırıcı.</p>
      </div>

      {data && (
        <div className="control-row">
          <SegmentFilter
            label="Risk segmenti filtrele"
            options={riskOptions}
            counts={data.risk_counts}
            value={selectedRisk}
            onChange={setSelectedRisk}
          />
        </div>
      )}

      {loading && <div className="loading-state">Model eğitiliyor, bu biraz sürebilir…</div>}
      {error && <div className="error-state">{error}</div>}

      {metrics && !loading && (
        <div className="card-grid">
          <MetricCard label="Held-out ROC AUC" value={metrics.roc_auc.toFixed(3)} tone={aucTone(metrics.roc_auc)} />
          <MetricCard label="Test Seti" value={metrics.n_test.toLocaleString("tr-TR")} />
          <MetricCard label="Pozitif (Churn) Oranı" value={`%${(metrics.positive_rate * 100).toFixed(1)}`} />
        </div>
      )}

      {data && !loading && (
        <div className="receipt-card" style={{ marginBottom: 24 }}>
          <p className="receipt-label">Risk Segmentlerine Göre Dağılım</p>
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie
                data={chartData}
                dataKey="count"
                nameKey="risk"
                cx="50%"
                cy="50%"
                innerRadius={55}
                outerRadius={95}
                paddingAngle={2}
                cursor="pointer"
                onClick={(entry) => setSelectedRisk(entry.risk === selectedRisk ? ALL_VALUE : entry.risk)}
              >
                {chartData.map((entry) => (
                  <Cell
                    key={entry.risk}
                    fill={RISK_COLORS[entry.risk] ?? "#6b7280"}
                    opacity={selectedRisk === ALL_VALUE || selectedRisk === entry.risk ? 1 : 0.25}
                  />
                ))}
              </Pie>
              <Tooltip contentStyle={tooltipStyle} />
              <Legend wrapperStyle={{ fontSize: 12, color: "var(--paper-dim)" }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      )}

      {data && !loading && (
        <DataTable
          key={selectedRisk}
          columns={COLUMNS}
          rows={filteredRows}
          exportFilename="churn_tahminleri.csv"
        />
      )}
    </div>
  );
}
