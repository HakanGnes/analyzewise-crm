from analyzewise_crm.cltv import compute_cltv_c, compute_cltv_p


def test_compute_cltv_c_produces_segment_and_positive_values(synthetic_transactions):
    cltv_c = compute_cltv_c(synthetic_transactions)
    assert "cltv" in cltv_c.columns
    assert "segment" in cltv_c.columns
    assert (cltv_c["total_transaction"] > 0).all()


def test_compute_cltv_p_produces_expected_purchase_columns(synthetic_transactions):
    cltv_p = compute_cltv_p(synthetic_transactions)
    for label in ["1_week", "1_month", "3_month", "6_month", "9_month", "12_month"]:
        assert f"expected_purc_{label}" in cltv_p.columns
    assert "expected_average_profit" in cltv_p.columns
    assert "clv" in cltv_p.columns
    assert "segment" in cltv_p.columns
    # only repeat customers (frequency > 1) should remain
    assert (cltv_p["frequency"] > 1).all()
