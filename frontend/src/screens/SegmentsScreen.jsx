import { useEffect, useMemo, useState } from "react";
import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { getSegments } from "../api";
import DataTable from "../components/DataTable";
import SegmentFilter, { ALL_VALUE } from "../components/SegmentFilter";

const COLUMNS = [
  { key: "CustomerNo", label: "Müşteri No" },
  { key: "recency", label: "Recency" },
  { key: "frequency", label: "Sıklık" },
  { key: "monetary", label: "Harcama" },
  { key: "segment", label: "Segment" },
];

const PALETTE = ["#4f46e5", "#059669", "#d97706", "#dc2626", "#0891b2", "#7c3aed", "#db2777", "#65a30d", "#ea580c", "#0284c7"];

const tooltipStyle = {
  background: "var(--panel)",
  border: "1px solid var(--line)",
  borderRadius: 8,
  color: "var(--paper)",
  fontSize: 13,
};

export default function SegmentsScreen({ sessionId }) {
  const [auto, setAuto] = useState(false);
  const [k, setK] = useState(6);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedSegment, setSelectedSegment] = useState(ALL_VALUE);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setSelectedSegment(ALL_VALUE);
    getSegments(sessionId, { k, auto })
      .then((res) => !cancelled && setData(res))
      .catch((err) => !cancelled && setError(err.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [sessionId, k, auto]);

  const segmentOptions = data ? Object.keys(data.segment_counts) : [];
  const chartData = data
    ? Object.entries(data.segment_counts).map(([segment, count]) => ({ segment, count }))
    : [];

  const filteredRows = useMemo(() => {
    if (!data) return [];
    if (selectedSegment === ALL_VALUE) return data.rows;
    return data.rows.filter((row) => row.segment === selectedSegment);
  }, [data, selectedSegment]);

  return (
    <div>
      <div className="screen-header">
        <h1 className="screen-title">Müşteri Segmentasyonu</h1>
        <p className="screen-subtitle">
          K-Means kümeleme ile veri odaklı segmentasyon. Segment sayısını elle seçin ya da elbow yöntemiyle
          otomatik belirlensin.
        </p>
      </div>

      <div className="control-row">
        <div className="control-group">
          <span className="control-label">Segment sayısı</span>
          <div className="slider-row">
            <input
              type="range"
              min={2}
              max={10}
              value={k}
              disabled={auto}
              onChange={(e) => setK(Number(e.target.value))}
            />
            <span style={{ fontFamily: "var(--font-mono)" }}>{k}</span>
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
            label="Segment filtrele"
            options={segmentOptions}
            counts={data.segment_counts}
            value={selectedSegment}
            onChange={setSelectedSegment}
          />
        )}
      </div>

      {loading && <div className="loading-state">Segmentler hesaplanıyor…</div>}
      {error && <div className="error-state">{error}</div>}

      {data && !loading && (
        <>
          <div className="receipt-card" style={{ marginBottom: 24 }}>
            <p className="receipt-label">Segment Dağılımı — bir dilime tıklayarak filtreleyin</p>
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie
                  data={chartData}
                  dataKey="count"
                  nameKey="segment"
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={100}
                  paddingAngle={2}
                  cursor="pointer"
                  onClick={(entry) =>
                    setSelectedSegment(entry.segment === selectedSegment ? ALL_VALUE : entry.segment)
                  }
                >
                  {chartData.map((entry, i) => (
                    <Cell
                      key={entry.segment}
                      fill={PALETTE[i % PALETTE.length]}
                      opacity={selectedSegment === ALL_VALUE || selectedSegment === entry.segment ? 1 : 0.25}
                    />
                  ))}
                </Pie>
                <Tooltip contentStyle={tooltipStyle} />
                <Legend wrapperStyle={{ fontSize: 12, color: "var(--paper-dim)" }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <DataTable
            key={`${k}-${auto}-${selectedSegment}`}
            columns={COLUMNS}
            rows={filteredRows}
            exportFilename="musteri_segmentleri.csv"
          />
        </>
      )}
    </div>
  );
}
