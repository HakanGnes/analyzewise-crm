"""Column recognition + the inspect/confirm upload flow, on files that do
not look like the template: letter IDs, no invoice column, only a line
total, title rows above the header, several sheets, unhelpful headers."""
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from analyzewise_crm.schema import normalize_ids, parse_date_column, to_number
from app.main import app

from .hard_files import ALL, base

client = TestClient(app)


def _inspect(name):
    content, filename = ALL[name]()
    r = client.post("/api/upload/inspect", files={"file": (filename, content)})
    assert r.status_code == 200, r.text
    return r.json()


def _roles(body):
    return {r["role"]: r["column"] for r in body["roles"]}


def test_erp_export_is_understood():
    body = _inspect("erp")
    assert body["sheet"] == "Satışlar" and body["header_row"] == 4
    roles = _roles(body)
    assert roles["customer_id"] == "Cari Kodu"
    assert roles["date"] == "Satış Tarihi"
    assert roles["amount"] == "Tutar" and roles["price"] is None
    assert roles["transaction_id"] is None
    assert body["problems"] == []


def test_unknown_headers_get_content_based_guesses():
    body = _inspect("unknown_names")
    roles = _roles(body)
    assert roles["date"] == "Zaman"
    assert roles["quantity"] == "Kaç tane"
    assert roles["amount"] == "Para"
    conf = {r["role"]: r["confidence"] for r in body["roles"]}
    assert conf["amount"] == "kontrol et"


@pytest.mark.parametrize("name", ["erp", "ecommerce", "online_retail"])
def test_confirmed_file_matches_the_source_revenue(name):
    body = _inspect(name)
    r = client.post(f"/api/upload/{body['upload_id']}/confirm", json={"mapping": _roles(body), "sheet": body["sheet"]})
    assert r.status_code == 200, r.text
    out = r.json()
    summary = out["summary"]
    truth = base()
    assert summary["n_customers"] >= 0.95 * truth["CustomerNo"].nunique()
    assert summary["rows_used"] > 0.9 * len(truth)
    assert out["n_customers"] == summary["n_customers"]


def test_letter_ids_run_through_every_screen_and_the_report():
    body = _inspect("erp")
    sid = client.post(f"/api/upload/{body['upload_id']}/confirm", json={"mapping": _roles(body), "sheet": body["sheet"]}).json()["session_id"]
    for path, params in [
        ("/api/overview", {}),
        ("/api/segments", {"k": 4}),
        ("/api/cltv", {}),
        ("/api/churn", {}),
        ("/api/value-risk", {}),
        ("/api/products", {}),
    ]:
        r = client.get(path, params={"session_id": sid, **params})
        assert r.status_code == 200, (path, r.text[:300])
    rows = client.get("/api/segments", params={"session_id": sid, "k": 4}).json()["rows"]
    assert str(rows[0]["CustomerNo"]).startswith("MUS-")
    product = client.get("/api/products", params={"session_id": sid}).json()["popular"][0]
    r = client.get("/api/recommendations", params={"session_id": sid, "product_id": product, "method": "cf"})
    assert r.status_code == 200, r.text[:300]
    assert client.get("/api/report", params={"session_id": sid}).status_code == 200
    assert client.get("/api/report.xlsx", params={"session_id": sid}).status_code == 200


def test_confirm_rejects_incomplete_mapping():
    body = _inspect("erp")
    mapping = _roles(body) | {"amount": None}
    r = client.post(f"/api/upload/{body['upload_id']}/confirm", json={"mapping": mapping, "sheet": body["sheet"]})
    assert r.status_code == 400
    assert "Birim fiyat ya da satır tutarı" in r.json()["detail"]


def test_reinspect_switches_sheet():
    body = _inspect("erp")
    r = client.post(f"/api/upload/{body['upload_id']}/inspect", json={"sheet": "Özet"})
    assert r.status_code == 200
    assert r.json()["sheet"] == "Özet"
    assert r.json()["problems"]


def test_number_and_id_helpers():
    assert to_number(pd.Series(["₺1.234,50", "12,5", "1.250"])).tolist() == [1234.5, 12.5, 1250.0]
    assert to_number(pd.Series(["$1,234.50", "9.99"])).tolist() == [1234.5, 9.99]
    assert normalize_ids(pd.Series(["00123", "A-1"])).tolist() == ["00123", "A-1"]
    assert normalize_ids(pd.Series(["12000.0", "7"])).tolist() == [12000, 7]


def test_ambiguous_dates_follow_the_chosen_order():
    s = pd.Series(["03/04/2024", "05/06/2024", "01/02/2024"])
    auto = parse_date_column(s)
    assert auto.ambiguous and auto.values.iloc[0].month == 4  # day-first by default
    assert parse_date_column(s, order="monthfirst").values.iloc[0].month == 3
    assert parse_date_column(pd.Series(["03/04/2024", "25/06/2024"])).ambiguous is False
