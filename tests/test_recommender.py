import pandas as pd

from analyzewise_crm.config import AnalysisConfig
from analyzewise_crm.recommender import (
    collaborative_filtering_recommend,
    compute_association_rules,
    recommend_products,
)


def _basket_transactions() -> pd.DataFrame:
    """Bread (1) and butter (2) are always bought together by many
    customers; milk (3) is independent. Wide enough support/confidence
    to survive FP-Growth's default thresholds.
    """
    rows = []
    txn = 1
    for customer in range(1, 11):
        for _ in range(4):
            rows.append({"TransactionNo": f"T{txn}", "ProductNo": 1, "ProductName": "Bread",
                         "Quantity": 1, "Price": 5, "Date": "01/01/2020", "Country": "France",
                         "CustomerNo": customer})
            rows.append({"TransactionNo": f"T{txn}", "ProductNo": 2, "ProductName": "Butter",
                         "Quantity": 1, "Price": 3, "Date": "01/01/2020", "Country": "France",
                         "CustomerNo": customer})
            txn += 1
    for customer in range(1, 4):
        rows.append({"TransactionNo": f"T{txn}", "ProductNo": 3, "ProductName": "Milk",
                     "Quantity": 1, "Price": 2, "Date": "01/01/2020", "Country": "France",
                     "CustomerNo": customer})
        txn += 1
    return pd.DataFrame(rows)


def test_fpgrowth_recommend_finds_frequently_paired_item():
    df = _basket_transactions()
    config = AnalysisConfig(arl_min_support=0.1, arl_min_threshold=0.1)
    rules = compute_association_rules(df, config=config, country="France")
    recommendations = recommend_products(rules, product_id=1, top_n=5)
    assert 2 in recommendations


def test_fpgrowth_recommend_returns_empty_list_when_no_rules_match():
    df = _basket_transactions()
    config = AnalysisConfig(arl_min_support=0.1, arl_min_threshold=0.1)
    rules = compute_association_rules(df, config=config, country="France")
    recommendations = recommend_products(rules, product_id=999, top_n=5)
    assert recommendations == []


def test_collaborative_filtering_recommends_similar_products():
    df = _basket_transactions()
    recs = collaborative_filtering_recommend(df, product_id=1, top_n=5)
    assert 2 in recs


def test_collaborative_filtering_unknown_product_returns_empty():
    df = _basket_transactions()
    recs = collaborative_filtering_recommend(df, product_id=999, top_n=5)
    assert recs == []
