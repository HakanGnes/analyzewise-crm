"""Tests for package behaviour added on the backend copy of analyzewise_crm:
RFM-grid segment naming, scored recommendations, co-purchase trend."""
import warnings

import pytest

from analyzewise_crm import DEFAULT_CONFIG
from analyzewise_crm.recommender import (
    collaborative_filtering_recommend,
    collaborative_filtering_scores,
    compute_association_rules,
    copurchase_trend,
    recommend_products,
    recommend_products_scored,
    top_rules,
)
from analyzewise_crm.segmentation import SEGMENT_NAMES, cluster_customers
from app.demo_data import generate_demo_transactions

warnings.filterwarnings("ignore")


@pytest.fixture(scope="module")
def demo():
    return generate_demo_transactions()


@pytest.mark.parametrize("k", [3, 6, 10])
def test_segment_names_are_unique_and_valid(demo, k):
    seg = cluster_customers(demo, DEFAULT_CONFIG, k=k)
    names = seg.groupby("cluster")["segment"].first()
    assert names.nunique() == k
    assert set(names) <= set(SEGMENT_NAMES)


def test_segment_names_follow_behaviour(demo):
    """The most recent, most frequent cluster must not be named like a lapsed
    one, and vice versa — regression test for single-score naming, which
    called a long-lapsed frequent-buyer cluster "yeni müşteriler"."""
    seg = cluster_customers(demo, DEFAULT_CONFIG, k=6)
    means = seg.groupby("segment")[["recency", "frequency"]].mean()
    lapsed = {"kış uykusundakiler", "riskte olanlar", "kaybedilmemeli", "uykuya yakın"}
    best = means.sort_values(["frequency"], ascending=False).index[0]
    worst = means.sort_values(["recency"], ascending=False).index[0]
    assert best not in lapsed
    assert worst in lapsed


def test_scored_recommendations_match_unscored_order(demo):
    rules = compute_association_rules(demo, DEFAULT_CONFIG)
    scored = recommend_products_scored(rules, 1001, 5)
    assert list(scored["product"]) == recommend_products(rules, 1001, 5)
    assert (scored["lift"].diff().dropna() <= 0).all()

    cf = collaborative_filtering_scores(demo, DEFAULT_CONFIG, 1001, 5)
    assert list(cf["product"]) == collaborative_filtering_recommend(demo, DEFAULT_CONFIG, 1001, 5)
    assert cf["similarity"].between(0, 1).all()


def test_top_rules_keeps_one_direction_per_pair(demo):
    pairs = top_rules(compute_association_rules(demo, DEFAULT_CONFIG), 10)
    keys = {tuple(sorted(p)) for p in zip(pairs["antecedent"], pairs["consequent"])}
    assert len(keys) == len(pairs)


def test_copurchase_trend_detects_planted_rise(demo):
    """The demo data plants a rising tea-set → bamboo-tray pairing."""
    trend = copurchase_trend(demo, DEFAULT_CONFIG, 1001, 8)
    rows = trend["rows"].set_index("product")
    assert 1004 in rows.index
    assert rows.loc[1004, "rate_second"] > rows.loc[1004, "rate_first"] * 1.5


def test_copurchase_trend_unknown_product_is_empty(demo):
    assert copurchase_trend(demo, DEFAULT_CONFIG, 999999)["rows"] == []
