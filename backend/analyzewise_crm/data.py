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


# Tried in order; the first one that parses every non-empty value wins.
DATE_FORMATS = [
    "%m/%d/%Y",
    "%m/%d/%Y %H:%M",
    "%Y-%m-%d",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%d.%m.%Y",
    "%d.%m.%Y %H:%M",
    "%d/%m/%Y",
    "%d/%m/%Y %H:%M",
]

def parse_dates(series: pd.Series, config: AnalysisConfig = DEFAULT_CONFIG) -> pd.Series:
    """Parse a date column. Excel date cells arrive already parsed; text
    dates are tried against the configured format first, then common
    ISO and day-first (Turkish) layouts. Raises ValueError if none fits.
    """
    if pd.api.types.is_datetime64_any_dtype(series):
        return series
    text = series.astype(str).str.strip()
    formats = [config.date_format] if config.date_format else []
    formats += [f for f in DATE_FORMATS if f not in formats]
    best = None
    for fmt in formats:
        parsed = pd.to_datetime(text, format=fmt, errors="coerce")
        if parsed.notna().all():
            return parsed
        if best is None or parsed.notna().sum() > best.notna().sum():
            best = parsed
    # A handful of malformed cells shouldn't reject a whole file: if one
    # format reads at least 98% of the values, the rest become empty and
    # are dropped like any other incomplete row.
    if best is not None and len(text) and best.notna().mean() >= 0.98:
        return best
    example = text.iloc[0] if len(text) else ""
    raise ValueError(
        f"Tarih kolonu okunamadı (örnek değer: '{example}'). Desteklenen biçimler: 2026-10-22, "
        "22.10.2026, 22/10/2026, 10/22/2026 (saat eklenebilir). Excel'de tarih hücresi olarak kaydetmek en güvenlisi."
    )


def load_transactions(source: SourceType, config: AnalysisConfig = DEFAULT_CONFIG) -> pd.DataFrame:
    """Load a sales file (.xlsx, .xls or .csv; path or file-like) and turn
    it into the standard transaction table, guessing which column is
    which (see schema.py). Raises ValueError with a Turkish message when
    the file can't be understood or analysed.

    The web app uses the two-step inspect/confirm flow instead, so the
    user can correct a guess before the table is built.
    """
    from .schema import auto_build

    if isinstance(source, (str, Path)):
        content, name = Path(source).read_bytes(), str(source)
    else:
        content = source.read()
        name = str(getattr(source, "name", "upload.xlsx"))
    df, _report = auto_build(content, name, config)
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

    df[cols.date] = parse_dates(df[cols.date], config)

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
