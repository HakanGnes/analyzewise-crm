"""Kendi CRM verinizle model performansını (ROC AUC / MAE) ve en iyi
hiperparametreleri hızlıca kontrol edin.

Kullanım:
    python scripts/check_model_quality.py data/CrmData.xlsx
    python scripts/check_model_quality.py path/to/kendi_verin.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analyzewise_crm import DEFAULT_CONFIG, load_transactions
from analyzewise_crm.churn import build_churn_training_set, evaluate_churn_model
from analyzewise_crm.cltv_ml import build_cltv_training_set, evaluate_cltv_hurdle_model, evaluate_cltv_model


def main(path: str) -> None:
    raw_df = load_transactions(path, DEFAULT_CONFIG)
    print(f"Veri: {path} — {len(raw_df)} satır")
    print()

    print("Churn modeli için hiperparametre araması çalışıyor (RandomizedSearchCV, GroupKFold)...")
    churn_features = build_churn_training_set(raw_df, DEFAULT_CONFIG)
    churn_metrics = evaluate_churn_model(churn_features)
    print("=== Churn modeli ===")
    print(f"  Eğitim satırı (rolling snapshot dahil): {len(churn_features)}")
    print(f"  Held-out ROC AUC: {churn_metrics['roc_auc']:.3f}  (arama sırasında CV: {churn_metrics['cv_roc_auc']:.3f})")
    print(f"  Test seti boyutu: {churn_metrics['n_test']}")
    print(f"  Pozitif (churn) oranı: %{churn_metrics['positive_rate'] * 100:.1f}")
    print(f"  En iyi hiperparametreler: {churn_metrics['best_params']}")
    print(
        "  Yorum: 0.5 = rastgeleden farksız, 0.6-0.7 = zayıf ama kullanılabilir, "
        "0.7-0.85 = iyi, >0.95 = büyük ihtimalle veri sızıntısı var, şüphelenin"
    )
    print()

    print("CLTV modeli için hiperparametre araması çalışıyor (RandomizedSearchCV, GroupKFold)...")
    cltv_features = build_cltv_training_set(raw_df, DEFAULT_CONFIG)
    cltv_metrics = evaluate_cltv_model(cltv_features)
    print("=== CLTV modeli ===")
    print(f"  Eğitim satırı (rolling snapshot dahil): {len(cltv_features)}")
    print(f"  Held-out MAE: {cltv_metrics['mae']:.2f}  (arama sırasında CV: {cltv_metrics['cv_mae']:.2f})")
    print(f"  Naive baseline MAE (herkese ortalamayı tahmin et): {cltv_metrics['baseline_mae']:.2f}")
    print(f"  Baseline'a göre iyileşme: %{cltv_metrics['improvement_over_baseline'] * 100:.1f}")
    print(f"  Ortalama gerçek gelecek harcama: {cltv_metrics['mean_future_spend']:.2f}")
    print(f"  Test seti boyutu: {cltv_metrics['n_test']}")
    print(f"  En iyi hiperparametreler: {cltv_metrics['best_params']}")
    print(
        "  Yorum: baseline'a göre iyileşme %20'nin altındaysa model çoğunlukla "
        "'ortalamayı tahmin et' kadar bilgi veriyor demektir — özellik/hiperparametre "
        "iyileştirmesi gerekir"
    )
    print()

    hurdle_metrics = evaluate_cltv_hurdle_model(cltv_features)
    print("=== CLTV modeli — iki aşamalı (hurdle) karşılaştırması ===")
    print(f"  Harcaması sıfır olan satır oranı: %{hurdle_metrics['zero_share'] * 100:.1f}")
    print(f"  Hurdle MAE: {hurdle_metrics['mae']:.2f}  (tek aşamalı: {cltv_metrics['mae']:.2f})")
    print(f"  Hurdle baseline'a göre iyileşme: %{hurdle_metrics['improvement_over_baseline'] * 100:.1f}")
    print(
        "  Yorum: sıfır oranı yüksekse (örn. >%40) hurdle genelde tek aşamalıyı geçer. "
        "Hangisi daha düşük MAE veriyorsa Streamlit'te onu seçin."
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Kullanım: python scripts/check_model_quality.py <veri_dosyasi.xlsx|csv>")
        sys.exit(1)
    main(sys.argv[1])
