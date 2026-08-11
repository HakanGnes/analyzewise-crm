"""Data loading and the single shared cleaning step.

The original code copy-pasted the same dropna / outlier-capping / date
parsing block inside create_rfm, create_cltv_c and create_cltv_p. It now
lives here once, as prepare_transactions().
"""
from __future__ import annotations

from pathlib import Path
from typing import Tuple, Union

import pandas as pd

from .config import AnalysisConfig, DEFAULT_CONFIG

SourceType = Union[str, Path, "object"]


def load_transactions(source: SourceType, config: AnalysisConfig = DEFAULT_CONFIG) -> pd.DataFrame:
    """Load raw transaction data from a path, or a file-like object such as
    Streamlit's UploadedFile. Supports .xlsx/.xls and .csv.

    Raises ValueError early if required columns are missing, instead of
    failing deep inside a later groupby with a confusing KeyError.
    """
    name = str(getattr(source, "name", source)).lower()

    if name.endswith(".csv"):
        df = pd.read_csv(source)
    else:
        df = pd.read_excel(source)

    cols = config.columns
    required = {cols.customer_id, cols.transaction_id, cols.quantity, cols.price, cols.date}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Yüklenen veri dosyasında beklenen kolonlar eksik: {sorted(missing)}")

    return df


def outlier_thresholds(series: pd.Series, factor: float = 1.5) -> Tuple[float, float]:
    q1, q3 = series.quantile(0.25), series.quantile(0.75)
    iqr = q3 - q1
    return q1 - factor * iqr, q3 + factor * iqr


def _cap_outliers(df: pd.DataFrame, column: str) -> None:
    low, high = outlier_thresholds(df[column])
    df.loc[df[column] < low, column] = low
    df.loc[df[column] > high, column] = high


def prepare_transactions(raw_df: pd.DataFrame, config: AnalysisConfig = DEFAULT_CONFIG) -> pd.DataFrame:
    """Clean raw transactions: drop nulls, keep positive quantity/price,
    parse dates, cap outliers, and add a TotalPrice column.
    """
    cols = config.columns
    df = raw_df.dropna(subset=[cols.customer_id, cols.quantity, cols.price, cols.date]).copy()
    df = df[(df[cols.quantity] > 0) & (df[cols.price] > 0)]

    if config.date_format:
        df[cols.date] = pd.to_datetime(df[cols.date], format=config.date_format)
    else:
        df[cols.date] = pd.to_datetime(df[cols.date])

    # Excel/CSV often infer whole-number Quantity as int64. Outlier capping
    # assigns a float threshold (e.g. -5.5) into that column; pandas 2.x+
    # raises instead of silently upcasting, so cast explicitly first.
    df[cols.quantity] = df[cols.quantity].astype(float)
    df[cols.price] = df[cols.price].astype(float)

    _cap_outliers(df, cols.quantity)
    _cap_outliers(df, cols.price)

    df["TotalPrice"] = df[cols.quantity] * df[cols.price]
    return df


def resolve_analysis_date(df: pd.DataFrame, config: AnalysisConfig = DEFAULT_CONFIG):
    """Reference date for recency calculations.

    Defaults to one day after the most recent transaction in the given
    data (config.analysis_date=None), instead of a value frozen to one
    historical dataset. Pass an explicit analysis_date in the config to
    override.
    """
    if config.analysis_date is not None:
        return config.analysis_date
    return df[config.columns.date].max() + pd.Timedelta(days=1)
