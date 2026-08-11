import { useRef, useState } from "react";
import { uploadFile } from "../api";
import MetricCard from "../components/MetricCard";

export default function UploadScreen({ dataset, onUploaded }) {
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const inputRef = useRef(null);

  async function handleFile(file) {
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const result = await uploadFile(file);
      onUploaded(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <div className="screen-header">
        <h1 className="screen-title">Veri Yükle</h1>
        <p className="screen-subtitle">
          CRM işlem verinizi (.xlsx / .csv) yükleyin. En az müşteri no, işlem no, adet, fiyat ve tarih kolonları
          gerekir.
        </p>
      </div>

      <div
        className={`dropzone${dragging ? " dragging" : ""}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          handleFile(e.dataTransfer.files?.[0]);
        }}
      >
        <p className="dropzone-title">{loading ? "Yükleniyor…" : "Dosyayı buraya bırakın"}</p>
        <p className="dropzone-sub">ya da tıklayıp bilgisayarınızdan seçin — .xlsx, .xls, .csv</p>
        <input
          ref={inputRef}
          type="file"
          accept=".xlsx,.xls,.csv"
          hidden
          onChange={(e) => handleFile(e.target.files?.[0])}
        />
      </div>

      {error && <p className="error-state">{error}</p>}

      {dataset && (
        <div className="dataset-summary">
          <div className="card-grid">
            <MetricCard label="Dosya" value={dataset.filename} />
            <MetricCard label="Satır Sayısı" value={dataset.n_rows.toLocaleString("tr-TR")} tone="teal" />
            <MetricCard label="Müşteri Sayısı" value={dataset.n_customers.toLocaleString("tr-TR")} tone="teal" />
          </div>
          <p className="receipt-note">
            Veri yüklendi — sol menüden segmentasyon, CLTV, churn ve ürün önerisi ekranlarına geçebilirsiniz.
          </p>
        </div>
      )}
    </div>
  );
}
