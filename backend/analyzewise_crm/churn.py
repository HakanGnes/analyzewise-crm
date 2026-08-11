"""Customer-level churn prediction.

v2 (rolling-window): replaces the single 50/50 calibration/holdout split
with a sliding fixed-length window across the transaction history. The
single-split version bounded training-time recency to half the dataset's
date range while scoring used the full range, so the model had to
extrapolate for any long-dormant customer — tree models can't do that,
predictions just flatten out past the training boundary (see
tests/test_churn.py::test_churn_probability_does_not_flatten_for_high_recency
for a regression test against exactly that failure mode).
"""
from __future__ import annotations

from typing import Optional

import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold, RandomizedSearchCV
from xgboost import XGBClassifier

from .config import AnalysisConfig, DEFAULT_CONFIG
from .data import prepare_transactions
from .features import FEATURE_COLUMNS, add_extended_features, build_customer_features, group_train_test_split, iter_rolling_windows

RISK_LABELS = ["düşük risk", "orta risk", "yüksek risk", "çok yüksek risk"]

PARAM_DISTRIBUTIONS = {
    "n_estimators": [100, 150, 200, 300, 400],
    "max_depth": [2, 3, 4, 5, 6],
    "learning_rate": [0.01, 0.03, 0.05, 0.08, 0.1],
    "subsample": [0.6, 0.7, 0.8, 1.0],
    "colsample_bytree": [0.6, 0.7, 0.8, 1.0],
    "min_child_weight": [1, 3, 5, 7],
}


def build_churn_training_set(raw_df: pd.DataFrame, config: AnalysisConfig = DEFAULT_CONFIG) -> pd.DataFrame:
    """Concatenate one row per (customer, snapshot cutoff) across every
    rolling window. Every snapshot's calibration slice spans exactly
    config.observation_days, so recency/tenure are bounded the same way
    in every row — including the live snapshot used later for scoring.
    """
    df = prepare_transactions(raw_df, config)
    rows = []
    for cutoff, calibration, holdout in iter_rolling_windows(df, config):
        if calibration.empty:
            continue
        as_of = cutoff + pd.Timedelta(days=1)
        feats = build_customer_features(calibration, config, as_of=as_of)
        feats = add_extended_features(feats, df, calibration, config, as_of)
        returned_customers = set(holdout[config.columns.customer_id].unique())
        feats["churned"] = (~feats.index.isin(returned_customers)).astype(int)
        rows.append(feats)

    if not rows:
        raise ValueError(
            "Rolling pencere için yeterli veri aralığı yok. "
            "config.observation_days / prediction_days değerlerini küçültün "
            "veya daha uzun bir tarih aralığına sahip veri kullanın."
        )
    return pd.concat(rows)


def train_churn_model(features: pd.DataFrame, random_state: int = 42) -> XGBClassifier:
    """Fixed, untuned hyperparameters — kept for quick/cheap use (e.g. the
    regression test that just checks predictions vary with recency).
    Prefer tune_churn_model for anything reporting real quality numbers.
    """
    model = XGBClassifier(
        n_estimators=200,
        max_depth=3,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=random_state,
        eval_metric="logloss",
    )
    model.fit(features[FEATURE_COLUMNS], features["churned"])
    return model


def tune_churn_model(
    features: pd.DataFrame, n_iter: int = 30, n_splits: int = 4, random_state: int = 42
) -> tuple:
    """Randomized hyperparameter search over XGBClassifier, with
    GroupKFold on customer id so a given customer's multiple rolling
    snapshots always land in the same fold — otherwise the same customer
    could appear in both the train and validation side of a fold, making
    the CV score look better than it really is.

    Returns (best_fitted_model, best_params, best_cv_roc_auc).
    """
    X, y = features[FEATURE_COLUMNS], features["churned"]
    groups = features.index
    n_splits = max(2, min(n_splits, len(set(groups))))
    cv_splits = list(GroupKFold(n_splits=n_splits).split(X, y, groups=groups))

    search = RandomizedSearchCV(
        XGBClassifier(random_state=random_state, eval_metric="logloss"),
        param_distributions=PARAM_DISTRIBUTIONS,
        n_iter=n_iter,
        scoring="roc_auc",
        cv=cv_splits,
        random_state=random_state,
        n_jobs=-1,
    )
    search.fit(X, y)
    return search.best_estimator_, search.best_params_, search.best_score_


def evaluate_churn_model(features: pd.DataFrame, random_state: int = 42, n_iter: int = 20) -> dict:
    """Held-out ROC AUC on a stratified 80/20 split, using a
    hyperparameter-tuned model (GroupKFold search on the 80% side) so the
    reported number reflects the tuned model's real quality, not just
    whatever the fixed defaults happened to produce.
    """
    train_df, test_df = group_train_test_split(features, test_size=0.2, random_state=random_state)

    model, best_params, cv_score = tune_churn_model(train_df, n_iter=n_iter, random_state=random_state)
    if test_df["churned"].nunique() > 1:
        proba = model.predict_proba(test_df[FEATURE_COLUMNS])[:, 1]
        auc = roc_auc_score(test_df["churned"], proba)
    else:
        auc = float("nan")
    return {
        "roc_auc": auc,
        "cv_roc_auc": cv_score,
        "best_params": best_params,
        "n_train": len(train_df),
        "n_test": len(test_df),
        "positive_rate": float(features["churned"].mean()),
    }


def predict_churn(raw_df: pd.DataFrame, config: AnalysisConfig = DEFAULT_CONFIG) -> pd.DataFrame:
    training_features = build_churn_training_set(raw_df, config)
    model, _best_params, _cv_score = tune_churn_model(training_features)

    df = prepare_transactions(raw_df, config)
    max_date = df[config.columns.date].max()
    obs_start = max_date - pd.Timedelta(days=config.observation_days)
    current_window = df[df[config.columns.date] > obs_start]
    as_of = max_date + pd.Timedelta(days=1)

    live_features = build_customer_features(current_window, config, as_of=as_of)
    live_features = add_extended_features(live_features, df, current_window, config, as_of)
    live_features["churn_probability"] = model.predict_proba(live_features[FEATURE_COLUMNS])[:, 1]

    # Customers with no purchase at all inside the observation window
    # would force the model to extrapolate past its training range if
    # scored directly (recency > anything it ever saw). By the training
    # label's own definition — "churned" means no purchase within
    # prediction_days of the cutoff — anyone silent for longer than that
    # is already churned; no model call needed, just the definitional
    # answer, so they still show up in the report instead of vanishing.
    active_ids = set(live_features.index)
    all_ids = set(df[config.columns.customer_id].unique())
    dormant_ids = all_ids - active_ids
    if dormant_ids:
        dormant_df = df[df[config.columns.customer_id].isin(dormant_ids)]
        dormant_features = build_customer_features(dormant_df, config, as_of=as_of)
        dormant_features = add_extended_features(dormant_features, df, dormant_df, config, as_of)
        dormant_features["churn_probability"] = 1.0
        live_features = pd.concat([live_features, dormant_features])

    live_features["risk_segment"] = pd.cut(
        live_features["churn_probability"], bins=[-0.01, 0.25, 0.5, 0.75, 1.0], labels=RISK_LABELS
    )
    return live_features
