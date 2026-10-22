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


# Other names the same field commonly goes by: Turkish exports, the UCI
# "Online Retail" layout (InvoiceNo / StockCode / UnitPrice / CustomerID /
# InvoiceDate) and generic e-commerce exports. Matching is case- and
# accent-insensitive and ignores spaces, dots, dashes and underscores.
COLUMN_ALIASES = {
    "customer_id": ["customerno", "customerid", "customer", "clientid", "musterino", "musteriid", "musterikodu", "musteri"],
    "transaction_id": [
        "transactionno", "transactionid", "invoiceno", "invoice", "invoiceid", "orderno", "orderid",
        "islemno", "siparisno", "siparisid", "faturano", "fisno",
    ],
    "product_id": ["productno", "productid", "stockcode", "sku", "urunno", "urunkodu", "urunid", "stokkodu"],
    "product_name": ["productname", "description", "urunadi", "urunismi", "urun"],
    "quantity": ["quantity", "qty", "adet", "miktar"],
    "price": ["price", "unitprice", "fiyat", "birimfiyat", "birimfiyati"],
    "date": ["date", "invoicedate", "orderdate", "transactiondate", "tarih", "islemtarihi", "siparistarihi", "faturatarihi"],
    "country": ["country", "ulke"],
}

FIELD_LABELS = {
    "customer_id": "müşteri no",
    "transaction_id": "işlem / fatura no",
    "quantity": "adet",
    "price": "birim fiyat",
    "date": "tarih",
}

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

MIN_HISTORY_DAYS = 180


def _key(name: object) -> str:
    text = str(name).strip().lower()
    for a, b in (("ı", "i"), ("ü", "u"), ("ş", "s"), ("ğ", "g"), ("ç", "c"), ("ö", "o"), ("i̇", "i")):
        text = text.replace(a, b)
    return "".join(ch for ch in text if ch.isalnum())


def normalize_columns(df: pd.DataFrame, config: AnalysisConfig = DEFAULT_CONFIG) -> pd.DataFrame:
    """Rename recognised alternative column names to the ones the analysis
    expects (config.columns). A column that already has the expected name
    is left alone; an alias is only used when exactly one column matches.
    """
    cols = config.columns
    present = {_key(c): c for c in df.columns}
    renames = {}
    for field_name, aliases in COLUMN_ALIASES.items():
        target = getattr(cols, field_name)
        if target in df.columns:
            continue
        matches = [present[a] for a in aliases if a in present and present[a] not in renames]
        if len(matches) == 1:
            renames[matches[0]] = target
    return df.rename(columns=renames)


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


def _to_number(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        return series
    # "1.234,50" (Turkish) and "1234.50" both become 1234.5
    text = series.astype(str).str.strip()
    turkish = text.str.contains(",", regex=False)
    text = text.where(~turkish, text.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    return pd.to_numeric(text, errors="coerce")


def load_transactions(source: SourceType, config: AnalysisConfig = DEFAULT_CONFIG) -> pd.DataFrame:
    """Load raw transaction data from a path or file-like object (.xlsx,
    .xls or .csv), map alternative column names, and check everything the
    analysis needs up front — so a bad file fails at upload with a clear
    message, not minutes later deep inside model training.
    """
    name = str(getattr(source, "name", source)).lower()

    if name.endswith(".csv"):
        # sep=None sniffs the delimiter: Turkish Excel exports CSV with ';'
        df = pd.read_csv(source, sep=None, engine="python", encoding="utf-8-sig")
    elif name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(source)
    else:
        raise ValueError("Desteklenmeyen dosya türü. Lütfen .xlsx, .xls ya da .csv yükleyin.")

    df = normalize_columns(df, config)
    cols = config.columns
    required = {f: getattr(cols, f) for f in FIELD_LABELS}
    missing = [f"{col} ({FIELD_LABELS[f]})" for f, col in required.items() if col not in df.columns]
    if missing:
        raise ValueError(
            "Dosyada gerekli kolonlar bulunamadı: " + ", ".join(missing)
            + ". Kolon adlarını şablondaki gibi yazın ya da sayfadaki eş anlamlı adlardan birini kullanın."
        )

    df[cols.quantity] = _to_number(df[cols.quantity])
    df[cols.price] = _to_number(df[cols.price])

    raw_dates = df[cols.date]
    filled = raw_dates.notna() & (raw_dates.astype(str).str.strip() != "")
    parsed = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]")
    parsed[filled] = parse_dates(raw_dates[filled], config)
    df[cols.date] = parsed

    usable = df.dropna(subset=[cols.customer_id, cols.quantity, cols.price, cols.date])
    usable = usable[(usable[cols.quantity] > 0) & (usable[cols.price] > 0)]
    if usable.empty:
        raise ValueError(
            "Kullanılabilir satır yok: müşteri no, adet, fiyat ve tarihi dolu, adet ve fiyatı sıfırdan büyük "
            "en az bir satır olmalı. Adet ve fiyat sayı olmalı."
        )

    dates = usable[cols.date]
    span = (dates.max() - dates.min()).days
    if span < MIN_HISTORY_DAYS:
        raise ValueError(
            f"Veri yalnızca {span} günü kapsıyor. CLTV ve churn modelleri 90 günlük geçmişe bakıp sonraki 90 günü "
            f"tahmin ettiği için en az {MIN_HISTORY_DAYS} günlük (tercihen 1 yıllık) işlem verisi gerekir."
        )
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
