"""AnalyzeWise-CRM analiz çekirdeği.

Faz 2 itibarıyla varsayılan pipeline tamamen yeni algoritmalara geçti:

- Segmentasyon: quintile+regex RFM yerine K-Means kümeleme (segmentation.py)
- CLTV: BG/NBD + Gamma-Gamma yerine XGBoost regresyon (cltv_ml.py)
- Churn: nüfus ortalaması churn_rate yerine müşteri bazlı XGBoost sınıflandırıcı (churn.py)
- Ürün önerisi: Apriori yerine FP-Growth + item-based collaborative filtering (recommender.py)

Eski BG/NBD ve kural-tabanlı RFM fonksiyonları (rfm.py / cltv.py) referans
amaçlı dosyada duruyor ama artık __init__ üzerinden dışa açılmıyor.
"""
from .churn import build_churn_training_set, predict_churn, train_churn_model
from .cltv_ml import build_cltv_training_set, predict_cltv, train_cltv_model
from .config import DEFAULT_CONFIG, AnalysisConfig, ColumnMap
from .data import load_transactions, prepare_transactions, resolve_analysis_date
from .features import build_customer_features, split_calibration_holdout
from .model_selection import search_windows
from .recommender import (
    collaborative_filtering_recommend,
    compute_association_rules,
    recommend_products,
)
from .segmentation import cluster_customers, find_optimal_k

__all__ = [
    "AnalysisConfig",
    "ColumnMap",
    "DEFAULT_CONFIG",
    "load_transactions",
    "prepare_transactions",
    "resolve_analysis_date",
    "build_customer_features",
    "split_calibration_holdout",
    "cluster_customers",
    "find_optimal_k",
    "predict_cltv",
    "build_cltv_training_set",
    "train_cltv_model",
    "predict_churn",
    "build_churn_training_set",
    "train_churn_model",
    "compute_association_rules",
    "recommend_products",
    "collaborative_filtering_recommend",
    "search_windows",
]
