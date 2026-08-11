"""Central configuration for AnalyzeWise-CRM.

Everything that used to be hardcoded inside the analysis functions
(magic dates, column names, profit margin, country filter, thresholds)
lives here instead, so the same analysis code can run on a different
retail dataset without editing the functions themselves.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional


@dataclass(frozen=True)
class ColumnMap:
    """Maps the logical fields the analysis needs to actual column names."""

    customer_id: str = "CustomerNo"
    transaction_id: str = "TransactionNo"
    product_id: str = "ProductNo"
    product_name: str = "ProductName"
    quantity: str = "Quantity"
    price: str = "Price"
    date: str = "Date"
    country: str = "Country"


@dataclass(frozen=True)
class AnalysisConfig:
    columns: ColumnMap = field(default_factory=ColumnMap)

    # Set to None to auto-detect the date format via pandas.
    date_format: Optional[str] = "%m/%d/%Y"

    # The old code froze this at datetime(2019, 12, 11) for one specific
    # dataset. None means "one day after the most recent transaction in
    # the uploaded data" so the app works correctly for any dataset.
    analysis_date: Optional[datetime] = None

    profit_margin: float = 0.10
    arl_country_filter: Optional[str] = "France"
    arl_min_support: float = 0.01
    arl_min_threshold: float = 0.01
    cltv_forecast_month: int = 3

    # Rolling-window training for the ML-CLTV and churn models. A single
    # 50/50 calibration/holdout split bounds the recency values the model
    # ever sees during training to half the dataset's date range, while
    # scoring uses the full range — the model then has to extrapolate for
    # any customer whose recency exceeds that bound, which tree models
    # cannot do (predictions flatten out). Sliding a fixed-length window
    # across the history keeps the recency range identical between
    # training and scoring, and yields far more training snapshots.
    observation_days: int = 90
    prediction_days: int = 90
    rolling_step_days: int = 30

    segmentation_k: Optional[int] = None

    weekly_periods: Dict[str, int] = field(
        default_factory=lambda: {
            "1_week": 1,
            "1_month": 4,
            "3_month": 12,
            "6_month": 26,
            "9_month": 39,
            "12_month": 52,
        }
    )


DEFAULT_CONFIG = AnalysisConfig()
