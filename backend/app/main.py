"""AnalyzeWise CRM API — FastAPI backend for the React frontend.

Thin wrapper: every route just calls into the analyzewise_crm package
(the same one the Streamlit app used) and shapes the result as JSON.
No business logic lives here.
"""
from __future__ import annotations

import io
import os
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from analyzewise_crm import DEFAULT_CONFIG, load_transactions, search_windows
from analyzewise_crm.churn import build_churn_training_set, evaluate_churn_model, predict_churn
from analyzewise_crm.cltv_ml import (
    build_cltv_training_set,
    evaluate_cltv_hurdle_model,
    evaluate_cltv_model,
    predict_cltv,
    predict_cltv_hurdle,
)
from analyzewise_crm.recommender import (
    collaborative_filtering_recommend,
    compute_association_rules,
    recommend_products,
)
from analyzewise_crm.segmentation import cluster_customers

from .demo_data import DEMO_FILENAME, generate_demo_transactions
from .store import store
from .utils import df_to_records, safe_jsonable

app = FastAPI(title="AnalyzeWise CRM API", version="0.3.0")

# Dev-friendly CORS default: allow everything unless ALLOWED_ORIGINS is set
# (comma-separated list, e.g. "https://analyzewise.vercel.app"). Set it in
# production so the API only answers your deployed frontend's origin.
_allowed_origins_env = os.environ.get("ALLOWED_ORIGINS", "*")
_allowed_origins = ["*"] if _allowed_origins_env == "*" else [o.strip() for o in _allowed_origins_env.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_session(session_id: str):
    session = store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Oturum bulunamadı. Dosyayı tekrar yükleyin.")
    return session


def _coerce_product_id(raw_df: pd.DataFrame, product_id: str):
    col = DEFAULT_CONFIG.columns.product_id
    if col not in raw_df.columns:
        return product_id
    sample = raw_df[col].dropna().iloc[0] if not raw_df[col].dropna().empty else None
    if isinstance(sample, (int, np.integer)):
        try:
            return int(product_id)
        except ValueError:
            return product_id
    return product_id


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    content = await file.read()
    buf = io.BytesIO(content)
    buf.name = file.filename  # load_transactions sniffs the extension from this

    try:
        raw_df = load_transactions(buf, DEFAULT_CONFIG)
    except Exception as exc:  # noqa: BLE001 - surfacing the parser's own message is the point
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _session_payload(store.create(raw_df, file.filename), raw_df, file.filename)


@app.post("/api/demo")
def start_demo():
    """Start a session on the built-in synthetic dataset, so a visitor
    without their own CRM file can still try every screen."""
    raw_df = generate_demo_transactions()
    session_id = store.create(raw_df, DEMO_FILENAME)
    payload = _session_payload(session_id, raw_df, DEMO_FILENAME)
    payload["is_demo"] = True
    return payload


def _session_payload(session_id: str, raw_df: pd.DataFrame, filename: str) -> dict:
    cols = DEFAULT_CONFIG.columns
    return safe_jsonable(
        {
            "session_id": session_id,
            "filename": filename,
            "n_rows": len(raw_df),
            "n_customers": int(raw_df[cols.customer_id].nunique()),
            "columns": list(raw_df.columns),
            "has_product_id": cols.product_id in raw_df.columns,
            "has_country": cols.country in raw_df.columns,
            "is_demo": False,
        }
    )


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str):
    deleted = store.delete(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Oturum bulunamadı.")
    return {"deleted": True}


@app.get("/api/overview")
def get_overview(session_id: str):
    """Fast dashboard summary — no model training, just aggregation, so
    it can be the landing screen right after upload without a wait.
    """
    session = _get_session(session_id)
    cached = store.cache_get(session_id, "overview")
    if cached is not None:
        return cached

    from analyzewise_crm.data import prepare_transactions

    cols = DEFAULT_CONFIG.columns
    df = prepare_transactions(session.raw_df, DEFAULT_CONFIG)

    kpis = {
        "total_customers": int(df[cols.customer_id].nunique()),
        "total_revenue": float(df["TotalPrice"].sum()),
        "total_transactions": int(df[cols.transaction_id].nunique()),
        "avg_order_value": float(df.groupby(cols.transaction_id)["TotalPrice"].sum().mean()),
        "date_min": df[cols.date].min().strftime("%Y-%m-%d"),
        "date_max": df[cols.date].max().strftime("%Y-%m-%d"),
    }

    monthly = df.set_index(cols.date).resample("MS").agg(
        revenue=("TotalPrice", "sum"),
        transactions=(cols.transaction_id, "nunique"),
    )
    first_purchase_month = df.groupby(cols.customer_id)[cols.date].min().dt.to_period("M").dt.to_timestamp()
    new_customers_by_month = first_purchase_month.value_counts().sort_index()
    monthly["new_customers"] = monthly.index.map(new_customers_by_month).fillna(0).astype(int)
    monthly = monthly.reset_index().rename(columns={cols.date: "month"})
    monthly["month"] = monthly["month"].dt.strftime("%Y-%m")

    payload = {"kpis": safe_jsonable(kpis), "monthly_trend": safe_jsonable(monthly.to_dict(orient="records"))}
    store.cache_set(session_id, "overview", payload)
    return payload


@app.get("/api/segments")
def get_segments(session_id: str, k: Optional[int] = Query(None, ge=2, le=10), auto: bool = False):
    session = _get_session(session_id)
    cache_key = f"segments:{k}:{auto}"
    cached = store.cache_get(session_id, cache_key)
    if cached is not None:
        return cached

    kmeans_k = None if auto else (k or 6)
    result_df = cluster_customers(session.raw_df, DEFAULT_CONFIG, k=kmeans_k)
    payload = {
        "rows": df_to_records(result_df),
        "segment_counts": safe_jsonable(result_df["segment"].value_counts().to_dict()),
        "segment_means": df_to_records(result_df.groupby("segment")[["recency", "frequency", "monetary"]].mean()),
    }
    store.cache_set(session_id, cache_key, payload)
    return payload


@app.get("/api/cltv")
def get_cltv(session_id: str, approach: str = Query("single", pattern="^(single|hurdle)$")):
    session = _get_session(session_id)
    cache_key = f"cltv:{approach}"
    cached = store.cache_get(session_id, cache_key)
    if cached is not None:
        return cached

    result_df = predict_cltv_hurdle(session.raw_df, DEFAULT_CONFIG) if approach == "hurdle" else predict_cltv(
        session.raw_df, DEFAULT_CONFIG
    )
    cols = DEFAULT_CONFIG.columns
    payload = {
        "rows": df_to_records(result_df[["predicted_cltv", "frequency", "monetary", "segment"]]),
        "segment_means": df_to_records(result_df.groupby("segment")["predicted_cltv"].mean().to_frame()),
    }
    store.cache_set(session_id, cache_key, payload)
    return payload


@app.get("/api/cltv/evaluate")
def get_cltv_evaluate(session_id: str, approach: str = Query("single", pattern="^(single|hurdle)$")):
    session = _get_session(session_id)
    cache_key = f"cltv_eval:{approach}"
    cached = store.cache_get(session_id, cache_key)
    if cached is not None:
        return cached

    features = build_cltv_training_set(session.raw_df, DEFAULT_CONFIG)
    metrics = evaluate_cltv_hurdle_model(features) if approach == "hurdle" else evaluate_cltv_model(features)
    metrics = safe_jsonable(metrics)
    store.cache_set(session_id, cache_key, metrics)
    return metrics


@app.get("/api/churn")
def get_churn(session_id: str):
    session = _get_session(session_id)
    cached = store.cache_get(session_id, "churn")
    if cached is not None:
        return cached

    result_df = predict_churn(session.raw_df, DEFAULT_CONFIG)
    payload = {
        "rows": df_to_records(result_df[["churn_probability", "recency", "frequency", "risk_segment"]]),
        "risk_counts": safe_jsonable(result_df["risk_segment"].value_counts().to_dict()),
    }
    store.cache_set(session_id, "churn", payload)
    return payload


@app.get("/api/churn/evaluate")
def get_churn_evaluate(session_id: str):
    session = _get_session(session_id)
    cached = store.cache_get(session_id, "churn_eval")
    if cached is not None:
        return cached

    features = build_churn_training_set(session.raw_df, DEFAULT_CONFIG)
    metrics = safe_jsonable(evaluate_churn_model(features))
    store.cache_set(session_id, "churn_eval", metrics)
    return metrics


@app.get("/api/products")
def get_products(session_id: str):
    session = _get_session(session_id)
    col = DEFAULT_CONFIG.columns.product_id
    if col not in session.raw_df.columns:
        return {"products": []}
    ids = sorted(session.raw_df[col].dropna().unique().tolist())
    return {"products": safe_jsonable(ids)}


@app.get("/api/recommendations")
def get_recommendations(
    session_id: str,
    product_id: str,
    method: str = Query("fpgrowth", pattern="^(fpgrowth|cf)$"),
    top_n: int = Query(5, ge=1, le=10),
):
    session = _get_session(session_id)
    pid = _coerce_product_id(session.raw_df, product_id)

    if method == "fpgrowth":
        rules = store.cache_get(session_id, "rules")
        if rules is None:
            rules = compute_association_rules(session.raw_df, DEFAULT_CONFIG)
            store.cache_set(session_id, "rules", rules)
        recs = recommend_products(rules, pid, top_n)
    else:
        recs = collaborative_filtering_recommend(session.raw_df, DEFAULT_CONFIG, pid, top_n)

    return {"recommendations": safe_jsonable(list(recs))}


@app.get("/api/windows/search")
def search_window_options(session_id: str):
    """Powers the "pencere araması" screen. This is the slow one (trains
    several models) — the frontend should show a loading state and the
    result is cached per session so it only runs once.
    """
    session = _get_session(session_id)
    cached = store.cache_get(session_id, "window_search")
    if cached is not None:
        return cached

    try:
        results = search_windows(session.raw_df, DEFAULT_CONFIG)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = {"rows": df_to_records(results)}
    store.cache_set(session_id, "window_search", payload)
    return payload
