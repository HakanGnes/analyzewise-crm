"""JSON-safety helpers.

pandas/numpy types (int64, float64, Categorical, Timestamp) aren't
JSON-serializable by Python's stdlib json module, which is what
Starlette's default JSONResponse uses. Two small helpers cover every
response shape this API returns: a DataFrame of rows, or a metrics dict
that may contain numpy scalars nested inside (e.g. RandomizedSearchCV's
best_params_).
"""
from __future__ import annotations

import json
from typing import Any, List

import numpy as np
import pandas as pd


def df_to_records(df: pd.DataFrame) -> List[dict]:
    """Convert a DataFrame (index included) to a list of JSON-safe dicts.

    Routes through pandas' own to_json — it already knows how to handle
    numpy scalar types, Categorical columns, and NaN/NaT — instead of
    hand-rolling type coercion.
    """
    return json.loads(df.reset_index().to_json(orient="records", date_format="iso"))


def _default(o: Any):
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (pd.Timestamp,)):
        return o.isoformat()
    return str(o)


def safe_jsonable(obj: Any) -> Any:
    """Round-trip through json.dumps/loads with a numpy-aware default
    encoder, so nested numpy scalars anywhere in a dict/list survive.
    """
    return json.loads(json.dumps(obj, default=_default))
