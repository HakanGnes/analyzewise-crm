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
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from analyzewise_crm import DEFAULT_CONFIG, load_transactions, search_windows
from analyzewise_crm import schema
from analyzewise_crm.recommender import (
    collaborative_filtering_scores,
    copurchase_trend,
    recommend_products_scored,
)

from . import analysis, report
from .demo_data import DEMO_FILENAME, generate_demo_transactions
from .store import pending, store
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
    """One-shot upload: guess the columns and analyse without asking.
    The web app uses /api/upload/inspect + /confirm instead."""
    content = await file.read()
    try:
        raw_df, build = schema.auto_build(content, file.filename or "upload.xlsx", DEFAULT_CONFIG)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = _session_payload(store.create(raw_df, file.filename), raw_df, file.filename)
    payload["summary"] = build.as_dict()
    return payload


MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def _inspection(upload_id: str, sheet: Optional[str], date_order: str = "auto") -> dict:
    item = pending.get(upload_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Yüklenen dosya bulunamadı ya da süresi doldu. Dosyayı tekrar yükleyin.")
    content, filename = item
    try:
        table = schema.read_table(content, filename, sheet)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if table.df.empty or len(table.df.columns) < 2:
        raise HTTPException(status_code=400, detail="Dosyada okunabilir bir tablo bulunamadı.")

    profiles = schema.profile_columns(table.df, date_order)
    suggestions = schema.suggest_mapping(table.df, profiles)
    mapping = {role: s.column for role, s in suggestions.items()}
    by_name = {p.name: p for p in profiles}
    date_profile = by_name.get(mapping["date"]) if mapping["date"] else None
    preview = table.df.head(5).map(lambda v: "" if pd.isna(v) else schema._sample_text(v))
    return safe_jsonable(
        {
            "upload_id": upload_id,
            "filename": filename,
            "sheets": table.sheets,
            "sheet": table.sheet,
            "header_row": table.header_row + 1,  # 1-based for people
            "n_rows": len(table.df),
            "columns": [
                {"name": p.name, "kind": p.kind, "samples": p.samples, "unique": p.unique,
                 "empty_share": round(p.empty_share, 3), "date_ambiguous": p.date_ambiguous}
                for p in profiles
            ],
            "roles": [
                {"role": role, "label": spec["label"], "required": spec["required"], "help": spec["help"],
                 "column": suggestions[role].column, "confidence": suggestions[role].confidence,
                 "reason": suggestions[role].reason}
                for role, spec in schema.ROLES.items()
            ],
            "date": {
                "label": date_profile.date_label if date_profile else "",
                "ambiguous": bool(date_profile and date_profile.date_ambiguous),
                "order": date_order,
            },
            "hints": schema.unreadable_hints(profiles, suggestions),
            "problems": schema.mapping_problems(mapping),
            "preview": {"columns": list(preview.columns), "rows": preview.values.tolist()},
        }
    )


@app.post("/api/upload/inspect")
async def upload_inspect(file: UploadFile = File(...), sheet: Optional[str] = Form(None)):
    """Step 1 of the upload flow: read the file and guess which column
    is which. Nothing is analysed yet; the user confirms or corrects the
    guesses, then calls /confirm."""
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Dosya 50 MB'tan büyük.")
    upload_id = pending.add(content, file.filename or "upload.xlsx")
    return _inspection(upload_id, sheet)


class InspectOptions(BaseModel):
    sheet: Optional[str] = None
    date_order: str = "auto"


@app.post("/api/upload/{upload_id}/inspect")
def upload_reinspect(upload_id: str, options: InspectOptions):
    """Re-read the same file with another sheet or date order."""
    return _inspection(upload_id, options.sheet, options.date_order)


class ConfirmBody(BaseModel):
    mapping: dict
    sheet: Optional[str] = None
    date_order: str = "auto"


@app.post("/api/upload/{upload_id}/confirm")
def upload_confirm(upload_id: str, body: ConfirmBody):
    """Step 2: build the standard table with the user's mapping and open
    an analysis session."""
    item = pending.get(upload_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Yüklenen dosya bulunamadı ya da süresi doldu. Dosyayı tekrar yükleyin.")
    content, filename = item
    mapping = {role: (body.mapping.get(role) or None) for role in schema.ROLES}
    try:
        table = schema.read_table(content, filename, body.sheet)
        df, build = schema.apply_mapping(table.df, mapping, DEFAULT_CONFIG, body.date_order)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    pending.pop(upload_id)
    payload = _session_payload(store.create(df, filename), df, filename)
    payload["summary"] = build.as_dict()
    return payload


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
    result_df = analysis.segments(session_id, session, k, auto)
    return {
        "rows": df_to_records(result_df),
        "segment_counts": safe_jsonable(result_df["segment"].value_counts().to_dict()),
        "segment_means": df_to_records(result_df.groupby("segment")[["recency", "frequency", "monetary"]].mean()),
    }


@app.get("/api/cltv")
def get_cltv(session_id: str, approach: str = Query("single", pattern="^(single|hurdle)$")):
    session = _get_session(session_id)
    result_df = analysis.cltv(session_id, session, approach)
    return {
        "rows": df_to_records(result_df[["predicted_cltv", "frequency", "monetary", "segment"]]),
        "segment_means": df_to_records(result_df.groupby("segment", observed=True)["predicted_cltv"].mean().to_frame()),
    }


@app.get("/api/cltv/evaluate")
def get_cltv_evaluate(session_id: str, approach: str = Query("single", pattern="^(single|hurdle)$")):
    session = _get_session(session_id)
    return safe_jsonable(analysis.cltv_metrics(session_id, session, approach))


@app.get("/api/churn")
def get_churn(session_id: str):
    session = _get_session(session_id)
    result_df = analysis.churn(session_id, session)
    return {
        "rows": df_to_records(result_df[["churn_probability", "recency", "frequency", "risk_segment"]]),
        "risk_counts": safe_jsonable(result_df["risk_segment"].value_counts().to_dict()),
    }


@app.get("/api/churn/evaluate")
def get_churn_evaluate(session_id: str):
    session = _get_session(session_id)
    return safe_jsonable(analysis.churn_metrics(session_id, session))


@app.get("/api/value-risk")
def get_value_risk(session_id: str, approach: str = Query("single", pattern="^(single|hurdle)$")):
    """Churn probability × historical spend per customer, plus the
    priority list: customers who spent a lot and are likely to leave."""
    session = _get_session(session_id)
    joined = analysis.value_risk(session_id, session, approach)
    priority = joined[joined["quadrant"] == "değerli, riskte"].sort_values("historical_spend", ascending=False)
    return {
        "rows": df_to_records(joined[["churn_probability", "historical_spend", "quadrant"]]),
        "quadrant_counts": safe_jsonable(joined["quadrant"].value_counts().to_dict()),
        "thresholds": {"risk": analysis.HIGH_RISK, "value": safe_jsonable(joined.attrs.get("value_cut", 0.0))},
        "priority": df_to_records(priority.head(25)),
        "priority_total_value": safe_jsonable(float(priority["historical_spend"].sum())),
        "priority_count": int(len(priority)),
    }


@app.get("/api/products")
def get_products(session_id: str):
    session = _get_session(session_id)
    col = DEFAULT_CONFIG.columns.product_id
    if col not in session.raw_df.columns:
        return {"products": [], "names": {}}
    names = analysis.product_names(session)
    ids = sorted(session.raw_df[col].dropna().unique().tolist())
    basket_counts = session.raw_df.groupby(col)[DEFAULT_CONFIG.columns.transaction_id].nunique()
    popular = basket_counts.sort_values(ascending=False).head(10).index.tolist()
    return {
        "products": safe_jsonable(ids),
        "names": {str(k): v for k, v in safe_jsonable(names).items()},
        "popular": safe_jsonable(popular),
    }


@app.get("/api/recommendations")
def get_recommendations(
    session_id: str,
    product_id: str,
    method: str = Query("fpgrowth", pattern="^(fpgrowth|cf)$"),
    top_n: int = Query(5, ge=1, le=10),
):
    session = _get_session(session_id)
    pid = _coerce_product_id(session.raw_df, product_id)
    names = analysis.product_names(session)

    if method == "fpgrowth":
        scored = recommend_products_scored(analysis.rules(session_id, session), pid, top_n)
        score_col = "lift"
    else:
        scored = collaborative_filtering_scores(session.raw_df, DEFAULT_CONFIG, pid, top_n)
        score_col = "similarity"

    items = [
        {
            "product_id": row["product"],
            "name": names.get(row["product"], str(row["product"])),
            "score": row[score_col],
            **({"confidence": row["confidence"], "support": row["support"]} if method == "fpgrowth" else {}),
        }
        for row in scored.to_dict(orient="records")
    ]
    return safe_jsonable(
        {
            "recommendations": [i["product_id"] for i in items],
            "items": items,
            "score_label": "Lift" if method == "fpgrowth" else "Benzerlik (kosinüs)",
            "anchor_name": names.get(pid, str(pid)),
        }
    )


@app.get("/api/recommendations/trend")
def get_recommendation_trend(session_id: str, product_id: str, top_n: int = Query(8, ge=2, le=12)):
    """Paired data for the co-purchase slopegraph (first vs second half)."""
    session = _get_session(session_id)
    pid = _coerce_product_id(session.raw_df, product_id)
    names = analysis.product_names(session)
    trend = copurchase_trend(session.raw_df, DEFAULT_CONFIG, pid, top_n)
    rows = trend["rows"]
    items = (
        [
            {
                "product_id": r["product"],
                "name": names.get(r["product"], str(r["product"])),
                "first": r["rate_first"],
                "second": r["rate_second"],
            }
            for r in rows.to_dict(orient="records")
        ]
        if len(rows)
        else []
    )
    return safe_jsonable({"items": items, "periods": trend["periods"], "anchor_baskets": trend["anchor_baskets"]})


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


def _report_context(session_id: str, k: Optional[int], auto: bool, approach: str) -> dict:
    session = _get_session(session_id)
    return report.build_context(session_id, session, k, auto, approach)


@app.get("/api/report", response_class=HTMLResponse)
def get_report(
    session_id: str,
    k: Optional[int] = Query(None, ge=2, le=10),
    auto: bool = False,
    approach: str = Query("single", pattern="^(single|hurdle)$"),
    download: bool = False,
):
    """Self-contained HTML CRM report built from the same cached analyses
    the screens use, with the settings the user picked there."""
    content = report.render_html(_report_context(session_id, k, auto, approach))
    headers = {"Content-Disposition": 'attachment; filename="crm_raporu.html"'} if download else {}
    return HTMLResponse(content=content, headers=headers)


@app.get("/api/report.xlsx")
def get_report_xlsx(
    session_id: str,
    k: Optional[int] = Query(None, ge=2, le=10),
    auto: bool = False,
    approach: str = Query("single", pattern="^(single|hurdle)$"),
):
    """Excel workbook with the report's lists: summary, segments with
    actions, every customer with all scores, win-back list, product pairs."""
    data = report.render_xlsx(_report_context(session_id, k, auto, approach))
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="crm_raporu.xlsx"'},
    )
