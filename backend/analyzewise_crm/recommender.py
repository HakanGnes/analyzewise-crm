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


def recommend_products_scored(rules: pd.DataFrame, product_id, top_n: int = 5) -> pd.DataFrame:
    """Same ranking as recommend_products, but keeps the evidence behind
    each suggestion: the strongest rule's lift, confidence and support.

    Returns one row per recommended product (deduplicated, best rule wins),
    sorted by lift descending.
    """
    columns = ["product", "lift", "confidence", "support"]
    if rules.empty:
        return pd.DataFrame(columns=columns)

    best: dict = {}
    for row in rules.sort_values("lift", ascending=False).itertuples():
        if product_id not in row.antecedents:
            continue
        for item in row.consequents:
            if item == product_id or item in best:
                continue
            best[item] = (float(row.lift), float(row.confidence), float(row.support))
    out = pd.DataFrame(
        [(item, *vals) for item, vals in best.items()], columns=columns
    ).sort_values("lift", ascending=False)
    return out.head(top_n).reset_index(drop=True)


def collaborative_filtering_scores(
    raw_df: pd.DataFrame,
    config: AnalysisConfig = DEFAULT_CONFIG,
    product_id=None,
    top_n: int = 5,
    by_id: bool = True,
) -> pd.DataFrame:
    """Same ranking as collaborative_filtering_recommend, returning the
    cosine similarity score next to each product."""
    columns = ["product", "similarity"]
    matrix = build_customer_product_matrix(raw_df, config, by_id=by_id)
    if product_id not in matrix.columns:
        return pd.DataFrame(columns=columns)

    target = matrix[product_id].to_numpy().reshape(1, -1)
    sims = cosine_similarity(target, matrix.T.to_numpy())[0]
    scores = pd.Series(sims, index=matrix.columns).drop(index=product_id).sort_values(ascending=False)
    scores = scores[scores > 0].head(top_n)
    return pd.DataFrame({"product": scores.index, "similarity": scores.to_numpy()})


def top_rules(rules: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Strongest single-item → single-item rules, for a report-level view
    of which products sell together (multi-item rules are harder to read)."""
    columns = ["antecedent", "consequent", "lift", "confidence", "support"]
    if rules.empty:
        return pd.DataFrame(columns=columns)
    simple = rules[(rules["antecedents"].map(len) == 1) & (rules["consequents"].map(len) == 1)].copy()
    simple["antecedent"] = simple["antecedents"].map(lambda s: next(iter(s)))
    simple["consequent"] = simple["consequents"].map(lambda s: next(iter(s)))
    # A→B and B→A share lift; keep one direction per unordered pair
    simple["pair"] = simple.apply(lambda r: tuple(sorted([r["antecedent"], r["consequent"]])), axis=1)
    simple = simple.sort_values(["lift", "confidence"], ascending=False).drop_duplicates("pair")
    return simple[columns].head(n).reset_index(drop=True)


def copurchase_trend(
    raw_df: pd.DataFrame,
    config: AnalysisConfig = DEFAULT_CONFIG,
    product_id=None,
    top_n: int = 8,
    min_baskets: int = 5,
) -> dict:
    """Paired data for a slopegraph: for the baskets that contain
    `product_id`, the share that also contained each other product, in the
    first half of the date range versus the second half.

    Same products, two periods — so a rising line means that pairing is
    gaining strength (a recommendation worth pushing), a falling one means
    it is fading. Only products seen with the anchor at least `min_baskets`
    times overall are kept, so a single co-purchase can't become a 100% line.
    """
    cols = config.columns
    empty = {"rows": [], "periods": [], "anchor_baskets": [0, 0]}
    if product_id is None or cols.product_id not in raw_df.columns:
        return empty

    df = raw_df[[cols.transaction_id, cols.product_id, cols.date]].dropna().copy()
    if config.date_format:
        df[cols.date] = pd.to_datetime(df[cols.date], format=config.date_format, errors="coerce")
    else:
        df[cols.date] = pd.to_datetime(df[cols.date], errors="coerce")
    df = df.dropna(subset=[cols.date])

    basket_dates = df.groupby(cols.transaction_id)[cols.date].min()
    lo, hi = basket_dates.min(), basket_dates.max()
    mid = lo + (hi - lo) / 2

    anchor_txns = set(df.loc[df[cols.product_id] == product_id, cols.transaction_id])
    if not anchor_txns:
        return empty
    anchor_dates = basket_dates.loc[list(anchor_txns)]
    first_txns = set(anchor_dates[anchor_dates <= mid].index)
    second_txns = set(anchor_dates[anchor_dates > mid].index)
    if not first_txns or not second_txns:
        return empty

    in_anchor = df[df[cols.transaction_id].isin(anchor_txns) & (df[cols.product_id] != product_id)]
    in_anchor = in_anchor.drop_duplicates([cols.transaction_id, cols.product_id])
    in_anchor["half"] = in_anchor[cols.transaction_id].map(lambda t: "first" if t in first_txns else "second")
    counts = in_anchor.groupby([cols.product_id, "half"]).size().unstack(fill_value=0)
    for half in ("first", "second"):
        if half not in counts.columns:
            counts[half] = 0
    counts = counts[(counts["first"] + counts["second"]) >= min_baskets]
    if counts.empty:
        return empty

    trend = pd.DataFrame(
        {
            "product": counts.index,
            "rate_first": counts["first"].to_numpy() / len(first_txns),
            "rate_second": counts["second"].to_numpy() / len(second_txns),
            "overall": (counts["first"] + counts["second"]).to_numpy() / len(anchor_txns),
        }
    ).sort_values("overall", ascending=False).head(top_n)

    return {
        "rows": trend.reset_index(drop=True),
        "periods": [
            f"{lo:%Y-%m-%d} – {mid:%Y-%m-%d}",
            f"{mid:%Y-%m-%d} – {hi:%Y-%m-%d}",
        ],
        "anchor_baskets": [len(first_txns), len(second_txns)],
    }
