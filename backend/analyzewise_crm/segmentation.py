"""Data-driven customer segmentation via K-Means clustering.

Replaces the old rule-based RFM segmentation (fixed quintile bins + a
static regex map of segment names) with unsupervised clustering: the
data decides where the boundaries are instead of a hand-written regex
table. Cluster count is auto-selected with the same custom elbow
heuristic used in TransferRumor-App (no yellowbrick dependency), and
each cluster gets an interpretable Turkish label based on where its
centroid ranks relative to the others.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

from .config import AnalysisConfig, DEFAULT_CONFIG
from .data import prepare_transactions
from .features import build_customer_features

FEATURE_COLUMNS = ["recency", "frequency", "monetary"]

SEGMENT_NAMES = [
    "şampiyonlar",
    "sadık müşteriler",
    "potansiyel sadıklar",
    "yeni müşteriler",
    "umut veren",
    "ilgi gerek",
    "uykuya yakın",
    "riskte olanlar",
    "kaybedilmemeli",
    "kış uykusundakiler",
]


def find_optimal_k(X: np.ndarray, k_range=range(2, 11), random_state: int = 42) -> int:
    """Elbow method via distance-to-line: fit KMeans for each k, then pick
    the k whose (k, inertia) point is furthest from the straight line
    joining the first and last points on the inertia curve.
    """
    inertias = []
    for k in k_range:
        km = KMeans(n_clusters=k, n_init=10, random_state=random_state)
        km.fit(X)
        inertias.append(km.inertia_)

    ks = np.array(list(k_range), dtype=float)
    inertias = np.array(inertias, dtype=float)

    p1 = np.array([ks[0], inertias[0]])
    p2 = np.array([ks[-1], inertias[-1]])
    line_vec = p2 - p1
    line_len = np.linalg.norm(line_vec)
    line_unit = line_vec / line_len if line_len > 0 else line_vec

    distances = []
    for k, inertia in zip(ks, inertias):
        point = np.array([k, inertia]) - p1
        proj_len = np.dot(point, line_unit)
        proj_point = proj_len * line_unit
        distances.append(np.linalg.norm(point - proj_point))

    best_idx = int(np.argmax(distances))
    return int(ks[best_idx])


# Where each name sits on the classic RFM grid (R = recency score, F =
# frequency score, both 1–5, 5 = best), matching the original app's
# regex map: 5[4-5] champions, [3-4][4-5] loyal, [4-5][2-3] potential
# loyalists, 51 new, 41 promising, 33 need attention, 3[1-2] about to
# sleep, [1-2][3-4] at risk, [1-2]5 can't lose, [1-2][1-2] hibernating.
SEGMENT_GRID = {
    "şampiyonlar": (5.0, 4.5),
    "sadık müşteriler": (3.5, 4.5),
    "potansiyel sadıklar": (4.5, 2.5),
    "yeni müşteriler": (5.0, 1.0),
    "umut veren": (4.0, 1.0),
    "ilgi gerek": (3.0, 3.0),
    "uykuya yakın": (3.0, 1.5),
    "riskte olanlar": (1.5, 3.5),
    "kaybedilmemeli": (1.5, 5.0),
    "kış uykusundakiler": (1.5, 1.5),
}


def _rf_scores(centroids: pd.DataFrame, customers: pd.DataFrame) -> np.ndarray:
    """Continuous 1–5 R and F scores for each centroid, from where it falls
    in the customer distribution (lower recency is better)."""
    rec = np.sort(customers["recency"].to_numpy())
    freq = np.sort(customers["frequency"].to_numpy())
    r_pct = np.searchsorted(rec, centroids["recency"].to_numpy(), side="right") / len(rec)
    f_pct = np.searchsorted(freq, centroids["frequency"].to_numpy(), side="right") / len(freq)
    return np.column_stack([1 + 4 * (1 - r_pct), 1 + 4 * f_pct])


def _label_clusters(centroids: pd.DataFrame, customers: pd.DataFrame) -> dict:
    """Give each cluster the RFM segment name whose grid position is
    closest to the cluster's own R/F scores, each name used once (an
    assignment problem). Naming by a single "overall score" rank instead
    mislabels clusters — e.g. a cluster that bought often but stopped long
    ago would be called "yeni müşteriler".
    """
    from scipy.optimize import linear_sum_assignment

    ids = centroids.index.tolist()
    if len(ids) > len(SEGMENT_NAMES):
        score = -centroids["recency"].rank() + centroids["frequency"].rank() + centroids["monetary"].rank()
        ranked = score.sort_values(ascending=False).index.tolist()
        return {cid: (SEGMENT_NAMES[i] if i < len(SEGMENT_NAMES) else f"segment {i + 1}") for i, cid in enumerate(ranked)}

    scores = _rf_scores(centroids, customers)
    grid = np.array([SEGMENT_GRID[name] for name in SEGMENT_NAMES])
    cost = ((scores[:, None, :] - grid[None, :, :]) ** 2).sum(axis=2)
    rows, cols = linear_sum_assignment(cost)
    return {ids[r]: SEGMENT_NAMES[c] for r, c in zip(rows, cols)}


def cluster_customers(
    raw_df: pd.DataFrame,
    config: AnalysisConfig = DEFAULT_CONFIG,
    k: Optional[int] = None,
    random_state: int = 42,
) -> pd.DataFrame:
    """K-Means based customer segmentation.

    Returns a DataFrame indexed by customer id with recency/frequency/
    monetary, the numeric cluster id, and an interpretable `segment`
    label — a drop-in replacement for the old compute_rfm() output shape.
    """
    df = prepare_transactions(raw_df, config)
    features = build_customer_features(df, config)

    X_raw = features[FEATURE_COLUMNS].copy()
    # RFM is heavily right-skewed; log1p before scaling gives far more
    # balanced clusters than scaling the raw values directly.
    X_log = np.log1p(X_raw)
    X_scaled = StandardScaler().fit_transform(X_log)

    if k is None:
        k = find_optimal_k(X_scaled)
    k = max(2, min(k, len(features) - 1))

    km = KMeans(n_clusters=k, n_init=10, random_state=random_state)
    features["cluster"] = km.fit_predict(X_scaled)

    centroids = features.groupby("cluster")[FEATURE_COLUMNS].mean()
    label_map = _label_clusters(centroids, features)
    features["segment"] = features["cluster"].map(label_map)

    return features[["recency", "frequency", "monetary", "cluster", "segment"]]
