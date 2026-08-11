"""Search over (observation_days, prediction_days) combinations.

The rolling-window length itself is a hyperparameter nobody has tuned yet
— it's been fixed at 90/90 since Faz 2.1. This module does a lightweight
grid search: for each combination, build the rolling training set and
fit a single fixed-hyperparameter model (not a full RandomizedSearchCV —
that would multiply the already-nontrivial cost by every combination) to
get a fast, relative comparison. Once you've picked a window from this,
re-run the full tuned pipeline (evaluate_churn_model /
evaluate_cltv_hurdle_model) with that window for the real reported
numbers.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Sequence

import pandas as pd
from sklearn.metrics import mean_absolute_error, roc_auc_score

from .churn import build_churn_training_set, train_churn_model
from .cltv_ml import build_cltv_training_set, train_cltv_hurdle_model, predict_with_hurdle_model
from .config import AnalysisConfig, DEFAULT_CONFIG
from .features import FEATURE_COLUMNS, group_train_test_split


def search_windows(
    raw_df: pd.DataFrame,
    base_config: AnalysisConfig = DEFAULT_CONFIG,
    observation_days_options: Sequence[int] = (30, 60, 90, 120),
    prediction_days_options: Sequence[int] = (30, 60, 90),
    random_state: int = 42,
) -> pd.DataFrame:
    """Try every (observation_days, prediction_days) combination, report
    held-out churn ROC AUC and CLTV-hurdle MAE/baseline-improvement for
    each. Combinations where the window doesn't fit the data's date
    range are skipped (build_*_training_set raises ValueError for those).

    Returns a DataFrame sorted by churn_auc descending — reasonable
    default since churn is usually the more actionable signal, but check
    cltv_mae too since the best window for one isn't always best for the
    other.
    """
    rows = []
    for obs_days in observation_days_options:
        for pred_days in prediction_days_options:
            step_days = max(7, obs_days // 3)
            cfg = replace(
                base_config,
                observation_days=obs_days,
                prediction_days=pred_days,
                rolling_step_days=step_days,
            )

            try:
                churn_features = build_churn_training_set(raw_df, cfg)
                cltv_features = build_cltv_training_set(raw_df, cfg)
            except ValueError:
                continue

            train_df, test_df = group_train_test_split(churn_features, test_size=0.2, random_state=random_state)
            churn_train, churn_test = train_df, test_df
            churn_model = train_churn_model(churn_train, random_state=random_state)
            if churn_test["churned"].nunique() > 1:
                churn_auc = roc_auc_score(
                    churn_test["churned"], churn_model.predict_proba(churn_test[FEATURE_COLUMNS])[:, 1]
                )
            else:
                churn_auc = float("nan")

            cltv_train, cltv_test = group_train_test_split(cltv_features, test_size=0.2, random_state=random_state)
            clf, reg = train_cltv_hurdle_model(cltv_train, random_state=random_state)
            preds = predict_with_hurdle_model(clf, reg, cltv_test[FEATURE_COLUMNS])
            cltv_mae = mean_absolute_error(cltv_test["future_spend"], preds)
            baseline_pred = cltv_train["future_spend"].mean()
            baseline_mae = mean_absolute_error(cltv_test["future_spend"], [baseline_pred] * len(cltv_test))
            improvement = 1 - (cltv_mae / baseline_mae) if baseline_mae > 0 else float("nan")

            rows.append(
                {
                    "observation_days": obs_days,
                    "prediction_days": pred_days,
                    "n_train_rows": len(churn_features),
                    "churn_auc": churn_auc,
                    "cltv_mae": cltv_mae,
                    "cltv_improvement_over_baseline": improvement,
                }
            )

    if not rows:
        raise ValueError(
            "Denenen hiçbir pencere kombinasyonu veri aralığına sığmadı. "
            "observation_days_options / prediction_days_options değerlerini küçültün."
        )
    return pd.DataFrame(rows).sort_values("churn_auc", ascending=False).reset_index(drop=True)
