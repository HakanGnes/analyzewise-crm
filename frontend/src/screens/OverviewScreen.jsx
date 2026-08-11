import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getOverview } from "../api";
import MetricCard from "../components/MetricCard";

const tooltipStyle = {
  background: "var(--panel)",
  border: "1px solid var(--line)",
  borderRadius: 8,
  color: "var(--paper)",
  fontSize: 13,
};

export default function OverviewScreen({ sessionId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getOverview(sessionId)
      .then((res) => !cancelled && setData(res))
      .catch((err) => !cancelled && setError(err.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  if (loading) return <div className="loading-state">Özet hesaplanıyor…</div>;
  if (error) return <div className="error-state">{error}</div>;
  if (!data) return null;

  const { kpis, monthly_trend: trend } = data;

  return (
    <div>
      <div className="screen-header">
        <h1 className="screen-title">Genel Bakış</h1>
        <p className="screen-subtitle">
          {kpis.date_min} — {kpis.date_max} arası veri özeti. Detaylı analizler için sol menüden ilerleyin.
        </p>
      </div>

      <div className="card-grid">
        <MetricCard label="Toplam Müşteri" value={kpis.total_customers.toLocaleString("tr-TR")} tone="teal" />
        <MetricCard
          label="Toplam Gelir"
          value={kpis.total_revenue.toLocaleString("tr-TR", { maximumFractionDigits: 0 })}
        />
        <MetricCard label="Toplam İşlem" value={kpis.total_transactions.toLocaleString("tr-TR")} />
        <MetricCard label="Ort. Sipariş Değeri" value={kpis.avg_order_value.toFixed(2)} />
      </div>

      <div className="chart-grid">
        <div className="receipt-card">
          <p className="receipt-label">Aylık Gelir Trendi</p>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={trend}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
              <XAxis dataKey="month" tick={{ fill: "var(--paper-dim)", fontSize: 11 }} />
              <YAxis tick={{ fill: "var(--paper-dim)", fontSize: 11 }} />
              <Tooltip contentStyle={tooltipStyle} />
              <Line type="monotone" dataKey="revenue" stroke="var(--teal)" strokeWidth={2.5} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="receipt-card">
          <p className="receipt-label">Aylık İşlem Sayısı</p>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={trend}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
              <XAxis dataKey="month" tick={{ fill: "var(--paper-dim)", fontSize: 11 }} />
              <YAxis tick={{ fill: "var(--paper-dim)", fontSize: 11 }} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="transactions" fill="var(--teal)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="receipt-card">
        <p className="receipt-label">Yeni Müşteri Kazanımı (Aylık)</p>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={trend}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
            <XAxis dataKey="month" tick={{ fill: "var(--paper-dim)", fontSize: 11 }} />
            <YAxis tick={{ fill: "var(--paper-dim)", fontSize: 11 }} />
            <Tooltip contentStyle={tooltipStyle} />
            <Bar dataKey="new_customers" fill="var(--amber)" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
