import { useRef, useState } from "react";
import { inspectUpload } from "../api";
import MappingStep from "../components/MappingStep";
import MetricCard from "../components/MetricCard";

const TEMPLATE_XLSX = "/analyzewise-ornek-veri.xlsx";
const TEMPLATE_CSV = "/analyzewise-ornek-veri.csv";

const NEED = {
  required: { text: "Zorunlu", cls: "badge-required" },
  either: { text: "Biri zorunlu", cls: "badge-required" },
  optional: { text: "İsteğe bağlı", cls: "badge-neutral" },
};

const FORMAT_COLUMNS = [
  { name: "CustomerNo", need: "required", what: "Müşteri no, kodu ya da e-postası", example: "MUS-0012", aliases: "Müşteri No, Cari Kodu, CustomerID" },
  { name: "Date", need: "required", what: "İşlem tarihi", example: "17.01.2019", aliases: "Tarih, Satış Tarihi, InvoiceDate" },
  { name: "Price", need: "either", what: "Birim fiyat", example: "20,35", aliases: "Birim Fiyat, Fiyat, UnitPrice" },
  { name: "TotalPrice", need: "either", what: "Satır tutarı (adet × fiyat). Birim fiyat yoksa buradan hesaplanır.", example: "₺61,05", aliases: "Tutar, Toplam, Amount" },
  {
    name: "TransactionNo",
    need: "optional",
    what: "Fatura ya da sipariş no. Yoksa aynı müşterinin aynı günkü satırları tek alışveriş sayılır.",
    example: "504788",
    aliases: "Fatura No, Sipariş No, InvoiceNo, OrderID",
  },
  { name: "Quantity", need: "optional", what: "Satılan adet. Yoksa 1 sayılır.", example: "3", aliases: "Adet, Miktar, Qty" },
  { name: "ProductNo", need: "optional", what: "Ürün kodu. Ürün önerileri için; yoksa ürün adı kullanılır.", example: "1002", aliases: "Ürün Kodu, Stok Kodu, SKU" },
  { name: "ProductName", need: "optional", what: "Ürün adı", example: "Demlik", aliases: "Ürün Adı, Stok Adı, Description" },
  { name: "Country", need: "optional", what: "Ülke ya da bölge", example: "Türkiye", aliases: "Ülke, Bölge" },
];

export default function UploadScreen({ dataset, onUploaded, onStartDemo, demoLoading, demoError }) {
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const inputRef = useRef(null);

  const [inspection, setInspection] = useState(null);

  async function handleFile(file) {
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      setInspection(await inspectUpload(file));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  if (inspection) {
    return (
      <div>
        <div className="screen-header">
          <h1 className="screen-title">Veri Yükle</h1>
        </div>
        <MappingStep
          key={inspection.upload_id}
          inspection={inspection}
          onDone={(result) => {
            setInspection(null);
            onUploaded(result);
          }}
          onCancel={() => setInspection(null)}
        />
      </div>
    );
  }

  return (
    <div>
      <div className="screen-header">
        <h1 className="screen-title">Veri Yükle</h1>
        <p className="screen-subtitle">
          Satış verinizi Excel ya da CSV olarak yükleyin. Kolon adları ve biçimler farklı olabilir: sistem hangi kolonun ne
          olduğunu tahmin eder, analizden önce size gösterip onaylatır.
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
        <p className="dropzone-title">{loading ? "Dosya okunuyor…" : "Dosyayı buraya bırakın"}</p>
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
                Sistemin aradığı bilgiler
              </p>
              <p className="upload-help-text">
                Her satır bir satış (bir faturadaki bir ürün). Kolon adları birebir aynı olmak zorunda değil; sıra önemli
                değil, fazladan kolonlar yok sayılır. Sıfırdan hazırlıyorsanız şablonu kullanın.
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
                      <span className={`badge ${NEED[c.need].cls}`}>{NEED[c.need].text}</span>
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
              <strong>Zorunlu olanlar:</strong> müşteri, tarih ve birim fiyat ya da satır tutarı. Fatura no yoksa aynı
              müşterinin aynı gündeki satırları tek alışveriş sayılır; adet yoksa her satır 1 adet sayılır.
            </li>
            <li>
              <strong>Kimlikler:</strong> müşteri ve fatura no harf içerebilir (MUS-0012, ORD-1001, e-posta). Baştaki
              sıfırlar korunur.
            </li>
            <li>
              <strong>Tarih ve sayılar:</strong> Excel tarih hücresi, 2026-10-22, 22.10.2026, 10/22/2026 gibi biçimler ve
              ₺1.234,50 ya da $1,234.50 gibi tutarlar okunur. Gün/ay sırası belirsizse size sorulur.
            </li>
            <li>
              <strong>Dosya yapısı:</strong> Başlığın üstündeki rapor başlığı satırları atlanır; birden fazla sayfa varsa
              veri olan sayfa seçilir, isterseniz değiştirebilirsiniz.
            </li>
            <li>
              <strong>Süre ve gizlilik:</strong> En az 6 ay, tercihen 1 yıllık veri. Dosya yalnızca oturumunuz boyunca
              bellekte tutulur; diske ya da veritabanına yazılmaz.
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
