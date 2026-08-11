import { useState } from "react";
import { searchWindows } from "../api";
import DataTable from "../components/DataTable";

const COLUMNS = [
  { key: "observation_days", label: "Gözlem (gün)" },
  { key: "prediction_days", label: "Tahmin (gün)" },
  { key: "n_train_rows", label: "Eğitim Satırı" },
  { key: "churn_auc", label: "Churn AUC" },
  { key: "cltv_mae", label: "CLTV MAE" },
  { key: "cltv_improvement_over_baseline", label: "CLTV İyileşme" },
];

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

  return (
    <div>
      <div className="screen-header">
        <h1 className="screen-title">Pencere Araması</h1>
        <p className="screen-subtitle">
          Farklı gözlem/tahmin penceresi (observation/prediction days) kombinasyonlarını dener, hangisinin daha
          yüksek churn AUC / daha düşük CLTV MAE verdiğini karşılaştırır. Sabit hiperparametrelerle hızlı bir
          tarama — bu birkaç dakika sürebilir.
        </p>
      </div>

      <button className="btn-primary" onClick={runSearch} disabled={loading} style={{ marginBottom: 20 }}>
        {loading ? "Taranıyor…" : "Aramayı Başlat"}
      </button>

      {error && <div className="error-state">{error}</div>}
      {data && (
        <DataTable columns={COLUMNS} rows={data.rows} pageSize={20} exportFilename="pencere_taramasi.csv" />
      )}
    </div>
  );
}
