"""Awkward real-world-style sales files built from the synthetic demo data:
what the column recognition has to cope with."""
import io
import numpy as np, pandas as pd
from app.demo_data import generate_demo_transactions

def base():
    d = generate_demo_transactions()
    d["Date"] = pd.to_datetime(d["Date"], format="%m/%d/%Y")
    return d

def erp_letters():
    """Letter customer codes, no invoice column, only a ₺ line total, Turkish headers, title rows, 2 sheets."""
    d = base()
    d["Cari Kodu"] = "MUS-" + d["CustomerNo"].astype(str).str.zfill(6)
    d["Satış Tarihi"] = d["Date"].dt.strftime("%d.%m.%Y")
    d["Stok Kodu"] = "STK" + d["ProductNo"].astype(str)
    d["Stok Adı"] = d["ProductName"]
    d["Miktar"] = d["Quantity"].astype(int)
    d["Tutar"] = (d["Quantity"] * d["Price"]).map(lambda v: f"₺{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    d["Şube"] = "Merkez"
    out = d[["Satış Tarihi", "Cari Kodu", "Stok Kodu", "Stok Adı", "Miktar", "Tutar", "Şube"]]
    buf = io.BytesIO()
    with pd.ExcelWriter(buf) as w:
        pd.DataFrame({"Özet": ["Toplam satır", "Dönem"], "Değer": [len(out), "2019"]}).to_excel(w, sheet_name="Özet", index=False)
        pd.DataFrame([["XYZ Mağazacılık — Satış Raporu"], ["Rapor tarihi: 01.01.2020"], [None]]).to_excel(w, sheet_name="Satışlar", index=False, header=False)
        out.to_excel(w, sheet_name="Satışlar", index=False, startrow=3)
    return buf.getvalue(), "erp_satis_raporu.xlsx"

def ecommerce_csv():
    """English e-commerce export: emails as customers, order ids with letters, ISO datetime, comma thousands."""
    d = base()
    d["customer_email"] = "user" + d["CustomerNo"].astype(str) + "@mail.com"
    d["order_id"] = "ORD-" + d["TransactionNo"].astype(str)
    d["created_at"] = (d["Date"] + pd.to_timedelta(np.random.default_rng(0).integers(0, 86400, len(d)), unit="s")).dt.strftime("%Y-%m-%dT%H:%M:%S")
    d["sku"] = d["ProductNo"]; d["product"] = d["ProductName"]; d["qty"] = d["Quantity"].astype(int)
    d["unit_price"] = d["Price"].map(lambda v: f"${v:,.2f}")
    out = d[["order_id", "created_at", "customer_email", "sku", "product", "qty", "unit_price"]]
    return out.to_csv(index=False).encode(), "shopify_orders.csv"

def online_retail():
    """UCI Online Retail style with cancellations and missing customers."""
    d = base()
    d = d.rename(columns={"TransactionNo": "InvoiceNo", "ProductNo": "StockCode", "ProductName": "Description",
                          "Price": "UnitPrice", "Date": "InvoiceDate", "CustomerNo": "CustomerID"})
    d["CustomerID"] = d["CustomerID"].astype(float)
    d.loc[d.sample(frac=0.05, random_state=1).index, "CustomerID"] = np.nan
    canc = d.sample(frac=0.02, random_state=2).copy()
    canc["InvoiceNo"] = "C" + canc["InvoiceNo"].astype(str); canc["Quantity"] = -canc["Quantity"]
    d = pd.concat([d, canc])
    d["InvoiceNo"] = d["InvoiceNo"].astype(str)
    d["InvoiceDate"] = d["InvoiceDate"].dt.strftime("%m/%d/%Y %H:%M")
    return d.to_csv(index=False, sep=";").encode("cp1254"), "online_retail.csv"

def unknown_names():
    """Headers the system can't know: content must carry it."""
    d = base()
    out = pd.DataFrame({"Kod": "K" + d["CustomerNo"].astype(str), "Zaman": d["Date"].dt.strftime("%Y-%m-%d"),
                        "Ne aldı": d["ProductName"], "Kaç tane": d["Quantity"].astype(int), "Para": (d["Quantity"]*d["Price"]).round(2)})
    return out.to_csv(index=False).encode(), "garip_basliklar.csv"


ALL = {"erp": erp_letters, "ecommerce": ecommerce_csv, "online_retail": online_retail, "unknown_names": unknown_names}
