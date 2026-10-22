"""Cached analysis layer shared by the JSON endpoints and the CRM report.

Each function computes one analysis for a session the first time it's
asked for and keeps the resulting DataFrame (or metrics dict) in the
session cache. The screens and the report therefore read the exact same
numbers, and generating a report after browsing the screens doesn't
retrain any model.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from analyzewise_crm import DEFAULT_CONFIG
from analyzewise_crm.churn import build_churn_training_set, evaluate_churn_model, predict_churn
from analyzewise_crm.cltv_ml import (
    build_cltv_training_set,
    evaluate_cltv_hurdle_model,
    evaluate_cltv_model,
    predict_cltv,
    predict_cltv_hurdle,
)
from analyzewise_crm.recommender import compute_association_rules
from analyzewise_crm.segmentation import cluster_customers

from .store import Session, store

COLS = DEFAULT_CONFIG.columns

# Thresholds for the risk × value view. A customer is "high risk" from a
# 50% churn probability (the boundary between the medium and high risk
# bands), and "high value" in the top quarter of predicted CLTV.
HIGH_RISK = 0.5
HIGH_VALUE_QUANTILE = 0.75


def _cached(session_id: str, key: str, compute):
    value = store.cache_get(session_id, key)
    if value is None:
        value = compute()
        store.cache_set(session_id, key, value)
    return value


def segments(session_id: str, session: Session, k: Optional[int], auto: bool) -> pd.DataFrame:
    kmeans_k = None if auto else (k or 6)
    return _cached(
        session_id,
        f"df:segments:{kmeans_k}:{auto}",
        lambda: cluster_customers(session.raw_df, DEFAULT_CONFIG, k=kmeans_k),
    )


def cltv(session_id: str, session: Session, approach: str) -> pd.DataFrame:
    fn = predict_cltv_hurdle if approach == "hurdle" else predict_cltv
    return _cached(session_id, f"df:cltv:{approach}", lambda: fn(session.raw_df, DEFAULT_CONFIG))


def cltv_metrics(session_id: str, session: Session, approach: str) -> dict:
    def compute():
        features = build_cltv_training_set(session.raw_df, DEFAULT_CONFIG)
        return evaluate_cltv_hurdle_model(features) if approach == "hurdle" else evaluate_cltv_model(features)

    return _cached(session_id, f"metrics:cltv:{approach}", compute)


def churn(session_id: str, session: Session) -> pd.DataFrame:
    return _cached(session_id, "df:churn", lambda: predict_churn(session.raw_df, DEFAULT_CONFIG))


def churn_metrics(session_id: str, session: Session) -> dict:
    return _cached(
        session_id,
        "metrics:churn",
        lambda: evaluate_churn_model(build_churn_training_set(session.raw_df, DEFAULT_CONFIG)),
    )


def rules(session_id: str, session: Session) -> pd.DataFrame:
    return _cached(session_id, "df:rules", lambda: compute_association_rules(session.raw_df, DEFAULT_CONFIG))


def product_names(session: Session) -> dict:
    if COLS.product_id not in session.raw_df.columns or COLS.product_name not in session.raw_df.columns:
        return {}
    pairs = session.raw_df[[COLS.product_id, COLS.product_name]].dropna().drop_duplicates(COLS.product_id)
    return dict(zip(pairs[COLS.product_id], pairs[COLS.product_name].astype(str)))


def historical_spend(session: Session) -> pd.Series:
    """Total spend per customer over the whole uploaded history."""
    df = session.raw_df
    spend = (df[COLS.quantity] * df[COLS.price]).groupby(df[COLS.customer_id]).sum()
    return spend.rename("historical_spend")


def value_risk(session_id: str, session: Session, approach: str) -> pd.DataFrame:
    """One row per customer: churn probability next to historical spend,
    with a quadrant label. The "değerli, riskte" quadrant (spent a lot,
    likely to leave) is the CRM win-back list.

    The value axis is deliberately *past* spend, not predicted CLTV:
    predicted CLTV already prices in the chance of leaving, so a customer
    likely to churn always has a low prediction and the high-value /
    high-risk corner would be empty by construction.
    """

    def compute():
        risk = churn(session_id, session)[["churn_probability", "recency", "frequency"]]
        value = cltv(session_id, session, approach)[["predicted_cltv"]]
        joined = risk.join(value, how="inner").join(historical_spend(session), how="left")
        joined["historical_spend"] = joined["historical_spend"].fillna(0.0)
        value_cut = float(joined["historical_spend"].quantile(HIGH_VALUE_QUANTILE))
        high_value = joined["historical_spend"] >= value_cut
        high_risk = joined["churn_probability"] >= HIGH_RISK
        joined["quadrant"] = "düşük değer, düşük risk"
        joined.loc[high_value & ~high_risk, "quadrant"] = "değerli, güvende"
        joined.loc[~high_value & high_risk, "quadrant"] = "düşük değer, riskte"
        joined.loc[high_value & high_risk, "quadrant"] = "değerli, riskte"
        joined.attrs["value_cut"] = value_cut
        return joined

    return _cached(session_id, f"df:value_risk:{approach}", compute)
