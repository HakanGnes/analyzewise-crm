"""CLTV models.

compute_cltv_p: probabilistic CLTV via BG/NBD (purchase counts) + Gamma-Gamma
(average profit per transaction).

compute_cltv_c: the simpler heuristic CLTV-C formula, kept for the
CLTV-C screen but with the profit_margin and churn-rate edge case fixed.
"""
from __future__ import annotations

import pandas as pd
from lifetimes import BetaGeoFitter, GammaGammaFitter

from .config import AnalysisConfig, DEFAULT_CONFIG
from .data import prepare_transactions, resolve_analysis_date


def compute_cltv_c(raw_df: pd.DataFrame, config: AnalysisConfig = DEFAULT_CONFIG) -> pd.DataFrame:
    cols = config.columns
    df = prepare_transactions(raw_df, config)

    cltv_c = df.groupby(cols.customer_id).agg(
        total_transaction=(cols.transaction_id, "nunique"),
        total_unit=(cols.quantity, "sum"),
        total_price=("TotalPrice", "sum"),
    )

    cltv_c["avg_order_value"] = cltv_c["total_price"] / cltv_c["total_transaction"]
    cltv_c["purchase_frequency"] = cltv_c["total_transaction"] / cltv_c.shape[0]

    repeat_rate = (cltv_c["total_transaction"] > 1).mean()
    churn_rate = 1 - repeat_rate
    if churn_rate <= 0:
        # Every customer in this dataset is a repeat buyer - avoid a
        # division by zero instead of crashing the whole screen.
        churn_rate = 1e-6

    cltv_c["profit_margin"] = cltv_c["total_price"] * config.profit_margin
    cltv_c["customer_value"] = cltv_c["avg_order_value"] * cltv_c["purchase_frequency"]
    cltv_c["cltv"] = (cltv_c["customer_value"] / churn_rate) * cltv_c["profit_margin"]
    cltv_c["segment"] = pd.qcut(cltv_c["cltv"], 4, labels=["low", "mid", "high", "very high"])
    return cltv_c


def compute_cltv_p(raw_df: pd.DataFrame, config: AnalysisConfig = DEFAULT_CONFIG) -> pd.DataFrame:
    cols = config.columns
    df = prepare_transactions(raw_df, config)
    analysis_date = resolve_analysis_date(df, config)

    summary = df.groupby(cols.customer_id).agg(
        recency=(cols.date, lambda s: (s.max() - s.min()).days),
        T=(cols.date, lambda s: (analysis_date - s.min()).days),
        frequency=(cols.transaction_id, "nunique"),
        monetary=("TotalPrice", "sum"),
    )
    summary["monetary"] = summary["monetary"] / summary["frequency"]
    summary = summary[summary["frequency"] > 1]
    summary["recency"] = summary["recency"] / 7
    summary["T"] = summary["T"] / 7

    bgf = BetaGeoFitter(penalizer_coef=0.001)
    bgf.fit(summary["frequency"], summary["recency"], summary["T"])

    for label, weeks in config.weekly_periods.items():
        summary[f"expected_purc_{label}"] = bgf.predict(
            weeks, summary["frequency"], summary["recency"], summary["T"]
        )

    ggf = GammaGammaFitter(penalizer_coef=0.01)
    ggf.fit(summary["frequency"], summary["monetary"])
    summary["expected_average_profit"] = ggf.conditional_expected_average_profit(
        summary["frequency"], summary["monetary"]
    )

    clv = ggf.customer_lifetime_value(
        bgf,
        summary["frequency"],
        summary["recency"],
        summary["T"],
        summary["monetary"],
        time=config.cltv_forecast_month,
        freq="W",
        discount_rate=0.01,
    ).reset_index()

    result = summary.merge(clv, on=cols.customer_id, how="left")
    result["segment"] = pd.qcut(result["clv"], 4, labels=["low", "mid", "high", "very high"])
    return result
