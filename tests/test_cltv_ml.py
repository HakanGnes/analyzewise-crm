from analyzewise_crm import predict_cltv
from analyzewise_crm.cltv_ml import (
    build_cltv_training_set,
    evaluate_cltv_hurdle_model,
    evaluate_cltv_model,
    predict_cltv_hurdle,
    train_cltv_hurdle_model,
    train_cltv_model,
    tune_cltv_model,
)
from analyzewise_crm.features import FEATURE_COLUMNS


def test_build_cltv_training_set_has_future_spend_label(synthetic_transactions):
    features = build_cltv_training_set(synthetic_transactions)
    assert "future_spend" in features.columns
    assert (features["future_spend"] >= 0).all()
    assert len(features) > features.index.nunique()


def test_cltv_training_recency_bounded_by_observation_window(synthetic_transactions):
    from analyzewise_crm.config import DEFAULT_CONFIG

    features = build_cltv_training_set(synthetic_transactions)
    assert features["recency"].max() <= DEFAULT_CONFIG.observation_days


def test_predict_cltv_produces_non_negative_predictions(synthetic_transactions):
    result = predict_cltv(synthetic_transactions)
    assert "predicted_cltv" in result.columns
    assert (result["predicted_cltv"] >= 0).all()
    assert "segment" in result.columns
    assert result["segment"].notna().all()


def test_predict_cltv_covers_every_customer(synthetic_transactions):
    from analyzewise_crm.config import DEFAULT_CONFIG

    result = predict_cltv(synthetic_transactions)
    all_ids = synthetic_transactions[DEFAULT_CONFIG.columns.customer_id].unique()
    assert set(result.index) == set(all_ids)


def test_train_cltv_model_uses_expected_features(synthetic_transactions):
    features = build_cltv_training_set(synthetic_transactions)
    model = train_cltv_model(features)
    assert list(model.feature_names_in_) == FEATURE_COLUMNS


def test_evaluate_cltv_model_returns_mae(synthetic_transactions):
    features = build_cltv_training_set(synthetic_transactions)
    metrics = evaluate_cltv_model(features, n_iter=3)
    assert "mae" in metrics
    assert "baseline_mae" in metrics
    assert "improvement_over_baseline" in metrics
    assert "best_params" in metrics
    assert metrics["n_test"] > 0


def test_tune_cltv_model_returns_fitted_estimator(synthetic_transactions):
    features = build_cltv_training_set(synthetic_transactions)
    model, best_params, cv_mae = tune_cltv_model(features, n_iter=3, n_splits=2)
    assert list(model.feature_names_in_) == FEATURE_COLUMNS
    assert isinstance(best_params, dict) and len(best_params) > 0
    assert cv_mae >= 0


def test_train_cltv_hurdle_model_returns_two_fitted_estimators(synthetic_transactions):
    features = build_cltv_training_set(synthetic_transactions)
    clf, reg = train_cltv_hurdle_model(features)
    assert list(clf.feature_names_in_) == FEATURE_COLUMNS
    assert list(reg.feature_names_in_) == FEATURE_COLUMNS


def test_evaluate_cltv_hurdle_model_returns_mae_and_zero_share(synthetic_transactions):
    features = build_cltv_training_set(synthetic_transactions)
    metrics = evaluate_cltv_hurdle_model(features)
    assert "mae" in metrics
    assert "baseline_mae" in metrics
    assert 0.0 <= metrics["zero_share"] <= 1.0


def test_predict_cltv_hurdle_covers_every_customer(synthetic_transactions):
    from analyzewise_crm.config import DEFAULT_CONFIG

    result = predict_cltv_hurdle(synthetic_transactions)
    all_ids = synthetic_transactions[DEFAULT_CONFIG.columns.customer_id].unique()
    assert set(result.index) == set(all_ids)
    assert (result["predicted_cltv"] >= 0).all()
