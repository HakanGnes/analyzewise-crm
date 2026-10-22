import { useMemo, useState } from "react";
import { searchWindows } from "../api";
import ChartCard from "../charts/ChartCard";
import Heatmap from "../charts/Heatmap";
import { fmt } from "../charts/theme";
import DataTable from "../components/DataTable";

const COLUMNS = [
  { key: "observation_days", label: "Gözlem (gün)" },
  { key: "prediction_days", label: "Tahmin (gün)" },
  { key: "n_train_rows", label: "Eğitim satırı" },
  { key: "churn_auc", label: "Churn AUC" },
  { key: "cltv_mae", label: "CLTV MAE" },
  { key: "cltv_improvement_over_baseline", label: "CLTV iyileşme" },
];

function grid(rows, valueKey) {
  const obs = [...new Set(rows.map((r) => r.observation_days))].sort((a, b) => a - b);
  const pred = [...new Set(rows.map((r) => r.prediction_days))].sort((a, b) => a - b);
  return {
    columns: pred.map((p) => ({ key: String(p), label: `${p} gün tahmin` })),
    rows: obs.map((o) => ({
      key: String(o),
      label: `${o} gün gözlem`,
      values: Object.fromEntries(
        pred.map((p) => [String(p), rows.find((r) => r.observation_days === o && r.prediction_days === p)?.[valueKey]])
      ),
    })),
  };
}

export default function WindowSearchScreen({ sessionId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  function runSearch() {
    setLoading(true);
    setError(null);
    searchWindows(sessionId)
      .then((res) => setData(res))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }

  const views = useMemo(() => {
    if (!data?.rows?.length) return null;
    const best = [...data.rows].filter((r) => Number.isFinite(r.churn_auc)).sort((a, b) => b.churn_auc - a.churn_auc)[0];
    const bestCltv = [...data.rows].sort((a, b) => b.cltv_improvement_over_baseline - a.cltv_improvement_over_baseline)[0];
    return { auc: grid(data.rows, "churn_auc"), cltv: grid(data.rows, "cltv_improvement_over_baseline"), best, bestCltv };
  }, [data]);

  return (
    <div>
      <div className="screen-header">
        <h1 className="screen-title">Pencere Araması</h1>
        <p className="screen-subtitle">
          Modeller, müşterinin son X gününe bakıp sonraki Y gününü tahmin eder. Bu ekran farklı X ve Y değerlerini dener
          ve hangisinin daha iyi sonuç verdiğini gösterir. Birkaç dakika sürebilir.
        </p>
      </div>

      <button className="btn-primary" onClick={runSearch} disabled={loading} style={{ marginBottom: 20 }}>
        {loading ? "Taranıyor…" : data ? "Aramayı yeniden çalıştır" : "Aramayı başlat"}
      </button>

      {error && <div className="error-state">{error}</div>}

      {views && (
        <>
          <div className="chart-row">
            <ChartCard
              title={`Churn için en iyi pencere: ${views.best.observation_days} gün gözlem, ${views.best.prediction_days} gün tahmin (AUC ${fmt.dec(views.best.churn_auc, 2)})`}
              subtitle="Her hücre, o pencere çifti için churn modelinin ROC AUC skoru. Koyu renk daha iyi."
            >
              <Heatmap rowHeader="" rows={views.auc.rows} columns={views.auc.columns.map((c) => ({ ...c, format: (v) => fmt.dec(v, 2) }))} />
            </ChartCard>
            <ChartCard
              title={`CLTV için en iyi pencere: ${views.bestCltv.observation_days} gün gözlem, ${views.bestCltv.prediction_days} gün tahmin`}
              subtitle="Her hücre, CLTV modelinin herkese ortalamayı söylemeye göre hata azaltma oranı. Koyu renk daha iyi."
            >
              <Heatmap rowHeader="" rows={views.cltv.rows} columns={views.cltv.columns.map((c) => ({ ...c, format: (v) => fmt.pct(v) }))} />
            </ChartCard>
          </div>
          <DataTable columns={COLUMNS} rows={data.rows} pageSize={20} exportFilename="pencere_taramasi.csv" />
        </>
      )}
    </div>
  );
}
