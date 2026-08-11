"""Shared feature engineering for the ML-based models (segmentation,
ML-CLTV, churn).

Both cltv_ml.py and churn.py use a calibration/holdout time split:
features come from the customer's behaviour in the calibration period,
and the label (future spend, or whether they returned) comes from the
holdout period. This is the supervised-learning framing of the same idea
BG/NBD uses (recency/T/frequency) — but any customer-level feature can be
added here, and the model can learn non-linear interactions the
parametric model can't.
"""
from __future__ import annotations

from typing import Optional, Tuple

import pandas as pd

from .config import AnalysisConfig, DEFAULT_CONFIG


def split_calibration_holdout(
    df: pd.DataFrame,
    config: AnalysisConfig = DEFAULT_CONFIG,
    split_date: Optional[pd.Timestamp] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    """Split cleaned transactions into a calibration period (used to build
    features) and a holdout period (used to build labels). Defaults to
    the midpoint of the date range in the data.
    """
    cols = config.columns
    if split_date is None:
        min_d, max_d = df[cols.date].min(), df[cols.date].max()
        split_date = min_d + (max_d - min_d) / 2
    calibration = df[df[cols.date] <= split_date]
    holdout = df[df[cols.date] > split_date]
    return calibration, holdout, split_date


def build_customer_features(
    df: pd.DataFrame, config: AnalysisConfig = DEFAULT_CONFIG, as_of: Optional[pd.Timestamp] = None
) -> pd.DataFrame:
    """RFM-style feature snapshot for a period of transactions. Used as
    model input for clustering, ML-CLTV regression and churn
    classification.

    `as_of` is the reference date recency/tenure are measured against.
    Pass it explicitly when building a rolling-window snapshot (see
    iter_rolling_windows) so every snapshot's recency is measured from
    its own cutoff, not from the last transaction inside that slice —
    otherwise a customer who didn't buy near the end of the window would
    look more recent than they actually were as of the cutoff.
    """
    cols = config.columns
    if as_of is None:
        as_of = df[cols.date].max() + pd.Timedelta(days=1)

    features = df.groupby(cols.customer_id).agg(
        recency=(cols.date, lambda s: (as_of - s.max()).days),
        tenure=(cols.date, lambda s: (as_of - s.min()).days),
        frequency=(cols.transaction_id, "nunique"),
        monetary=("TotalPrice", "sum"),
        avg_order_value=("TotalPrice", "mean"),
        monetary_std=("TotalPrice", "std"),
        total_units=(cols.quantity, "sum"),
        avg_basket_size=(cols.quantity, "mean"),
    )
    features["monetary_std"] = features["monetary_std"].fillna(0.0)
    features["avg_days_between_orders"] = features["tenure"] / features["frequency"].clip(lower=1)

    # Product diversity: how many distinct products the customer has
    # bought. Optional — product_id isn't a required column, so datasets
    # without it just get 0 for every customer instead of failing.
    if cols.product_id in df.columns:
        diversity = df.groupby(cols.customer_id)[cols.product_id].nunique()
        features["product_diversity"] = features.index.map(diversity).fillna(0).astype(int)
    else:
        features["product_diversity"] = 0

    weekend_share = df.assign(_is_weekend=df[cols.date].dt.dayofweek >= 5).groupby(cols.customer_id)[
        "_is_weekend"
    ].mean()
    features["weekend_ratio"] = features.index.map(weekend_share).fillna(0.0)

    return features


def iter_rolling_windows(
    df: pd.DataFrame,
    config: AnalysisConfig = DEFAULT_CONFIG,
    observation_days: Optional[int] = None,
    prediction_days: Optional[int] = None,
    step_days: Optional[int] = None,
):
    """Slide a fixed-length (observation_days, prediction_days) window
    across the transaction history, yielding (cutoff, calibration_slice,
    holdout_slice) for each step.

    Every calibration slice spans exactly `observation_days`, so every
    snapshot's recency/tenure values are bounded the same way — including
    the final "live" snapshot used at scoring time. This is what keeps
    train-time and predict-time feature distributions consistent, instead
    of a single split whose calibration length depends on however much
    history happens to be in the uploaded file.
    """
    cols = config.columns
    observation_days = observation_days or config.observation_days
    prediction_days = prediction_days or config.prediction_days
    step_days = step_days or config.rolling_step_days

    min_d, max_d = df[cols.date].min(), df[cols.date].max()
    cutoff = min_d + pd.Timedelta(days=observation_days)
    last_cutoff = max_d - pd.Timedelta(days=prediction_days)

    while cutoff <= last_cutoff:
        calib_start = cutoff - pd.Timedelta(days=observation_days)
        calibration = df[(df[cols.date] > calib_start) & (df[cols.date] <= cutoff)]
        holdout = df[(df[cols.date] > cutoff) & (df[cols.date] <= cutoff + pd.Timedelta(days=prediction_days))]
        yield cutoff, calibration, holdout
        cutoff += pd.Timedelta(days=step_days)


def add_extended_features(
    feats: pd.DataFrame,
    full_df: pd.DataFrame,
    window_df: pd.DataFrame,
    config: AnalysisConfig,
    as_of: pd.Timestamp,
) -> pd.DataFrame:
    """Three extra features beyond the base RFM snapshot, computed with
    access to the customer's full history (not just this window):

    - customer_age_days: days since this customer's very first-ever
      transaction in the whole dataset, even if that's before the
      observation window started. Tells a brand-new customer apart from
      a long-standing one who happens to look identical within the
      window.
    - inter_purchase_std: how regular/irregular their purchase timing is
      within the window (std of days between consecutive orders).
    - recent_half_share: fraction of this window's purchases that fell
      in its more recent half — a cheap proxy for accelerating vs
      decelerating purchase behaviour.
    """
    cols = config.columns

    first_seen = full_df.groupby(cols.customer_id)[cols.date].min()
    feats["customer_age_days"] = feats.index.map(first_seen).map(
        lambda d: (as_of - d).days if pd.notna(d) else 0
    )

    def _std_days(dates: pd.Series) -> float:
        diffs = dates.sort_values().diff().dt.days.dropna()
        return float(diffs.std()) if len(diffs) > 1 else 0.0

    inter_std = window_df.groupby(cols.customer_id)[cols.date].apply(_std_days)
    feats["inter_purchase_std"] = feats.index.map(inter_std).fillna(0.0)

    window_start = as_of - pd.Timedelta(days=config.observation_days)
    midpoint = window_start + (as_of - window_start) / 2
    recent_half = window_df[window_df[cols.date] > midpoint]
    recent_count = recent_half.groupby(cols.customer_id)[cols.transaction_id].nunique()
    feats["recent_half_share"] = feats.index.map(recent_count).fillna(0) / feats["frequency"].clip(lower=1)

    return feats


def group_train_test_split(features: pd.DataFrame, test_size: float = 0.2, random_state: int = 42):
    """Held-out split that keeps a customer's rolling-window snapshots
    together on one side. Rows are indexed by customer id and a given
    customer can appear multiple times (once per snapshot cutoff) — a
    plain row-level train_test_split can put two highly similar
    snapshots of the same customer on opposite sides, which leaks
    information and makes held-out metrics look better than true
    generalization to unseen customers.
    """
    from sklearn.model_selection import GroupShuffleSplit

    groups = features.index
    splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=random_state)
    train_idx, test_idx = next(splitter.split(features, groups=groups))
    return features.iloc[train_idx], features.iloc[test_idx]


FEATURE_COLUMNS = [
    "recency",
    "tenure",
    "frequency",
    "monetary",
    "avg_order_value",
    "monetary_std",
    "total_units",
    "avg_basket_size",
    "product_diversity",
    "weekend_ratio",
    "avg_days_between_orders",
    "customer_age_days",
    "inter_purchase_std",
    "recent_half_share",
]
