import random
from datetime import datetime, timedelta

import pandas as pd
import pytest


def _make_transactions(n_customers=250, max_offset_days=340, seed=42) -> pd.DataFrame:
    random.seed(seed)
    countries = ["France", "Germany", "United Kingdom"]
    products = [(1000 + i, f"Product {i}") for i in range(30)]
    start = datetime(2019, 1, 1)

    rows = []
    txn_no = 1
    for customer_id in range(1, n_customers + 1):
        n_transactions = random.randint(1, 12)
        for _ in range(n_transactions):
            date = start + timedelta(days=random.randint(0, max_offset_days))
            n_lines = random.randint(1, 4)
            country = random.choice(countries)
            for _ in range(n_lines):
                product_id, product_name = random.choice(products)
                rows.append(
                    {
                        "CustomerNo": customer_id,
                        "TransactionNo": f"T{txn_no}",
                        "ProductNo": product_id,
                        "ProductName": product_name,
                        "Quantity": random.randint(1, 8),
                        "Price": round(random.uniform(2, 90), 2),
                        "Date": date.strftime("%m/%d/%Y"),
                        "Country": country,
                    }
                )
            txn_no += 1

    return pd.DataFrame(rows)


@pytest.fixture
def synthetic_transactions() -> pd.DataFrame:
    """A synthetic but realistic transactions table, shaped like the
    original CrmData.xlsx (CustomerNo, TransactionNo, ProductNo,
    ProductName, Quantity, Price, Date, Country).

    Spans ~340 days so the rolling-window (observation_days=90,
    prediction_days=90, step=30) generator in features.py has several
    valid cutoffs to iterate over.
    """
    return _make_transactions()
