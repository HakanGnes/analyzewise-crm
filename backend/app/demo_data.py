"""Synthetic demo dataset for the "Demo veriyle dene" flow.

The real CrmData.xlsx is customer data and never goes into the repo, so a
visitor arriving from the portfolio has nothing to upload. This module
generates a realistic retail transaction table on the fly instead.

Unlike a uniformly random table, the generator plants real behavioural
structure so every screen shows something meaningful:

- customer archetypes (loyal, regular, occasional, fading, one-time) with
  different purchase rates — segmentation finds real groups
- "fading" customers whose purchase rate decays over time — the churn
  model has an actual signal to learn
- archetype-dependent basket value — CLTV has something to predict
- product bundles that are bought together — FP-Growth finds real rules

Output columns match the app's expected schema (DEFAULT_CONFIG.columns),
with dates as "%m/%d/%Y" strings exactly like the original Excel file.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

DEMO_FILENAME = "demo_magaza_verisi.xlsx"

_START = datetime(2019, 1, 1)
_DAYS = 365

# (name, share of customers, purchases per 30 days, avg basket multiplier, decays over time)
_ARCHETYPES = [
    ("loyal", 0.12, 3.2, 1.6, False),
    ("regular", 0.22, 1.4, 1.1, False),
    ("occasional", 0.26, 0.45, 0.9, False),
    ("fading", 0.22, 1.6, 1.0, True),
    ("one_time", 0.18, 0.0, 0.8, False),
]

_PRODUCTS = [
    "Seramik Kupa", "Çay Bardağı Seti", "Demlik", "Kahve Fincanı", "Bambu Tepsi",
    "Mumluk", "Kokulu Mum", "Dekoratif Vazo", "Çerçeve 13x18", "Çerçeve 20x25",
    "Yastık Kılıfı", "Pamuk Havlu", "El Havlusu", "Mutfak Önlüğü", "Fırın Eldiveni",
    "Saklama Kabı", "Cam Kavanoz", "Baharatlık", "Kesme Tahtası", "Servis Kaşığı",
    "Defter A5", "Kalem Seti", "Ajanda", "Hediye Kutusu", "Hediye Paketi Kağıdı",
    "Bez Çanta", "Anahtarlık", "Duvar Saati", "Masa Lambası", "Peçetelik",
]

# Product id -> base unit price
_PRICES = {
    1000 + i: p
    for i, p in enumerate(
        [6.5, 18.0, 22.0, 9.5, 14.0, 7.0, 11.5, 24.0, 8.0, 12.5,
         13.0, 16.0, 7.5, 12.0, 9.0, 10.5, 6.0, 15.0, 13.5, 5.5,
         4.5, 8.5, 17.0, 6.0, 3.5, 9.5, 4.0, 28.0, 32.0, 5.0]
    )
}

# Bundles: when the first item is in a basket, the others are likely too
_BUNDLES = [
    ([1001, 1002, 1003], 0.55),  # çay bardağı + demlik + kahve fincanı
    ([1005, 1006], 0.6),          # mumluk + kokulu mum
    ([1008, 1009], 0.5),          # iki çerçeve boyu
    ([1011, 1012], 0.55),         # havlu + el havlusu
    ([1013, 1014], 0.6),          # önlük + fırın eldiveni
    ([1015, 1016, 1017], 0.45),   # saklama kabı + kavanoz + baharatlık
    ([1020, 1021, 1022], 0.5),    # defter + kalem + ajanda
    ([1023, 1024], 0.65),         # hediye kutusu + paket kağıdı
]

_COUNTRIES = ["United Kingdom", "France", "Germany", "Netherlands"]
_COUNTRY_WEIGHTS = [0.55, 0.2, 0.15, 0.1]


def _basket(rng: np.random.Generator) -> list[int]:
    product_ids = list(_PRICES.keys())
    items = {int(rng.choice(product_ids))}
    for anchor_and_rest, prob in _BUNDLES:
        anchor, rest = anchor_and_rest[0], anchor_and_rest[1:]
        if anchor in items:
            for pid in rest:
                if rng.random() < prob:
                    items.add(pid)
    extra = rng.poisson(1.0)
    for _ in range(extra):
        items.add(int(rng.choice(product_ids)))
    return sorted(items)


def generate_demo_transactions(n_customers: int = 600, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    names, shares, rates, value_mults, decays = zip(*_ARCHETYPES)
    shares = np.array(shares) / np.sum(shares)

    rows = []
    txn_no = 500000
    for i in range(n_customers):
        customer_id = 12000 + i
        a = rng.choice(len(names), p=shares)
        rate, value_mult, decays_over_time = rates[a], value_mults[a], decays[a]
        country = str(rng.choice(_COUNTRIES, p=_COUNTRY_WEIGHTS))

        first_day = int(rng.integers(0, int(_DAYS * 0.93)))
        purchase_days = [first_day]

        if rate > 0:
            day = first_day
            # fading customers stop at a random point in the year
            stop_day = (
                first_day + int(rng.integers(30, 200)) if decays_over_time else _DAYS
            )
            while True:
                gap = rng.exponential(30.0 / rate)
                day += max(1, int(gap))
                if day >= min(stop_day, _DAYS):
                    break
                purchase_days.append(day)

        for day in purchase_days:
            date_str = (_START + timedelta(days=day)).strftime("%m/%d/%Y")
            for pid in _basket(rng):
                base = _PRICES[pid]
                price = round(base * rng.uniform(0.9, 1.1), 2)
                quantity = max(1, int(rng.poisson(2.0 * value_mult)))
                rows.append(
                    {
                        "TransactionNo": str(txn_no),
                        "Date": date_str,
                        "ProductNo": pid,
                        "ProductName": _PRODUCTS[pid - 1000],
                        "Price": price,
                        "Quantity": quantity,
                        "CustomerNo": customer_id,
                        "Country": country,
                    }
                )
            txn_no += 1

    return pd.DataFrame(rows)
