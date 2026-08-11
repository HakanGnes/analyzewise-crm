"""AnalyzeWise CRM - Streamlit arayüzü (Faz 2.1: rolling-window modeller +
kontrol edilebilir segment sayısı + model performans metrikleri).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from analyzewise_crm import (
    DEFAULT_CONFIG,
    cluster_customers,
    collaborative_filtering_recommend,
    compute_association_rules,
    load_transactions,
    predict_churn,
    predict_cltv,
    recommend_products,
)
from analyzewise_crm.churn import build_churn_training_set, evaluate_churn_model
from analyzewise_crm.cltv_ml import (
    build_cltv_training_set,
    evaluate_cltv_hurdle_model,
    evaluate_cltv_model,
    predict_cltv_hurdle,
)

st.set_page_config(page_title="AnalyzeWise CRM", page_icon=":bar_chart:", layout="wide")

DEMO_DATA_PATH = Path(__file__).parent / "data" / "CrmData.xlsx"


# --- Cache'lenmiş hesaplama katmanı -------------------------------------

@st.cache_data(show_spinner="Müşteriler K-Means ile segmentleniyor...")
def _cached_segments(df: pd.DataFrame, k: int | None) -> pd.DataFrame:
    return cluster_customers(df, DEFAULT_CONFIG, k=k)


@st.cache_data(show_spinner="XGBoost CLTV modeli eğitiliyor...")
def _cached_cltv(df: pd.DataFrame) -> pd.DataFrame:
    return predict_cltv(df, DEFAULT_CONFIG)


@st.cache_data(show_spinner="CLTV modeli değerlendiriliyor (held-out MAE)...")
def _cached_cltv_eval(df: pd.DataFrame) -> dict:
    features = build_cltv_training_set(df, DEFAULT_CONFIG)
    return evaluate_cltv_model(features)


@st.cache_data(show_spinner="İki aşamalı (hurdle) CLTV modeli değerlendiriliyor...")
def _cached_cltv_hurdle_eval(df: pd.DataFrame) -> dict:
    features = build_cltv_training_set(df, DEFAULT_CONFIG)
    return evaluate_cltv_hurdle_model(features)


@st.cache_data(show_spinner="İki aşamalı (hurdle) CLTV modeli eğitiliyor...")
def _cached_cltv_hurdle(df: pd.DataFrame) -> pd.DataFrame:
    return predict_cltv_hurdle(df, DEFAULT_CONFIG)


@st.cache_data(show_spinner="Churn modeli eğitiliyor...")
def _cached_churn(df: pd.DataFrame) -> pd.DataFrame:
    return predict_churn(df, DEFAULT_CONFIG)


@st.cache_data(show_spinner="Churn modeli değerlendiriliyor (held-out ROC AUC)...")
def _cached_churn_eval(df: pd.DataFrame) -> dict:
    features = build_churn_training_set(df, DEFAULT_CONFIG)
    return evaluate_churn_model(features)


@st.cache_data(show_spinner="FP-Growth kuralları çıkarılıyor...")
def _cached_rules(df: pd.DataFrame) -> pd.DataFrame:
    return compute_association_rules(df, DEFAULT_CONFIG)


# --- Veri kaynağı --------------------------------------------------------

st.sidebar.title("Analiz Menüsü")

with st.sidebar.expander("Veri Kaynağı", expanded=True):
    uploaded = st.file_uploader("Kendi CRM verinizi yükleyin (.xlsx / .csv)", type=["xlsx", "xls", "csv"])
    use_demo = st.checkbox("Örnek demo veriyi kullan", value=uploaded is None)

if uploaded is not None and not use_demo:
    raw_df = load_transactions(uploaded, DEFAULT_CONFIG)
elif DEMO_DATA_PATH.exists():
    raw_df = load_transactions(DEMO_DATA_PATH, DEFAULT_CONFIG)
else:
    st.sidebar.warning("Demo veri bulunamadı, lütfen bir dosya yükleyin.")
    st.stop()

secenek = st.sidebar.radio(
    "Lütfen bir analiz seçin:",
    (
        "Giriş / Hakkında",
        "Müşteri Segmentasyonu (K-Means)",
        "CLTV Tahmini (XGBoost)",
        "Churn Tahmini (XGBoost)",
        "Ürün Önerisi (FP-Growth + CF)",
    ),
)

# --- Giriş -----------------------------------------------------------------
if secenek == "Giriş / Hakkında":
    st.title("AnalyzeWise CRM")
    st.markdown(
        """
        Küçük ve orta ölçekli işletmeler için müşteri ilişkileri yönetimi (CRM)
        süreçlerini analiz etmeye ve veri odaklı stratejik kararlar almaya
        yardımcı olur.

        **Faz 2 — modern algoritmalar**
        - **Müşteri Segmentasyonu:** K-Means kümeleme; segment sayısını siz belirleyin ya da elbow yöntemiyle otomatik seçilsin.
        - **CLTV Tahmini:** XGBoost regresyon, rolling-window (kayan pencere) eğitimle — held-out MAE raporlanır.
        - **Churn Tahmini:** her müşteri için ayrı churn olasılığı, rolling-window eğitimle — held-out ROC AUC raporlanır.
        - **Ürün Önerisi:** FP-Growth (hızlı birliktelik kuralları) + item-based collaborative filtering.

        CLTV ve churn modelleri artık tek bir sabit tarih bölmesi yerine, veri
        boyunca kayan bir pencereyle (rolling window) eğitiliyor — bu sayede
        model, canlı skorlama anında gördüğü müşteri davranışlarının aynısını
        eğitim sırasında da görmüş oluyor.
        """
    )
    st.info("Sol menüden analiz türünü seçerek uygulamayı kullanmaya başlayabilirsiniz.")

# --- Müşteri Segmentasyonu (K-Means) ---------------------------------------
elif secenek == "Müşteri Segmentasyonu (K-Means)":
    st.header("📈 Müşteri Segmentasyonu — K-Means")

    col_a, col_b = st.columns([2, 1])
    with col_b:
        otomatik = st.checkbox("Segment sayısını otomatik seç (elbow yöntemi)", value=False)
    with col_a:
        secili_k = st.slider("Segment sayısı", min_value=2, max_value=10, value=6, disabled=otomatik)

    seg_df = _cached_segments(raw_df, None if otomatik else secili_k).reset_index()

    secili_segment = st.selectbox("Segment Seçiniz:", seg_df["segment"].unique())
    filtreli = seg_df[seg_df["segment"] == secili_segment][DEFAULT_CONFIG.columns.customer_id]
    st.write(f"**{secili_segment}** segmentindeki müşteri numaraları (**{len(filtreli)}** müşteri):")
    st.write(list(filtreli))

    segment_sayilari = seg_df["segment"].value_counts()
    st.subheader("Segment Dağılımı")
    st.bar_chart(segment_sayilari)

    st.subheader("Segment Merkezleri (Ortalama Recency / Frequency / Monetary)")
    st.dataframe(seg_df.groupby("segment")[["recency", "frequency", "monetary"]].mean(), use_container_width=True)

# --- CLTV Tahmini (XGBoost) -------------------------------------------------
elif secenek == "CLTV Tahmini (XGBoost)":
    st.header("💡 CLTV Tahmini — XGBoost Regresyon")

    yaklasim = st.radio(
        "Yaklaşım seçin:",
        ("Tek aşamalı (doğrudan regresyon)", "İki aşamalı — hurdle (churn olasılığı × koşullu harcama)"),
        index=0,
        help="Harcama hedefi 'sıfır ağırlıklı' ise (çoğu müşteri hiç geri dönmüyorsa) "
        "hurdle yaklaşımı bazen daha iyi sonuç verir — ama bu iki yaklaşım genelde "
        "birbirine çok yakın çıkar, ikisini de deneyip held-out MAE'si düşük olanı seçin.",
    )

    if yaklasim.startswith("Tek"):
        metrics = _cached_cltv_eval(raw_df)
        st.caption(
            f"Held-out MAE: **{metrics['mae']:.2f}** vs. naive baseline (ortalamayı tahmin et): "
            f"**{metrics['baseline_mae']:.2f}** · baseline'a göre iyileşme: "
            f"**%{metrics['improvement_over_baseline']*100:.1f}** · test seti: {metrics['n_test']} satır"
        )
        with st.expander("En iyi hiperparametreler (RandomizedSearchCV, GroupKFold)"):
            st.json(metrics["best_params"])
            st.caption(f"CV MAE (arama sırasında): {metrics['cv_mae']:.2f}")
        cltv_df = _cached_cltv(raw_df).reset_index()
    else:
        metrics = _cached_cltv_hurdle_eval(raw_df)
        st.caption(
            f"Held-out MAE: **{metrics['mae']:.2f}** vs. naive baseline: **{metrics['baseline_mae']:.2f}** · "
            f"baseline'a göre iyileşme: **%{metrics['improvement_over_baseline']*100:.1f}** · "
            f"harcaması sıfır olan satır oranı: %{metrics['zero_share']*100:.1f} · test seti: {metrics['n_test']} satır"
        )
        cltv_df = _cached_cltv_hurdle(raw_df).reset_index()

    secili_segment = st.selectbox("Segment Seçiniz:", cltv_df["segment"].unique())
    filtreli = cltv_df[cltv_df["segment"] == secili_segment]

    st.dataframe(
        filtreli[[DEFAULT_CONFIG.columns.customer_id, "predicted_cltv", "frequency", "monetary", "segment"]]
        .rename(columns={
            DEFAULT_CONFIG.columns.customer_id: "Müşteri No",
            "predicted_cltv": "Tahmini CLTV",
            "frequency": "Sıklık",
            "monetary": "Toplam Harcama",
            "segment": "Segment",
        })
        .sort_values("Tahmini CLTV", ascending=False),
        use_container_width=True,
    )

    st.subheader("Segment Bazında Ortalama Tahmini CLTV")
    st.bar_chart(cltv_df.groupby("segment")["predicted_cltv"].mean())

# --- Churn Tahmini (XGBoost) -------------------------------------------------
elif secenek == "Churn Tahmini (XGBoost)":
    st.header("⚠️ Churn Tahmini — Müşteri Bazlı")

    metrics = _cached_churn_eval(raw_df)
    st.caption(
        f"Held-out ROC AUC: **{metrics['roc_auc']:.3f}** · test seti: {metrics['n_test']} satır · "
        f"pozitif (churn) oranı: %{metrics['positive_rate']*100:.1f} "
        "(0.5 = rastgeleden farksız, 1.0 = mükemmel ayrım)"
    )
    with st.expander("En iyi hiperparametreler (RandomizedSearchCV, GroupKFold)"):
        st.json(metrics["best_params"])
        st.caption(f"CV ROC AUC (arama sırasında): {metrics['cv_roc_auc']:.3f}")

    churn_df = _cached_churn(raw_df).reset_index()

    secili_risk = st.selectbox("Risk Segmenti Seçiniz:", churn_df["risk_segment"].unique())
    filtreli = churn_df[churn_df["risk_segment"] == secili_risk]

    st.dataframe(
        filtreli[[DEFAULT_CONFIG.columns.customer_id, "churn_probability", "recency", "frequency", "risk_segment"]]
        .rename(columns={
            DEFAULT_CONFIG.columns.customer_id: "Müşteri No",
            "churn_probability": "Churn Olasılığı",
            "recency": "Son Alışverişten Geçen Gün",
            "frequency": "Sıklık",
            "risk_segment": "Risk Segmenti",
        })
        .sort_values("Churn Olasılığı", ascending=False),
        use_container_width=True,
    )

    st.subheader("Risk Segmentlerine Göre Müşteri Sayısı")
    st.bar_chart(churn_df["risk_segment"].value_counts())

# --- Ürün Önerisi (FP-Growth + CF) ------------------------------------------
elif secenek == "Ürün Önerisi (FP-Growth + CF)":
    st.header("🎯 Ürün Öneri Sistemi")

    yontem = st.radio("Yöntem seçin:", ("FP-Growth (birlikte alınanlar)", "Collaborative Filtering (benzer müşteriler)"))
    secili_urun = st.selectbox("Ürün Seçiniz:", sorted(raw_df[DEFAULT_CONFIG.columns.product_id].unique()))
    onerilecek_adet = st.slider("Kaç ürün önerisi yapılacak?", 1, 10, 5)

    if st.button("Önerileri Gör"):
        if yontem.startswith("FP-Growth"):
            rules = _cached_rules(raw_df)
            oneriler = recommend_products(rules, secili_urun, onerilecek_adet)
        else:
            oneriler = collaborative_filtering_recommend(raw_df, DEFAULT_CONFIG, secili_urun, onerilecek_adet)

        if oneriler:
            st.success(f"**{secili_urun}** için önerilen ürünler ({yontem}):")
            for i, urun in enumerate(oneriler, start=1):
                st.write(f"{i}. Öneri: {urun}")
        else:
            st.warning("Bu ürün için yeterli veri/ilişki bulunamadı.")

st.markdown("---")
st.caption(":bar_chart: AnalyzeWise CRM — Faz 2.1: K-Means · XGBoost (rolling-window) · FP-Growth · Collaborative Filtering")
