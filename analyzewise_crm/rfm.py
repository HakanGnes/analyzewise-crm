"""RFM (Recency, Frequency, Monetary) segmentation."""
from __future__ import annotations

import pandas as pd

from .config import AnalysisConfig, DEFAULT_CONFIG
from .data import prepare_transactions, resolve_analysis_date

SEGMENT_MAP = {
    r"[1-2][1-2]": "kış uykusundakiler",
    r"[1-2][3-4]": "riskte olanlar",
    r"[1-2]5": "kaybedilmemeli",
    r"3[1-2]": "uykuya yakın",
    r"33": "ilgi gerek",
    r"[3-4][4-5]": "sadık müşteriler",
    r"41": "umut veren",
    r"51": "yeni müşteriler",
    r"[4-5][2-3]": "potansiyel sadıklar",
    r"5[4-5]": "şampiyonlar",
}


def compute_rfm(raw_df: pd.DataFrame, config: AnalysisConfig = DEFAULT_CONFIG) -> pd.DataFrame:
    """Return a DataFrame indexed by customer id with recency, frequency,
    monetary and a Turkish segment label, mirroring the original app's
    output shape.
    """
    cols = config.columns
    df = prepare_transactions(raw_df, config)
    analysis_date = resolve_analysis_date(df, config)

    rfm = df.groupby(cols.customer_id).agg(
        recency=(cols.date, lambda s: (analysis_date - s.max()).days),
        frequency=(cols.transaction_id, "nunique"),
        monetary=("TotalPrice", "sum"),
    )

    rfm["recency_score"] = pd.qcut(rfm["recency"], 5, labels=[5, 4, 3, 2, 1])
    rfm["frequency_score"] = pd.qcut(rfm["frequency"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5])
    rfm["monetary_score"] = pd.qcut(rfm["monetary"], 5, labels=[1, 2, 3, 4, 5])

    rfm["RFM_SCORE"] = rfm["recency_score"].astype(str) + rfm["frequency_score"].astype(str)
    rfm["segment"] = rfm["RFM_SCORE"].replace(SEGMENT_MAP, regex=True)

    rfm = rfm[["recency", "frequency", "monetary", "segment"]]
    rfm.index = rfm.index.astype(int)
    return rfm
