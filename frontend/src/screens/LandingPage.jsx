import SegmentScatter from "../components/SegmentScatter";
import "../landing.css";

const REPO_URL = "https://github.com/HakanGnes/analyzewise-crm";

const MODULES = [
  {
    title: "Müşteri segmentasyonu",
    text: "Son alışveriş zamanı, alışveriş sıklığı ve harcamaya göre müşterileri 2 ile 10 arasında gruba ayırır. Grup sınırlarını sabit kurallar değil, verinin kendisi belirler.",
    method: "K-Means kümeleme",
  },
  {
    title: "Yaşam boyu değer (CLTV)",
    text: "Her müşterinin önümüzdeki 90 günde ne kadar harcayacağını tahmin eder ve müşterileri değerine göre sıralar.",
    method: "XGBoost regresyon, iki aşamalı model seçeneğiyle",
  },
  {
    title: "Churn riski",
    text: "Her müşteri için bir sonraki dönemde geri gelmeme olasılığını hesaplar; düşük, orta, yüksek ve çok yüksek risk gruplarına ayırır.",
    method: "XGBoost sınıflandırıcı",
  },
  {
    title: "Ürün önerisi",
    text: "Aynı sepette sık görülen ürünleri ve benzer müşterilerin tercihlerini bularak çapraz satış önerileri çıkarır.",
    method: "FP-Growth ve iş birlikçi filtreleme",
  },
];

const STEPS = [
  {
    title: "Dosyanı yükle",
    text: "Excel ya da CSV. Müşteri no, fatura no, tarih, adet ve fiyat kolonları yeterli; ürün kodu varsa öneri ekranı da açılır. En az 6 aylık, tercihen 1 yıllık satış verisi.",
    link: { href: "/analyzewise-ornek-veri.xlsx", label: "Örnek şablonu indir (.xlsx)" },
  },
  {
    title: "Modeller verinle eğitilir",
    text: "Segmentasyon birkaç saniyede hazır. CLTV ve churn modelleri hiperparametre aramasıyla eğitildiği için biraz daha uzun sürer.",
  },
  {
    title: "Listeni dışa aktar",
    text: "İstediğin segmenti ya da risk grubunu filtrele, CSV olarak indir ve kampanyana bağla.",
  },
];

export default function LandingPage({ onStartDemo, onUpload, demoLoading, demoError }) {
  const demoButton = (
    <button className="lp-btn lp-btn-primary" onClick={onStartDemo} disabled={demoLoading}>
      {demoLoading ? "Demo hazırlanıyor…" : "Demo veriyle dene"}
    </button>
  );

  return (
    <div className="lp">
      <header className="lp-nav">
        <div className="lp-wrap lp-nav-inner">
          <a className="lp-logo" href="#top">
            <img src="/favicon.svg" alt="" width="26" height="26" />
            AnalyzeWise
          </a>
          <nav className="lp-nav-links" aria-label="Sayfa bölümleri">
            <a href="#neler-yapar">Neler yapar</a>
            <a href="#sonuclar">Sonuçlar</a>
            <a href="#nasil-calisir">Nasıl çalışır</a>
            <a href={REPO_URL} target="_blank" rel="noreferrer">
              GitHub
            </a>
          </nav>
          <button className="lp-btn lp-btn-small" onClick={onUpload}>
            Uygulamayı aç
          </button>
        </div>
      </header>

      <main id="top">
        <section className="lp-hero">
          <div className="lp-wrap lp-hero-grid">
            <div className="lp-hero-copy">
              <h1>Satış verinden kimin geri geleceğini, kimin gideceğini gör.</h1>
              <p className="lp-lead">
                AnalyzeWise, perakende işlem verini müşteri segmentlerine, yaşam boyu değer ve churn tahminlerine,
                ürün önerilerine dönüştürür. Tek bir Excel dosyası yeterli.
              </p>
              <div className="lp-cta-row">
                {demoButton}
                <button className="lp-btn lp-btn-ghost" onClick={onUpload}>
                  Kendi verini yükle
                </button>
              </div>
              {demoError ? (
                <p className="lp-error" role="alert">
                  {demoError}
                </p>
              ) : (
                <p className="lp-note">
                  Demo, sentetik bir mağaza verisiyle açılır. Sunucu uyku modundaysa ilk açılış 30–60 saniye sürebilir.
                </p>
              )}
            </div>
            <SegmentScatter />
          </div>
        </section>

        <section className="lp-section" id="neler-yapar">
          <div className="lp-wrap lp-split">
            <div className="lp-section-head">
              <h2>Tek dosyadan dört analiz</h2>
              <p>
                Her modül aynı veriyi kullanır, ayrıca hazırlık gerekmez. Sonuçlar müşteri bazında listelenir ve
                filtrelenebilir.
              </p>
            </div>
            <ul className="lp-modules">
              {MODULES.map((m) => (
                <li key={m.title}>
                  <h3>{m.title}</h3>
                  <p>{m.text}</p>
                  <span className="lp-method">{m.method}</span>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="lp-section lp-results" id="sonuclar">
          <div className="lp-wrap">
            <h2>Ölçülmüş, şişirilmemiş sonuçlar</h2>
            <p className="lp-results-intro">
              Modeller yaklaşık 9.500 satırlık gerçek bir perakende veri setinde, eğitim sırasında hiç görmedikleri
              müşteriler üzerinde test edildi. Bir müşterinin farklı dönemleri hiçbir zaman hem eğitimde hem testte yer
              almaz; skorlar bu yüzden veri sızıntısından arındırılmıştır.
            </p>
            <div className="lp-results-grid">
              <div className="lp-result">
                <p className="lp-result-value">0,74</p>
                <p className="lp-result-text">
                  <strong>Churn modelinin ROC AUC skoru.</strong> Bir sonraki dönemde geri gelmeyecek müşteriyi rastgele
                  tahminden (0,50) belirgin şekilde daha iyi ayırıyor.
                </p>
              </div>
              <div className="lp-result">
                <p className="lp-result-value">%31</p>
                <p className="lp-result-text">
                  <strong>Daha düşük CLTV tahmin hatası.</strong> Herkese ortalama harcamayı söyleyen basit yaklaşıma
                  kıyasla ortalama mutlak hata bu oranda azalıyor.
                </p>
              </div>
            </div>
          </div>
        </section>

        <section className="lp-section" id="nasil-calisir">
          <div className="lp-wrap">
            <h2>Nasıl çalışır</h2>
            <ol className="lp-steps">
              {STEPS.map((s, i) => (
                <li key={s.title}>
                  <span className="lp-step-num" aria-hidden="true">
                    {i + 1}
                  </span>
                  <h3>{s.title}</h3>
                  <p>{s.text}</p>
                  {s.link && (
                    <a className="lp-step-link" href={s.link.href} download>
                      {s.link.label}
                    </a>
                  )}
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="lp-closing">
          <div className="lp-wrap lp-closing-inner">
            <h2>Denemek için dosya gerekmiyor.</h2>
            <p>Demo; 600 müşterilik, bir yıllık sentetik bir mağaza verisiyle tüm ekranları açar.</p>
            {demoButton}
          </div>
        </section>
      </main>

      <footer className="lp-footer">
        <div className="lp-wrap lp-footer-inner">
          <p>Hakan Güneş tarafından geliştirildi. React, FastAPI, scikit-learn ve XGBoost ile yapıldı.</p>
          <a href={REPO_URL} target="_blank" rel="noreferrer">
            Kaynak kodu GitHub'da
          </a>
        </div>
      </footer>
    </div>
  );
}
