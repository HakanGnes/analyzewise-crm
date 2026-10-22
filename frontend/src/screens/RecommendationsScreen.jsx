import { useEffect, useMemo, useState } from "react";
import { getProducts, getRecommendationTrend, getRecommendations } from "../api";
import BarList from "../charts/BarList";
import ChartCard from "../charts/ChartCard";
import SlopeGraph from "../charts/SlopeGraph";
import { fmt } from "../charts/theme";
import DataTable from "../components/DataTable";

const METHOD_TEXT = {
  fpgrowth: {
    label: "Birlikte alınanlar (FP-Growth)",
    subtitle:
      "Lift: bu iki ürünün aynı sepette görülme olasılığı, birbirinden bağımsız olsalardı beklenenin kaç katı. 1'in üstü gerçek bir ilişki demek.",
  },
  cf: {
    label: "Benzer müşteriler (iş birlikçi filtreleme)",
    subtitle:
      "Kosinüs benzerliği: iki ürünü aynı müşterilerin alma derecesi, 0 ile 1 arasında. Aynı sepette olmasalar da benzer müşterilerin tercihlerini yakalar.",
  },
};

function trendHeadline(items, anchorName) {
  if (!items.length) return `${anchorName} için iki dönemi karşılaştıracak kadar sepet yok`;
  const withDelta = items.map((d) => ({ ...d, delta: d.second - d.first }));
  const up = [...withDelta].sort((a, b) => b.delta - a.delta)[0];
  const down = [...withDelta].sort((a, b) => a.delta - b.delta)[0];
  if (up.delta >= 0.03 && Math.abs(up.delta) >= Math.abs(down.delta)) {
    return `${anchorName} alanlar arasında ${up.name} giderek daha çok tercih ediliyor (${fmt.pct(up.first)} → ${fmt.pct(up.second)})`;
  }
  if (down.delta <= -0.03) {
    return `${anchorName} ile ${down.name} birlikteliği zayıflıyor (${fmt.pct(down.first)} → ${fmt.pct(down.second)})`;
  }
  return `${anchorName} ile birlikte alınan ürünler iki dönemde de benzer`;
}

export default function RecommendationsScreen({ sessionId }) {
  const [catalog, setCatalog] = useState({ products: [], names: {}, popular: [] });
  const [productId, setProductId] = useState(null);
  const [method, setMethod] = useState("fpgrowth");
  const [topN, setTopN] = useState(6);
  const [recs, setRecs] = useState(null);
  const [trend, setTrend] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getProducts(sessionId).then((res) => {
      setCatalog(res);
      const first = res.popular?.[0] ?? res.products[0];
      if (first !== undefined) setProductId(first);
    });
  }, [sessionId]);

  useEffect(() => {
    if (productId === null) return;
    let cancelled = false;
    setError(null);
    getRecommendations(sessionId, productId, method, topN)
      .then((res) => !cancelled && setRecs(res))
      .catch((err) => !cancelled && setError(err.message));
    return () => {
      cancelled = true;
    };
  }, [sessionId, productId, method, topN]);

  useEffect(() => {
    if (productId === null) return;
    let cancelled = false;
    getRecommendationTrend(sessionId, productId)
      .then((res) => !cancelled && setTrend(res))
      .catch(() => !cancelled && setTrend({ items: [], periods: [] }));
    return () => {
      cancelled = true;
    };
  }, [sessionId, productId]);

  const nameOf = (id) => catalog.names?.[String(id)] ?? String(id);
  const anchorName = nameOf(productId);

  const options = useMemo(() => {
    const popular = new Set(catalog.popular ?? []);
    const byName = (a, b) => nameOf(a).localeCompare(nameOf(b), "tr");
    return {
      popular: (catalog.popular ?? []).slice(),
      rest: catalog.products.filter((p) => !popular.has(p)).sort(byName),
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [catalog]);

  if (catalog.products.length === 0) {
    return (
      <div>
        <div className="screen-header">
          <h1 className="screen-title">Ürün Önerisi</h1>
        </div>
        <div className="empty-state">
          Bu veri setinde ürün no (ProductNo) kolonu yok. Ürün önerisi için bu kolonu içeren bir dosya yükleyin.
        </div>
      </div>
    );
  }

  const bars = (recs?.items ?? []).map((it) => ({ key: String(it.product_id), label: it.name, value: it.score }));
  const scoreFormat = method === "fpgrowth" ? (v) => `${fmt.dec(v, 1)}×` : (v) => fmt.dec(v, 2);

  const tableColumns =
    method === "fpgrowth"
      ? [
          { key: "product_id", label: "Ürün No" },
          { key: "name", label: "Ürün" },
          { key: "score", label: "Lift" },
          { key: "confidence_pct", label: "Güven" },
        ]
      : [
          { key: "product_id", label: "Ürün No" },
          { key: "name", label: "Ürün" },
          { key: "score", label: "Benzerlik" },
        ];
  const tableRows = (recs?.items ?? []).map((it) => ({
    ...it,
    ProductNo: it.product_id,
    confidence_pct: it.confidence !== undefined ? fmt.pct(it.confidence) : undefined,
  }));

  return (
    <div>
      <div className="screen-header">
        <h1 className="screen-title">Ürün Önerisi</h1>
        <p className="screen-subtitle">
          Bir ürün seçin: onunla birlikte önerilecek ürünleri ve bu ilişkilerin zaman içinde nasıl değiştiğini görün.
        </p>
      </div>

      <div className="control-row">
        <div className="control-group">
          <span className="control-label">Ürün</span>
          <select className="select" value={productId ?? ""} onChange={(e) => setProductId(Number(e.target.value) || e.target.value)}>
            <optgroup label="En çok satanlar">
              {options.popular.map((p) => (
                <option key={p} value={p}>
                  {nameOf(p)}
                </option>
              ))}
            </optgroup>
            <optgroup label="Diğer ürünler">
              {options.rest.map((p) => (
                <option key={p} value={p}>
                  {nameOf(p)}
                </option>
              ))}
            </optgroup>
          </select>
        </div>
        <div className="control-group">
          <span className="control-label">Öneri yöntemi</span>
          <div className="radio-group">
            <button className={`radio-pill${method === "fpgrowth" ? " active" : ""}`} onClick={() => setMethod("fpgrowth")}>
              Birlikte alınanlar
            </button>
            <button className={`radio-pill${method === "cf" ? " active" : ""}`} onClick={() => setMethod("cf")}>
              Benzer müşteriler
            </button>
          </div>
        </div>
        <div className="control-group">
          <span className="control-label">Öneri sayısı</span>
          <div className="slider-row">
            <input type="range" min={3} max={10} value={topN} onChange={(e) => setTopN(Number(e.target.value))} />
            <span style={{ fontVariantNumeric: "tabular-nums" }}>{topN}</span>
          </div>
        </div>
      </div>

      {error && <div className="error-state">{error}</div>}

      <div className="chart-row">
        <ChartCard
          title={
            bars.length
              ? `${anchorName} için en güçlü öneri: ${bars[0].label}`
              : `${anchorName} için ${method === "fpgrowth" ? "birlikte alınma kuralı" : "benzer ürün"} bulunamadı`
          }
          subtitle={METHOD_TEXT[method].subtitle}
          footnote={
            method === "fpgrowth"
              ? "Kurallar FP-Growth ile, yapılandırmadaki ülke filtresine göre çıkarılır. Az kural çıkıyorsa diğer yönteme geçin."
              : undefined
          }
        >
          {bars.length ? (
            <BarList data={bars} valueFormat={scoreFormat} />
          ) : (
            <p className="empty-state" style={{ padding: "12px 0" }}>
              {method === "fpgrowth"
                ? "Bu ürün için yeterli destekle bir kural yok. 'Benzer müşteriler' yöntemini deneyin."
                : "Bu ürünü alan müşterilerle örtüşen başka ürün bulunamadı."}
            </p>
          )}
        </ChartCard>

        <ChartCard title="Önerilerin tablo görünümü" subtitle="Aynı öneriler; CSV olarak indirip kampanya listesine ekleyebilirsiniz.">
          {tableRows.length > 0 ? (
            <DataTable
              key={`${productId}-${method}-${topN}`}
              columns={tableColumns}
              rows={tableRows}
              pageSize={10}
              exportFilename={`urun_onerileri_${productId}.csv`}
            />
          ) : (
            <p className="empty-state" style={{ padding: "12px 0" }}>Gösterilecek öneri yok.</p>
          )}
        </ChartCard>
      </div>

      <ChartCard
        title={trend ? trendHeadline(trend.items, anchorName) : "Dönemsel değişim hesaplanıyor…"}
        subtitle={`${anchorName} içeren sepetlerin yüzde kaçında diğer ürün de vardı: veri döneminin ilk yarısı ile ikinci yarısı. Aynı ürünler, iki dönem; çizginin eğimi değişimi gösterir.`}
        footnote={
          trend?.anchor_baskets?.length
            ? `Hesaplanan sepet sayısı: ilk yarı ${fmt.int(trend.anchor_baskets[0])}, ikinci yarı ${fmt.int(trend.anchor_baskets[1])}. Yükselen çizgi kampanyada öne çıkarılacak eşleşme, düşen çizgi zayıflayan bir alışkanlıktır.`
            : undefined
        }
      >
        {trend?.items?.length ? (
          <div className="slopegraph-frame">
            <SlopeGraph items={trend.items} periods={trend.periods} leftTitle="İlk yarı" rightTitle="İkinci yarı" />
          </div>
        ) : (
          <p className="empty-state" style={{ padding: "12px 0" }}>
            {trend ? "Karşılaştırma için en az 5 ortak sepet gerekir." : "Yükleniyor…"}
          </p>
        )}
      </ChartCard>
    </div>
  );
}
