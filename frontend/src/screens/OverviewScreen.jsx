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
import ChartCard from "../charts/ChartCard";
import { C, axisTick, fmt, tooltipStyle } from "../charts/theme";
import MetricCard from "../components/MetricCard";

function peakTitle(trend, key, noun) {
  if (!trend.length) return "";
  const peak = trend.reduce((a, b) => (b[key] > a[key] ? b : a));
  return `En çok ${noun} ${peak.month} ayında: ${fmt.int(peak[key])}`;
}

function revenueTitle(trend) {
  if (trend.length < 2) return "Aylık gelir";
  const first = trend[0].revenue || 1;
  const last = trend[trend.length - 1].revenue;
  const change = last / first - 1;
  return change >= 0
    ? `Aylık gelir dönem boyunca ${fmt.pct(change)} arttı`
    : `Aylık gelir dönem boyunca ${fmt.pct(-change)} azaldı`;
}

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

      <div className="stat-strip">
        <MetricCard label="Toplam Müşteri" value={kpis.total_customers.toLocaleString("tr-TR")} tone="teal" />
        <MetricCard
          label="Toplam Gelir"
          value={kpis.total_revenue.toLocaleString("tr-TR", { maximumFractionDigits: 0 })}
        />
        <MetricCard label="Toplam İşlem" value={kpis.total_transactions.toLocaleString("tr-TR")} />
        <MetricCard label="Ort. Sipariş Değeri" value={kpis.avg_order_value.toFixed(2)} />
      </div>

      <div className="chart-row">
        <ChartCard title={revenueTitle(trend)} subtitle="Aylık toplam gelir.">
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={trend} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
              <CartesianGrid stroke={C.grid} vertical={false} />
              <XAxis dataKey="month" tick={axisTick} stroke={C.axis} />
              <YAxis tick={axisTick} stroke={C.axis} tickFormatter={(v) => fmt.money(v)} width={64} />
              <Tooltip contentStyle={tooltipStyle} formatter={(v) => [fmt.money(v), "Gelir"]} />
              <Line type="monotone" dataKey="revenue" stroke={C.series} strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title={peakTitle(trend, "transactions", "işlem")} subtitle="Aylık benzersiz işlem (sepet) sayısı.">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={trend} margin={{ top: 8, right: 12, bottom: 4, left: 4 }} barCategoryGap={2}>
              <CartesianGrid stroke={C.grid} vertical={false} />
              <XAxis dataKey="month" tick={axisTick} stroke={C.axis} />
              <YAxis tick={axisTick} stroke={C.axis} width={44} />
              <Tooltip contentStyle={tooltipStyle} cursor={{ fill: C.grid }} formatter={(v) => [fmt.int(v), "İşlem"]} />
              <Bar dataKey="transactions" fill={C.series} radius={[4, 4, 0, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <ChartCard
        title={peakTitle(trend, "new_customers", "yeni müşteri")}
        subtitle="Her ay ilk kez alışveriş yapan müşteri sayısı."
      >
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={trend} margin={{ top: 8, right: 12, bottom: 4, left: 4 }} barCategoryGap={2}>
            <CartesianGrid stroke={C.grid} vertical={false} />
            <XAxis dataKey="month" tick={axisTick} stroke={C.axis} />
            <YAxis tick={axisTick} stroke={C.axis} width={44} allowDecimals={false} />
            <Tooltip contentStyle={tooltipStyle} cursor={{ fill: C.grid }} formatter={(v) => [fmt.int(v), "Yeni müşteri"]} />
            <Bar dataKey="new_customers" fill={C.series} radius={[4, 4, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>
    </div>
  );
}
