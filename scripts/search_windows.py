"""Gözlem/tahmin penceresi (observation_days / prediction_days) kombinasyonlarını
tarayıp hangisinin daha iyi churn AUC / CLTV MAE verdiğini karşılaştırın.

Kullanım:
    python scripts/search_windows.py data/CrmData.xlsx

Not: bu hızlı bir tarama — sabit (aranmamış) hiperparametrelerle çalışır.
En iyi pencereyi bulduktan sonra, o pencereyi config.observation_days /
config.prediction_days olarak ayarlayıp check_model_quality.py ile tam
(hiperparametre aranmış) sayıları alın.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analyzewise_crm import DEFAULT_CONFIG, load_transactions, search_windows


def main(path: str) -> None:
    raw_df = load_transactions(path, DEFAULT_CONFIG)
    print(f"Veri: {path} — {len(raw_df)} satır")
    print("Pencere kombinasyonları taranıyor (bu birkaç dakika sürebilir)...")
    print()

    results = search_windows(raw_df, DEFAULT_CONFIG)
    with __import__("pandas").option_context("display.float_format", "{:.3f}".format):
        print(results.to_string(index=False))

    print()
    best = results.iloc[0]
    print(
        f"En yüksek churn AUC: observation_days={int(best['observation_days'])}, "
        f"prediction_days={int(best['prediction_days'])} (AUC={best['churn_auc']:.3f})"
    )
    print(
        "Bu değerleri kullanmak için AnalysisConfig(observation_days=..., prediction_days=...) "
        "ile kendi config'inizi oluşturup DEFAULT_CONFIG yerine geçirin."
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Kullanım: python scripts/search_windows.py <veri_dosyasi.xlsx|csv>")
        sys.exit(1)
    main(sys.argv[1])
