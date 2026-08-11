from analyzewise_crm.rfm import compute_rfm


def test_compute_rfm_produces_expected_columns(synthetic_transactions):
    rfm = compute_rfm(synthetic_transactions)
    assert set(rfm.columns) == {"recency", "frequency", "monetary", "segment"}
    assert rfm.index.name == "CustomerNo"
    assert rfm.index.dtype.kind == "i"


def test_compute_rfm_segments_are_non_null(synthetic_transactions):
    rfm = compute_rfm(synthetic_transactions)
    assert rfm["segment"].notna().all()
    assert rfm.shape[0] > 0
