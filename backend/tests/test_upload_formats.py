"""Upload accepts the layouts the format guide promises, and rejects bad
files at upload time with a message the user can act on."""
import io

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.demo_data import generate_demo_transactions
from app.main import app

client = TestClient(app)


@pytest.fixture(scope="module")
def demo():
    return generate_demo_transactions(n_customers=150)


def _post(df: pd.DataFrame, name: str, **csv_kwargs):
    buf = io.BytesIO()
    if name.endswith(".csv"):
        buf.write(df.to_csv(index=False, **csv_kwargs).encode("utf-8-sig"))
    else:
        df.to_excel(buf, index=False)
    return client.post("/api/upload", files={"file": (name, buf.getvalue())})


def test_turkish_csv_with_semicolons_comma_decimals_and_dotted_dates(demo):
    df = demo.rename(
        columns={
            "CustomerNo": "Müşteri No",
            "TransactionNo": "Fatura No",
            "ProductNo": "Ürün Kodu",
            "ProductName": "Ürün Adı",
            "Quantity": "Adet",
            "Price": "Birim Fiyat",
            "Date": "Tarih",
            "Country": "Ülke",
        }
    )
    df["Tarih"] = pd.to_datetime(df["Tarih"], format="%m/%d/%Y").dt.strftime("%d.%m.%Y")
    df["Birim Fiyat"] = df["Birim Fiyat"].map(lambda v: f"{v:.2f}".replace(".", ","))
    response = _post(df, "magaza.csv", sep=";")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["has_product_id"] and body["has_country"]

    overview = client.get("/api/overview", params={"session_id": body["session_id"]})
    assert overview.status_code == 200


def test_online_retail_layout_with_iso_dates(demo):
    df = demo.rename(
        columns={
            "CustomerNo": "CustomerID",
            "TransactionNo": "InvoiceNo",
            "ProductNo": "StockCode",
            "ProductName": "Description",
            "Price": "UnitPrice",
            "Date": "InvoiceDate",
        }
    )
    df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"], format="%m/%d/%Y").dt.strftime("%Y-%m-%d %H:%M:%S")
    assert _post(df, "online_retail.csv").status_code == 200


def test_missing_column_is_named_in_turkish(demo):
    response = _post(demo.drop(columns=["Price"]), "eksik.xlsx")
    assert response.status_code == 400
    assert "Birim fiyat ya da satır tutarı" in response.json()["detail"]


def test_too_short_history_is_rejected(demo):
    dates = pd.to_datetime(demo["Date"], format="%m/%d/%Y")
    short = demo[dates < dates.min() + pd.Timedelta(days=60)]
    response = _post(short, "kisa.xlsx")
    assert response.status_code == 400
    assert "180" in response.json()["detail"]


def test_unreadable_dates_are_rejected(demo):
    response = _post(demo.assign(Date="geçen hafta"), "tarih.xlsx")
    assert response.status_code == 400
    assert "'Date' kolonundaki değerler tarih olarak okunamadı" in response.json()["detail"]


def test_country_filter_falls_back_when_country_absent(demo):
    from analyzewise_crm import DEFAULT_CONFIG
    from analyzewise_crm.recommender import compute_association_rules

    no_france = demo.assign(Country="Türkiye")
    assert len(compute_association_rules(no_france, DEFAULT_CONFIG)) > 0
