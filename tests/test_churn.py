import numpy as np
import pandas as pd

from analyzewise_crm import predict_churn
from analyzewise_crm.churn import build_churn_training_set, evaluate_churn_model, train_churn_model, tune_churn_model
from analyzewise_crm.features import FEATURE_COLUMNS


def test_build_churn_training_set_has_binary_label(synthetic_transactions):
    features = build_churn_training_set(synthetic_transactions)
    assert set(features["churned"].unique()) <= {0, 1}
    # multiple rolling snapshots -> more rows than unique customers
    assert len(features) > features.index.nunique()


def test_churn_training_recency_bounded_by_observation_window(synthetic_transactions):
    from analyzewise_crm.config import DEFAULT_CONFIG

    features = build_churn_training_set(synthetic_transactions)
    assert features["recency"].max() <= DEFAULT_CONFIG.observation_days


def test_predict_churn_produces_probabilities_in_range(synthetic_transactions):
    result = predict_churn(synthetic_transactions)
    assert "churn_probability" in result.columns
    assert result["churn_probability"].between(0, 1).all()
    assert "risk_segment" in result.columns


def test_train_churn_model_uses_expected_features(synthetic_transactions):
    features = build_churn_training_set(synthetic_transactions)
    model = train_churn_model(features)
    assert list(model.feature_names_in_) == FEATURE_COLUMNS


def test_evaluate_churn_model_returns_auc(synthetic_transactions):
    features = build_churn_training_set(synthetic_transactions)
    metrics = evaluate_churn_model(features, n_iter=3)
    assert "roc_auc" in metrics
    assert "best_params" in metrics
    assert metrics["n_test"] > 0


def test_tune_churn_model_returns_fitted_estimator(synthetic_transactions):
    features = build_churn_training_set(synthetic_transactions)
    model, best_params, cv_score = tune_churn_model(features, n_iter=3, n_splits=2)
    assert list(model.feature_names_in_) == FEATURE_COLUMNS
    assert isinstance(best_params, dict) and len(best_params) > 0
    assert 0.0 <= cv_score <= 1.0


def test_predict_churn_covers_every_customer_including_long_dormant(synthetic_transactions):
    from analyzewise_crm.config import DEFAULT_CONFIG

    result = predict_churn(synthetic_transactions)
    all_ids = synthetic_transactions[DEFAULT_CONFIG.columns.customer_id].unique()
    assert set(result.index) == set(all_ids)
    # anyone silent longer than the observation window should be flagged
    # as maximal risk by definition, not silently dropped
    if (result["recency"] > DEFAULT_CONFIG.observation_days).any():
        dormant = result[result["recency"] > DEFAULT_CONFIG.observation_days]
        assert (dormant["churn_probability"] == 1.0).all()


def test_churn_probability_does_not_flatten_for_high_recency(synthetic_transactions):
    """Regression test for the exact bug reported against the v1
    (single-split) model: past the training recency boundary, predictions
    collapsed to one repeated constant instead of continuing to respond
    to recency. With rolling-window training, recency is bounded the same
    way at train and score time, so this probe (varying only recency,
    frequency=1) should not produce more than one distinct probability
    value across the high end of the range.
    """
    features = build_churn_training_set(synthetic_transactions)
    model = train_churn_model(features)

    probe = pd.DataFrame({"recency": np.arange(10, 90, 5)})
    for col in FEATURE_COLUMNS:
        if col == "recency":
            continue
        probe[col] = features[col].median()
    probe["frequency"] = 1
    probe["tenure"] = probe["recency"]
    probe["avg_days_between_orders"] = probe["tenure"]
    probe = probe[FEATURE_COLUMNS]

    proba = model.predict_proba(probe)[:, 1]
    # not asserting monotonicity (tree models are noisy on a held-out
    # probe), just that it isn't a single frozen constant across the
    # whole range the way the v1 model was past its training boundary.
    assert len(set(np.round(proba, 6))) > 1
