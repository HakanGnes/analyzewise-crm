import pandas as pd

from analyzewise_crm import prepare_transactions, resolve_analysis_date
from analyzewise_crm.config import DEFAULT_CONFIG


def test_prepare_transactions_adds_total_price(synthetic_transactions):
    cleaned = prepare_transactions(synthetic_transactions)
    assert "TotalPrice" in cleaned.columns
    assert (cleaned["TotalPrice"] == cleaned["Quantity"] * cleaned["Price"]).all()


def test_prepare_transactions_drops_non_positive_rows(synthetic_transactions):
    df = synthetic_transactions.copy()
    df.loc[0, "Quantity"] = -5
    df.loc[1, "Price"] = 0
    cleaned = prepare_transactions(df)
    assert (cleaned["Quantity"] > 0).all()
    assert (cleaned["Price"] > 0).all()


def test_resolve_analysis_date_defaults_to_day_after_last_transaction(synthetic_transactions):
    cleaned = prepare_transactions(synthetic_transactions)
    analysis_date = resolve_analysis_date(cleaned, DEFAULT_CONFIG)
    assert analysis_date == cleaned["Date"].max() + pd.Timedelta(days=1)


def test_prepare_transactions_handles_integer_dtype_columns(synthetic_transactions):
    """Regression test: Excel/CSV often infer whole-number Quantity/Price
    as int64. Outlier capping assigns a float threshold into that column,
    which pandas 2.x+ raises on instead of silently upcasting (caught by
    actually running scripts/check_model_quality.py against a real .xlsx
    file). Force int dtypes here to make sure that path stays fixed.
    """
    df = synthetic_transactions.copy()
    df["Quantity"] = df["Quantity"].astype("int64")
    df["Price"] = df["Price"].round().astype("int64")
    cleaned = prepare_transactions(df)
    assert len(cleaned) > 0


def test_group_train_test_split_never_splits_a_customer_across_sides():
    """Regression test: rolling-window training sets have duplicate
    customer-id rows (one per snapshot). A plain row-level train_test_split
    can put two of the same customer's snapshots on opposite sides, which
    leaks information and inflates held-out metrics (caught by comparing
    window-search AUCs before/after this fix — they dropped from ~0.65
    to ~0.5 on fully random synthetic data once fixed).
    """
    from analyzewise_crm.features import group_train_test_split

    idx = [1, 1, 1, 2, 2, 3, 4, 4, 5, 5, 5, 6, 7, 8, 9, 10]
    df = pd.DataFrame({"x": range(len(idx))}, index=pd.Index(idx, name="CustomerNo"))
    train_df, test_df = group_train_test_split(df, test_size=0.3, random_state=0)
    assert set(train_df.index) & set(test_df.index) == set()
