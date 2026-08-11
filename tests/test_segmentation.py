from analyzewise_crm import cluster_customers, find_optimal_k
from analyzewise_crm.segmentation import FEATURE_COLUMNS, SEGMENT_NAMES


def test_cluster_customers_produces_expected_columns(synthetic_transactions):
    clustered = cluster_customers(synthetic_transactions)
    assert set(["recency", "frequency", "monetary", "cluster", "segment"]) <= set(clustered.columns)
    assert clustered["segment"].notna().all()
    assert clustered["cluster"].nunique() >= 2


def test_cluster_customers_respects_explicit_k(synthetic_transactions):
    clustered = cluster_customers(synthetic_transactions, k=3)
    assert clustered["cluster"].nunique() == 3


def test_cluster_customers_supports_full_ten_category_taxonomy(synthetic_transactions):
    clustered = cluster_customers(synthetic_transactions, k=10)
    assert clustered["cluster"].nunique() == 10
    assert clustered["segment"].nunique() == 10
    assert set(clustered["segment"].unique()) <= set(SEGMENT_NAMES)


def test_find_optimal_k_returns_value_in_range():
    import numpy as np

    rng = np.random.default_rng(0)
    X = np.vstack([rng.normal(loc=c, scale=0.3, size=(40, 2)) for c in [0, 5, 10]])
    k = find_optimal_k(X, k_range=range(2, 7))
    assert 2 <= k <= 6
