# AnalyzeWise-CRM — Faz 3 (React + FastAPI)

Faz 2'nin (K-Means segmentasyon, XGBoost CLTV/churn, FP-Growth + collaborative
filtering ürün önerisi) Streamlit arayüzünü, ayrı bir **FastAPI backend** +
**React frontend**'e taşıyan sürüm. Analiz mantığının kendisi değişmedi —
`backend/analyzewise_crm/` paketi Faz 2.8'deki ile birebir aynı (sızıntı
düzeltmesi, rolling-window, hurdle model, hepsi dahil).

```
analyzewise-crm-phase3/
  backend/
    analyzewise_crm/   ← analiz paketi (Faz 2.8 ile aynı)
    app/
      main.py          ← FastAPI route'ları
      store.py          ← in-memory oturum/cache deposu
      utils.py           ← pandas/numpy → JSON dönüşümü
    tests/
      test_api.py       ← FastAPI TestClient ile uçtan uca API testleri
  frontend/
    src/
      api.js            ← backend'e fetch çağrıları
      App.jsx
      components/        ← Sidebar, MetricCard, DataTable
      screens/            ← Upload, Segments, CLTV, Churn, Recommendations, WindowSearch
```

## Tanıtım sayfası ve demo

Site bir tanıtım sayfasıyla açılır: ürünün ne yaptığı, kullanılan modeller,
gerçek veride ölçülen sonuçlar ve nasıl çalıştığı. "Demo veriyle dene"
butonu, `backend/app/demo_data.py` içinde üretilen 600 müşterilik, bir yıllık
sentetik bir mağaza verisiyle tüm ekranları açar — gerçek müşteri verisi
repoya hiç girmez.

Demo veri rastgele değil, içine gerçek davranış yapısı yerleştirilmiştir
(sadık / düzenli / ara sıra / giderek kopan / tek seferlik müşteri tipleri,
birlikte alınan ürün grupları). Bu sayede modeller demoda da anlamlı sonuç
verir: churn ROC AUC ≈ 0,82, CLTV baseline'a göre ≈ %27 iyileşme, FP-Growth
planlanan ürün gruplarını bulur.

Tanıtım sayfası açılır açılmaz backend'e bir `health` isteği gönderir; Render
ücretsiz katmanında uyuyan sunucu, ziyaretçi sayfayı okurken uyanmaya başlar.

## Görselleştirme ve otomatik CRM raporu

Grafik seçimleri Claus Wilke'nin *Fundamentals of Data Visualization*
kitabına dayanır; her grafik başlığı neyin çizildiğini değil, grafiğin
söylediği bulguyu yazar.

| Ekran | Soru | Grafik |
|---|---|---|
| Segmentasyon | Hangi grup ne kadar büyük, ne kadar değerli? | Sıralı yatay çubuk, segment profili ısı haritası, seçili segmenti vurgulayan dağılım grafiği |
| CLTV | Değer kimde toplanıyor? | Pareto (birikimli pay) eğrisi, tahmini değer histogramı |
| Churn | Kim gitmek üzere, kimi kurtarmalı? | Sıralı risk grupları için %100 yığılmış çubuk, olasılık histogramı, risk × geçmiş harcama matrisi + geri kazanım listesi |
| Ürün önerisi | Ne önerilmeli, hangi eşleşme güçleniyor? | Lift / benzerlik çubuğu, dönem başı ile sonunu karşılaştıran slopegraph |
| Pencere araması | Hangi gözlem/tahmin penceresi daha iyi? | İki ısı haritası |

Pasta grafik kullanılmıyor: segment sayısı 6–10 arasında ve sıralı risk
grupları için yığılmış çubuk sırayı daha iyi korur. Slopegraph, Wilke'nin
tanımına uygun olarak az sayıda öğenin (en çok birlikte alınan 8 ürün) iki
dönemdeki değerini karşılaştırmak için kullanılır. Renk rolleri
`frontend/src/charts/theme.js` içinde tek yerde; kategorik çiftler renk
körlüğü kontrolünden geçirildi.

**CRM raporu:** CLTV ve churn ekranlarına bakıldıktan sonra rapor arka planda
kendiliğinden hazırlanır ve üst çubukta "CRM raporunuz hazır" görünür. Rapor,
ekranlarda seçilen ayarları (segment sayısı, CLTV yaklaşımı) kullanır ve
modelleri yeniden eğitmez. İçerik: yönetici özeti, genel görünüm, segmentler
ve segment bazında önerilen aksiyonlar, müşteri değeri, churn riski, öncelikli
geri kazanım listesi, ürün önerileri, model kalitesi ve yöntem.

Çıktılar: tek dosyalık HTML (grafikler gömülü, internetsiz açılır), tarayıcıdan
**PDF olarak kaydet** (A4 yazdırma stili) ve **Excel** (özet, segmentler +
aksiyonlar, tüm müşterilerin skorları, geri kazanım listesi, ürün
birliktelikleri). Uç noktalar: `GET /api/report`, `GET /api/report.xlsx`.

## Neden bu mimari

- **Backend hiçbir iş mantığı içermiyor** — her route `analyzewise_crm`
  paketindeki fonksiyonları çağırıp sonucu JSON'a çeviriyor. Streamlit
  sürümüyle aynı davranış garanti.
- **In-memory oturum deposu** (`app/store.py`): dosya yüklendiğinde bir
  `session_id` üretilir, sonraki tüm istekler bu id ile veriye ve
  hesaplanmış sonuç cache'ine erişir. Tek process, kalıcılık yok — yerel
  kullanım için yeterli. Çok kullanıcılı bir production'a taşınacaksa
  Redis/kalıcı bir job kuyruğuna geçirilmesi gerekir (arayüz küçük
  tutuldu, bu geçiş kolay olsun diye).
- **CORS şu an `allow_origins=["*"]`** — yerel geliştirme için. Gerçek bir
  deploy öncesi frontend'in gerçek origin'iyle daraltılmalı.

## Kurulum ve çalıştırma

### Backend

```bash
cd backend
pip install -r requirements-dev.txt
# CrmData.xlsx'inizi backend/data/ altına koyabilirsiniz (opsiyonel — frontend
# üzerinden de dosya yükleyebilirsiniz)
uvicorn app.main:app --reload --port 8000
```

Test: `pytest -v` (12 test, ~50 saniye — model eğitimi içerdiği için).

### Frontend

```bash
cd frontend
npm install
cp .env.example .env   # VITE_API_BASE_URL varsayılanı http://localhost:8000
npm run dev
```

Tarayıcıda `http://localhost:5173` açılır. Sol menüden CRM dosyanızı
yükleyip segmentasyon/CLTV/churn/ürün önerisi ekranlarına geçebilirsiniz.

## API uç noktaları

| Method | Path | Açıklama |
|---|---|---|
| POST | `/api/upload` | Dosya yükle, `session_id` döner |
| POST | `/api/demo` | Dahili sentetik demo veriyle oturum başlatır (dosya yüklemeden deneme) |
| GET | `/api/value-risk` | Churn olasılığı × geçmiş harcama, dört bölge ve öncelikli geri kazanım listesi |
| GET | `/api/recommendations/trend` | Bir ürünle birlikte alınma oranlarının dönem başı / sonu karşılaştırması (slopegraph) |
| GET | `/api/report` | Otomatik CRM raporu (HTML) |
| GET | `/api/report.xlsx` | Rapor listeleri (Excel) |
| GET | `/api/overview` | KPI özeti + aylık gelir/işlem/yeni müşteri trendi (hızlı, model eğitmiyor) |
| GET | `/api/segments` | K-Means segmentasyon (`k`, `auto` parametreleri) |
| GET | `/api/cltv` | CLTV tahmini (`approach=single\|hurdle`) |
| GET | `/api/cltv/evaluate` | CLTV modeli held-out metrikleri |
| GET | `/api/churn` | Churn tahmini |
| GET | `/api/churn/evaluate` | Churn modeli held-out metrikleri |
| GET | `/api/products` | Ürün no listesi |
| GET | `/api/recommendations` | Ürün önerisi (`method=fpgrowth\|cf`) |
| GET | `/api/windows/search` | Gözlem/tahmin penceresi taraması |
| DELETE | `/api/sessions/{id}` | Oturumu ve önbelleğini sil |

## Canlıya alma

**Backend** (FastAPI + model eğitimi içerdiği için istekler onlarca saniye
sürebilir — bu yüzden **serverless değil, sürekli çalışan bir host**
gerekir: Railway, Render, Fly.io gibi. Vercel/Netlify serverless fonksiyon
zaman aşımları (~10sn) burada yetmez).

1. Railway/Render'da "New Project" → GitHub reponuzu bağlayın, **root
   directory: `backend`** seçin. `Dockerfile` otomatik algılanır.
2. Ortam değişkeni ekleyin: `ALLOWED_ORIGINS=https://<frontend-domaininiz>`
   (frontend'i deploy ettikten sonra domaini öğrenip buraya girin;
   birden fazla origin'i virgülle ayırabilirsiniz).
3. Deploy sonrası verdiği URL'i not edin (ör. `https://analyzewise-api.up.railway.app`).

**Frontend** (Vercel — Vite projelerini otomatik algılar):

1. Vercel'de "New Project" → GitHub reponuzu bağlayın, **root directory:
   `frontend`** seçin.
2. Ortam değişkeni ekleyin: `VITE_API_BASE_URL=https://<backend-url>` (yukarıda
   not ettiğiniz backend URL'i).
3. Deploy edin.

Backend'deki `ALLOWED_ORIGINS`'i frontend'in gerçek Vercel domainiyle
güncelleyip yeniden deploy etmeyi unutmayın (aksi halde CORS hatası alırsınız).

## GitHub'a yükleme

```bash
git init
git add .
git commit -m "AnalyzeWise CRM — Faz 3 (React + FastAPI)"
git branch -M main
git remote add origin https://github.com/<kullanici-adiniz>/<repo-adi>.git
git push -u origin main
```

(GitHub'da önce boş bir repo oluşturmanız gerekir — README/license eklemeden,
zaten bu repoda var.)



Faz 3.3 itibarıyla arayüz, gerçek CRM ürünlerinde (HubSpot, Salesforce, Zoho
tarzı) alışılmış modern SaaS diline çevrildi: açık (light) tema, beyaz kartlar
+ ince gölge, indigo (#4F46E5) birincil renk, Inter tipografi, ikonlu sidebar
navigasyonu + üstte bağlam çubuğu (topbar). Grafik türleri: pasta/donut
(segment ve risk dağılımı — Segmentasyon ve Churn ekranlarında, dilime
tıklayarak filtreleme yapılabiliyor), çizgi grafik (aylık gelir trendi —
Genel Bakış ekranı), sütun grafik (aylık işlem sayısı, yeni müşteri
kazanımı). Yeni **Genel Bakış** ekranı, dosya yüklendikten sonra varsayılan
iniş sayfası — KPI kartları (toplam müşteri, gelir, işlem, ortalama sipariş
değeri) + trend grafikleri, model eğitimi gerektirmediği için anında açılıyor
(`GET /api/overview`, sadece agregasyon).
