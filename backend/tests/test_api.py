import io
import random
from datetime import datetime, timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _make_demo_xlsx_bytes() -> bytes:
    random.seed(1)
    countries = ["France", "Germany", "United Kingdom"]
    products = [(1000 + i, f"Product {i}") for i in range(20)]
    start = datetime(2019, 1, 1)
    rows = []
    txn_no = 1
    for customer_id in range(1, 121):
        for _ in range(random.randint(1, 10)):
            date = start + timedelta(days=random.randint(0, 340))
            for _ in range(random.randint(1, 3)):
                product_id, product_name = random.choice(products)
                rows.append(
                    {
                        "CustomerNo": customer_id,
                        "TransactionNo": f"T{txn_no}",
                        "ProductNo": product_id,
                        "ProductName": product_name,
                        "Quantity": random.randint(1, 6),
                        "Price": round(random.uniform(2, 60), 2),
                        "Date": date.strftime("%m/%d/%Y"),
                        "Country": random.choice(countries),
                    }
                )
            txn_no += 1
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    return buf.getvalue()


@pytest.fixture(scope="module")
def session_id():
    content = _make_demo_xlsx_bytes()
    response = client.post(
        "/api/upload",
        files={"file": ("demo.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert response.status_code == 200
    return response.json()["session_id"]


def test_health():
    assert client.get("/api/health").json() == {"status": "ok"}


def test_upload_returns_session_info(session_id):
    assert session_id


def test_demo_endpoint_starts_a_usable_session():
    response = client.post("/api/demo")
    assert response.status_code == 200
    body = response.json()
    assert body["is_demo"] is True
    assert body["n_customers"] > 100
    overview = client.get("/api/overview", params={"session_id": body["session_id"]})
    assert overview.status_code == 200
    assert overview.json()["kpis"]["total_customers"] == body["n_customers"]


def test_upload_rejects_missing_columns():
    buf = io.BytesIO()
    pd.DataFrame({"foo": [1, 2]}).to_excel(buf, index=False)
    response = client.post("/api/upload", files={"file": ("bad.xlsx", buf.getvalue())})
    assert response.status_code == 400


def test_unknown_session_returns_404():
    response = client.get("/api/segments", params={"session_id": "does-not-exist"})
    assert response.status_code == 404


def test_overview_endpoint(session_id):
    response = client.get("/api/overview", params={"session_id": session_id})
    assert response.status_code == 200
    body = response.json()
    assert body["kpis"]["total_customers"] > 0
    assert len(body["monthly_trend"]) > 0


def test_segments_endpoint(session_id):
    response = client.get("/api/segments", params={"session_id": session_id, "k": 4})
    assert response.status_code == 200
    body = response.json()
    assert len(body["rows"]) > 0
    assert "segment" in body["rows"][0]


def test_cltv_endpoint_single_and_hurdle(session_id):
    for approach in ("single", "hurdle"):
        response = client.get("/api/cltv", params={"session_id": session_id, "approach": approach})
        assert response.status_code == 200
        assert len(response.json()["rows"]) > 0


def test_cltv_evaluate_endpoint(session_id):
    response = client.get("/api/cltv/evaluate", params={"session_id": session_id, "approach": "single"})
    assert response.status_code == 200
    body = response.json()
    assert "mae" in body
    assert "baseline_mae" in body


def test_churn_endpoint(session_id):
    response = client.get("/api/churn", params={"session_id": session_id})
    assert response.status_code == 200
    body = response.json()
    assert len(body["rows"]) > 0
    assert "risk_counts" in body


def test_churn_evaluate_endpoint(session_id):
    response = client.get("/api/churn/evaluate", params={"session_id": session_id})
    assert response.status_code == 200
    assert "roc_auc" in response.json()


def test_products_endpoint(session_id):
    response = client.get("/api/products", params={"session_id": session_id})
    assert response.status_code == 200
    assert len(response.json()["products"]) > 0


def test_recommendations_endpoint(session_id):
    products = client.get("/api/products", params={"session_id": session_id}).json()["products"]
    pid = products[0]
    for method in ("fpgrowth", "cf"):
        response = client.get(
            "/api/recommendations",
            params={"session_id": session_id, "product_id": pid, "method": method, "top_n": 3},
        )
        assert response.status_code == 200
        assert "recommendations" in response.json()


def test_delete_session(session_id):
    content = _make_demo_xlsx_bytes()
    upload_response = client.post("/api/upload", files={"file": ("demo2.xlsx", content)})
    sid = upload_response.json()["session_id"]
    response = client.delete(f"/api/sessions/{sid}")
    assert response.status_code == 200
    assert client.get("/api/segments", params={"session_id": sid}).status_code == 404
