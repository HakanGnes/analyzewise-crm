"""ML-based (supervised) CLTV prediction — replaces the parametric BG/NBD
+ Gamma-Gamma model.

v2 (rolling-window + hyperparameter tuning): a sliding fixed-length window
across the transaction history instead of one 50/50 split, so training and
scoring see the same recency/tenure range; and a GroupKFold-based
RandomizedSearchCV over XGBoost hyperparameters instead of a fixed,
never-tuned config.
"""
from __future__ import annotations

import pandas as pd
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import GroupKFold, RandomizedSearchCV
from xgboost import XGBClassifier, XGBRegressor

from .config import AnalysisConfig, DEFAULT_CONFIG
from .data import prepare_transactions
from .features import FEATURE_COLUMNS, add_extended_features, build_customer_features, group_train_test_split, iter_rolling_windows

PARAM_DISTRIBUTIONS = {
    "n_estimators": [100, 150, 200, 300, 400],
    "max_depth": [2, 3, 4, 5, 6],
    "learning_rate": [0.01, 0.03, 0.05, 0.08, 0.1],
    "subsample": [0.6, 0.7, 0.8, 1.0],
    "colsample_bytree": [0.6, 0.7, 0.8, 1.0],
    "min_child_weight": [1, 3, 5, 7],
}


def build_cltv_training_set(raw_df: pd.DataFrame, config: AnalysisConfig = DEFAULT_CONFIG) -> pd.DataFrame:
    df = prepare_transactions(raw_df, config)
    rows = []
    for cutoff, calibration, holdout in iter_rolling_windows(df, config):
        if calibration.empty:
            continue
        feats = build_customer_features(calibration, config, as_of=cutoff + pd.Timedelta(days=1))
        feats = add_extended_features(feats, df, calibration, config, cutoff + pd.Timedelta(days=1))
        holdout_spend = holdout.groupby(config.columns.customer_id)["TotalPrice"].sum()
        feats["future_spend"] = feats.index.map(holdout_spend).fillna(0.0)
        rows.append(feats)

    if not rows:
        raise ValueError(
            "Rolling pencere için yeterli veri aralığı yok. "
            "config.observation_days / prediction_days değerlerini küçültün "
            "veya daha uzun bir tarih aralığına sahip veri kullanın."
        )
    return pd.concat(rows)


def train_cltv_model(features: pd.DataFrame, random_state: int = 42) -> XGBRegressor:
    """Fixed, untuned hyperparameters — kept for quick/cheap use. Prefer
    tune_cltv_model for anything reporting real quality numbers.
    """
    model = XGBRegressor(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=random_state,
        objective="reg:squarederror",
    )
    model.fit(features[FEATURE_COLUMNS], features["future_spend"])
    return model


def tune_cltv_model(features: pd.DataFrame, n_iter: int = 30, n_splits: int = 4, random_state: int = 42) -> tuple:
    """Randomized hyperparameter search over XGBRegressor, with
    GroupKFold on customer id so a customer's multiple rolling snapshots
    always land in the same fold (avoids optimistic leakage across
    train/validation). Returns (best_fitted_model, best_params, best_cv_neg_mae).
    """
    X, y = features[FEATURE_COLUMNS], features["future_spend"]
    groups = features.index
    n_splits = max(2, min(n_splits, len(set(groups))))
    cv_splits = list(GroupKFold(n_splits=n_splits).split(X, y, groups=groups))

    search = RandomizedSearchCV(
        XGBRegressor(random_state=random_state, objective="reg:squarederror"),
        param_distributions=PARAM_DISTRIBUTIONS,
        n_iter=n_iter,
        scoring="neg_mean_absolute_error",
        cv=cv_splits,
        random_state=random_state,
        n_jobs=-1,
    )
    search.fit(X, y)
    return search.best_estimator_, search.best_params_, -search.best_score_


def evaluate_cltv_model(features: pd.DataFrame, random_state: int = 42, n_iter: int = 20) -> dict:
    """Held-out MAE on an 80/20 split, using a hyperparameter-tuned model
    (GroupKFold search on the 80% side), plus a naive baseline (predict
    the training mean for every test row) so the MAE has a concrete
    anchor: if the tuned model's MAE isn't meaningfully below the
    baseline's, it isn't adding value over "guess the average".
    """
    train_df, test_df = group_train_test_split(features, test_size=0.2, random_state=random_state)
    model, best_params, cv_mae = tune_cltv_model(train_df, n_iter=n_iter, random_state=random_state)
    preds = model.predict(test_df[FEATURE_COLUMNS]).clip(min=0)
    mae = mean_absolute_error(test_df["future_spend"], preds)

    baseline_pred = train_df["future_spend"].mean()
    baseline_mae = mean_absolute_error(test_df["future_spend"], [baseline_pred] * len(test_df))

    return {
        "mae": mae,
        "cv_mae": cv_mae,
        "best_params": best_params,
        "baseline_mae": baseline_mae,
        "improvement_over_baseline": 1 - (mae / baseline_mae) if baseline_mae > 0 else float("nan"),
        "n_train": len(train_df),
        "n_test": len(test_df),
        "mean_future_spend": float(features["future_spend"].mean()),
    }


def train_cltv_hurdle_model(features: pd.DataFrame, random_state: int = 42) -> tuple:
    """Two-stage ('hurdle') model for a zero-inflated target: a large
    share of future_spend values are exactly 0 (customers who don't
    return at all). A single regressor has to solve "will they return"
    and "how much will they spend" at once, which is harder than solving
    them separately:

      stage 1 (classifier): P(future_spend > 0)  — "will they buy again"
      stage 2 (regressor):  E[future_spend | future_spend > 0], fit only
                             on rows where the customer did return

    Final prediction = stage1_probability * stage2_expected_spend.
    """
    features = features.copy()
    features["will_repeat"] = (features["future_spend"] > 0).astype(int)

    clf = XGBClassifier(
        n_estimators=200,
        max_depth=3,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=random_state,
        eval_metric="logloss",
    )
    clf.fit(features[FEATURE_COLUMNS], features["will_repeat"])

    repeaters = features[features["will_repeat"] == 1]
    reg = XGBRegressor(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=random_state,
        objective="reg:squarederror",
    )
    reg.fit(repeaters[FEATURE_COLUMNS], repeaters["future_spend"])
    return clf, reg


def predict_with_hurdle_model(clf: XGBClassifier, reg: XGBRegressor, X: pd.DataFrame) -> pd.Series:
    p_repeat = clf.predict_proba(X)[:, 1]
    spend_given_repeat = reg.predict(X).clip(min=0)
    return pd.Series(p_repeat * spend_given_repeat, index=X.index)


def evaluate_cltv_hurdle_model(features: pd.DataFrame, random_state: int = 42) -> dict:
    """Same held-out 80/20 split and baseline as evaluate_cltv_model, so
    the two are directly comparable."""
    train_df, test_df = group_train_test_split(features, test_size=0.2, random_state=random_state)
    clf, reg = train_cltv_hurdle_model(train_df, random_state=random_state)
    preds = predict_with_hurdle_model(clf, reg, test_df[FEATURE_COLUMNS])
    mae = mean_absolute_error(test_df["future_spend"], preds)

    baseline_pred = train_df["future_spend"].mean()
    baseline_mae = mean_absolute_error(test_df["future_spend"], [baseline_pred] * len(test_df))

    return {
        "mae": mae,
        "baseline_mae": baseline_mae,
        "improvement_over_baseline": 1 - (mae / baseline_mae) if baseline_mae > 0 else float("nan"),
        "n_train": len(train_df),
        "n_test": len(test_df),
        "mean_future_spend": float(features["future_spend"].mean()),
        "zero_share": float((features["future_spend"] == 0).mean()),
    }


def predict_cltv_hurdle(raw_df: pd.DataFrame, config: AnalysisConfig = DEFAULT_CONFIG) -> pd.DataFrame:
    training_features = build_cltv_training_set(raw_df, config)
    clf, reg = train_cltv_hurdle_model(training_features)

    df = prepare_transactions(raw_df, config)
    max_date = df[config.columns.date].max()
    obs_start = max_date - pd.Timedelta(days=config.observation_days)
    current_window = df[df[config.columns.date] > obs_start]
    as_of = max_date + pd.Timedelta(days=1)
    live_features = build_customer_features(current_window, config, as_of=as_of)
    live_features = add_extended_features(live_features, df, current_window, config, as_of)
    live_features["predicted_cltv"] = predict_with_hurdle_model(clf, reg, live_features[FEATURE_COLUMNS])

    active_ids = set(live_features.index)
    all_ids = set(df[config.columns.customer_id].unique())
    dormant_ids = all_ids - active_ids
    if dormant_ids:
        dormant_df = df[df[config.columns.customer_id].isin(dormant_ids)]
        dormant_features = build_customer_features(dormant_df, config, as_of=as_of)
        dormant_features = add_extended_features(dormant_features, df, dormant_df, config, as_of)
        dormant_features["predicted_cltv"] = 0.0
        live_features = pd.concat([live_features, dormant_features])

    live_features["segment"] = pd.qcut(
        live_features["predicted_cltv"].rank(method="first"), 4, labels=["low", "mid", "high", "very high"]
    )
    return live_features


def predict_cltv(raw_df: pd.DataFrame, config: AnalysisConfig = DEFAULT_CONFIG) -> pd.DataFrame:
    training_features = build_cltv_training_set(raw_df, config)
    model, _best_params, _cv_mae = tune_cltv_model(training_features)

    df = prepare_transactions(raw_df, config)
    max_date = df[config.columns.date].max()
    obs_start = max_date - pd.Timedelta(days=config.observation_days)
    current_window = df[df[config.columns.date] > obs_start]
    as_of = max_date + pd.Timedelta(days=1)
    live_features = build_customer_features(current_window, config, as_of=as_of)
    live_features = add_extended_features(live_features, df, current_window, config, as_of)
    live_features["predicted_cltv"] = model.predict(live_features[FEATURE_COLUMNS]).clip(min=0)

    active_ids = set(live_features.index)
    all_ids = set(df[config.columns.customer_id].unique())
    dormant_ids = all_ids - active_ids
    if dormant_ids:
        dormant_df = df[df[config.columns.customer_id].isin(dormant_ids)]
        dormant_features = build_customer_features(dormant_df, config, as_of=as_of)
        dormant_features = add_extended_features(dormant_features, df, dormant_df, config, as_of)
        dormant_features["predicted_cltv"] = 0.0
        live_features = pd.concat([live_features, dormant_features])

    live_features["segment"] = pd.qcut(
        live_features["predicted_cltv"].rank(method="first"), 4, labels=["low", "mid", "high", "very high"]
    )
    return live_features
