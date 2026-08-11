"""Product recommendation.

Two modern strategies, both replacing the old Apriori-based association
rules:

- FP-Growth: same association-rule idea (products frequently bought
  together) but a much faster algorithm than Apriori (no candidate-set
  explosion) — a straightforward drop-in upgrade, from mlxtend.
- Item-based collaborative filtering: cosine similarity over the
  customer-product matrix. Can surface products that were never bought
  in the same basket but are bought by similar customers, which
  co-occurrence rules structurally cannot.
"""
from __future__ import annotations

from typing import List, Optional

import pandas as pd
from mlxtend.frequent_patterns import association_rules, fpgrowth
from sklearn.metrics.pairwise import cosine_similarity

from .config import AnalysisConfig, DEFAULT_CONFIG


def _invoice_product_matrix(df: pd.DataFrame, config: AnalysisConfig, by_id: bool = True) -> pd.DataFrame:
    cols = config.columns
    key = cols.product_id if by_id else cols.product_name
    matrix = df.groupby([cols.transaction_id, key])[cols.quantity].sum().unstack().fillna(0)
    return matrix.gt(0)


def compute_association_rules(
    raw_df: pd.DataFrame,
    config: AnalysisConfig = DEFAULT_CONFIG,
    country: Optional[str] = None,
    by_id: bool = True,
) -> pd.DataFrame:
    """FP-Growth based association rules (replaces Apriori). Country
    filter and support/threshold come from config, not hardcoded.
    """
    cols = config.columns
    df = raw_df
    country = country if country is not None else config.arl_country_filter
    if country and cols.country in df.columns:
        df = df[df[cols.country] == country]

    matrix = _invoice_product_matrix(df, config, by_id=by_id)
    frequent_itemsets = fpgrowth(matrix, min_support=config.arl_min_support, use_colnames=True)
    return association_rules(frequent_itemsets, metric="support", min_threshold=config.arl_min_threshold)


def recommend_products(rules: pd.DataFrame, product_id, top_n: int = 5) -> List:
    """Recommend up to top_n products frequently bought with product_id,
    ranked by lift, from FP-Growth-derived rules. Deduplicated.
    """
    if rules.empty:
        return []

    sorted_rules = rules.sort_values("lift", ascending=False)
    recommendations: List = []
    for antecedents, consequents in zip(sorted_rules["antecedents"], sorted_rules["consequents"]):
        if product_id in antecedents:
            for item in consequents:
                if item not in recommendations:
                    recommendations.append(item)
                if len(recommendations) >= top_n:
                    return recommendations
    return recommendations


def build_customer_product_matrix(raw_df: pd.DataFrame, config: AnalysisConfig = DEFAULT_CONFIG, by_id: bool = True) -> pd.DataFrame:
    cols = config.columns
    key = cols.product_id if by_id else cols.product_name
    return raw_df.groupby([cols.customer_id, key])[cols.quantity].sum().unstack().fillna(0)


def collaborative_filtering_recommend(
    raw_df: pd.DataFrame,
    config: AnalysisConfig = DEFAULT_CONFIG,
    product_id=None,
    top_n: int = 5,
    by_id: bool = True,
) -> List:
    """Item-based collaborative filtering: cosine similarity between
    products over the customer-product purchase matrix. Products bought
    by a similar set of customers are recommended, even if they were
    never purchased in the same basket.
    """
    matrix = build_customer_product_matrix(raw_df, config, by_id=by_id)
    if product_id not in matrix.columns:
        return []

    similarities = cosine_similarity(matrix.T)
    sim_df = pd.DataFrame(similarities, index=matrix.columns, columns=matrix.columns)
    scores = sim_df[product_id].drop(index=product_id).sort_values(ascending=False)
    return scores[scores > 0].head(top_n).index.tolist()
