import { useEffect, useState } from "react";
import { getProducts, getRecommendations } from "../api";

export default function RecommendationsScreen({ sessionId }) {
  const [products, setProducts] = useState([]);
  const [productId, setProductId] = useState(null);
  const [method, setMethod] = useState("fpgrowth");
  const [topN, setTopN] = useState(5);
  const [recs, setRecs] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    getProducts(sessionId).then((res) => {
      setProducts(res.products);
      if (res.products.length > 0) setProductId(res.products[0]);
    });
  }, [sessionId]);

  function handleSubmit() {
    if (productId === null) return;
    setLoading(true);
    setError(null);
    getRecommendations(sessionId, productId, method, topN)
      .then((res) => setRecs(res.recommendations))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }

  return (
    <div>
      <div className="screen-header">
        <h1 className="screen-title">Ürün Öneri Sistemi</h1>
        <p className="screen-subtitle">FP-Growth (birlikte alınanlar) veya item-based collaborative filtering.</p>
      </div>

      {products.length === 0 ? (
        <div className="empty-state">Bu veri kümesinde ürün no kolonu bulunamadı.</div>
      ) : (
        <>
          <div className="control-row">
            <div className="control-group">
              <span className="control-label">Yöntem</span>
              <div className="radio-group">
                <button className={`radio-pill${method === "fpgrowth" ? " active" : ""}`} onClick={() => setMethod("fpgrowth")}>
                  FP-Growth
                </button>
                <button className={`radio-pill${method === "cf" ? " active" : ""}`} onClick={() => setMethod("cf")}>
                  Collaborative Filtering
                </button>
              </div>
            </div>
            <div className="control-group">
              <span className="control-label">Ürün</span>
              <select className="select" value={productId ?? ""} onChange={(e) => setProductId(e.target.value)}>
                {products.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </div>
            <div className="control-group">
              <span className="control-label">Öneri sayısı</span>
              <div className="slider-row">
                <input type="range" min={1} max={10} value={topN} onChange={(e) => setTopN(Number(e.target.value))} />
                <span style={{ fontFamily: "var(--font-mono)" }}>{topN}</span>
              </div>
            </div>
            <button className="btn-primary" onClick={handleSubmit} disabled={loading}>
              {loading ? "Hesaplanıyor…" : "Önerileri Gör"}
            </button>
          </div>

          {error && <div className="error-state">{error}</div>}

          {recs && (
            <div className="receipt-card">
              <p className="receipt-label">Önerilen Ürünler</p>
              {recs.length === 0 ? (
                <p className="receipt-note">Bu ürün için yeterli veri/ilişki bulunamadı.</p>
              ) : (
                <ol style={{ margin: 0, paddingLeft: 20, fontFamily: "var(--font-mono)", fontSize: 15 }}>
                  {recs.map((r) => (
                    <li key={r} style={{ marginBottom: 4 }}>
                      {r}
                    </li>
                  ))}
                </ol>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
