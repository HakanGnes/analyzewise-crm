import { useRef, useState } from "react";
import { uploadFile } from "../api";
import MetricCard from "../components/MetricCard";

const TEMPLATE_XLSX = "/analyzewise-ornek-veri.xlsx";
const TEMPLATE_CSV = "/analyzewise-ornek-veri.csv";

const FORMAT_COLUMNS = [
  { name: "CustomerNo", required: true, what: "Müşteriyi tanımlayan no ya da kod", example: "12546", aliases: "Müşteri No, CustomerID" },
  {
    name: "TransactionNo",
    required: true,
    what: "Fatura ya da sipariş no. Aynı sepetteki satırlar aynı no'yu taşır.",
    example: "504788",
    aliases: "Fatura No, Sipariş No, InvoiceNo, OrderID",
  },
  { name: "Date", required: true, what: "İşlem tarihi", example: "17.01.2019", aliases: "Tarih, InvoiceDate, OrderDate" },
  { name: "Quantity", required: true, what: "Satılan adet", example: "3", aliases: "Adet, Miktar, Qty" },
  { name: "Price", required: true, what: "Birim fiyat. Satır tutarı adet × fiyat olarak hesaplanır.", example: "20,35", aliases: "Birim Fiyat, Fiyat, UnitPrice" },
  { name: "ProductNo", required: false, what: "Ürün kodu. Ürün önerisi ekranı için gerekir.", example: "1002", aliases: "Ürün Kodu, Stok Kodu, StockCode, SKU" },
  { name: "ProductName", required: false, what: "Ürün adı. Önerilerde kod yerine görünür.", example: "Demlik", aliases: "Ürün Adı, Description" },
  { name: "Country", required: false, what: "Ülke", example: "Türkiye", aliases: "Ülke" },
];

export default function UploadScreen({ dataset, onUploaded, onStartDemo, demoLoading, demoError }) {
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
          Satış işlemlerinizi Excel ya da CSV olarak yükleyin. Müşteri no, fatura no, tarih, adet ve fiyat yeterli;
          beklenen biçim aşağıda, hazır şablonu indirip doldurabilirsiniz.
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

      <div className="upload-help">
        <section className="format-guide" aria-labelledby="format-guide-title">
          <div className="format-guide-head">
            <div>
              <p className="upload-help-title" id="format-guide-title">
                Dosyanız nasıl olmalı?
              </p>
              <p className="upload-help-text">
                Excel ya da CSV; her satır bir faturadaki bir ürün. Kolon sırası önemli değil, fazladan kolonlar yok
                sayılır.
              </p>
            </div>
            <div className="format-guide-downloads">
              <a className="btn-secondary" href={TEMPLATE_XLSX} download>
                Örnek şablon (.xlsx)
              </a>
              <a className="btn-secondary" href={TEMPLATE_CSV} download>
                .csv
              </a>
            </div>
          </div>

          <div className="data-table-wrap">
            <table className="data-table format-table">
              <thead>
                <tr>
                  <th scope="col">Kolon</th>
                  <th scope="col">Gerekli mi</th>
                  <th scope="col">İçerik</th>
                  <th scope="col">Örnek</th>
                </tr>
              </thead>
              <tbody>
                {FORMAT_COLUMNS.map((c) => (
                  <tr key={c.name}>
                    <td>
                      <code>{c.name}</code>
                      <span className="format-aliases">ya da {c.aliases}</span>
                    </td>
                    <td>
                      <span className={`badge ${c.required ? "badge-required" : "badge-neutral"}`}>
                        {c.required ? "Zorunlu" : "İsteğe bağlı"}
                      </span>
                    </td>
                    <td>{c.what}</td>
                    <td className="format-example">{c.example}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <ul className="format-rules">
            <li>
              <strong>Tarih:</strong> Excel tarih hücresi en güvenlisi. Metin olarak 2026-10-22, 22.10.2026 ya da
              22/10/2026 yazabilirsiniz; saat eklenebilir.
            </li>
            <li>
              <strong>Süre:</strong> En az 6 ay (180 gün), tercihen 1 yıllık işlem geçmişi. Modeller müşterinin 90
              gününe bakıp sonraki 90 günü tahmin eder.
            </li>
            <li>
              <strong>Sayılar:</strong> 20,35 ve 20.35 ikisi de olur. Adedi ya da fiyatı 0 veya negatif satırlar
              (iadeler, iptaller) ve müşteri no'su boş satırlar analize alınmaz.
            </li>
            <li>
              <strong>Kolon adları:</strong> Türkçe adlar ve yaygın e-ticaret dışa aktarımları (ör. UCI Online
              Retail) otomatik tanınır. Eksik bir şey varsa yükleme anında hangi kolonun eksik olduğu yazılır.
            </li>
            <li>
              <strong>Gizlilik:</strong> Dosya yalnızca oturumunuz boyunca bellekte tutulur; diske ya da veritabanına
              yazılmaz.
            </li>
          </ul>
        </section>

        <div className="upload-demo">
          <p className="upload-help-title">Elinde dosya yok mu?</p>
          <p className="upload-help-text">600 müşterilik sentetik bir mağaza verisiyle tüm ekranları dene.</p>
          <button className="btn-primary" onClick={onStartDemo} disabled={demoLoading}>
            {demoLoading ? "Demo hazırlanıyor…" : "Demo veriyle dene"}
          </button>
          {demoError && <p className="error-state" style={{ padding: "8px 0 0" }}>{demoError}</p>}
        </div>
      </div>

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
