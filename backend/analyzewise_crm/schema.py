"""Understanding an arbitrary sales file.

People export sales data from very different systems (ERP, POS, e-commerce
panels, hand-made Excel sheets), so the uploaded file rarely looks like the
template. This module turns "some table" into the standard transaction
table the analysis expects, in three steps:

  1. read_table      — find the right sheet and header row, decode CSVs in
                       any common encoding/delimiter.
  2. suggest_mapping — guess which column plays which role (customer,
                       invoice, date, quantity, price / line total, product,
                       country) from the column NAME and its CONTENT, with a
                       confidence level per guess.
  3. apply_mapping   — build the standard table, tolerating letter/number
                       IDs, a missing invoice column, a line-total column
                       instead of unit price, Turkish number formats,
                       currency symbols and most date layouts; and report
                       how many rows were used or skipped and why.

The web app shows step 2's guesses to the user for confirmation before
step 3 runs, so a wrong guess costs one click instead of a wrong analysis.
"""
from __future__ import annotations

import difflib
import io
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .config import AnalysisConfig, DEFAULT_CONFIG

MIN_HISTORY_DAYS = 180

# Role -> (Turkish label, required?, help text shown under the dropdown)
ROLES: Dict[str, dict] = {
    "customer_id": {"label": "Müşteri", "required": True,
                    "help": "Müşteriyi tanımlayan no, kod ya da e-posta. Harf ve rakam karışık olabilir."},
    "transaction_id": {"label": "Fatura / sipariş", "required": False,
                       "help": "Yoksa aynı müşterinin aynı gündeki satırları tek alışveriş sayılır."},
    "date": {"label": "Tarih", "required": True, "help": "İşlem tarihi; saat varsa yok sayılır."},
    "quantity": {"label": "Adet", "required": False, "help": "Yoksa her satır 1 adet sayılır."},
    "price": {"label": "Birim fiyat", "required": False,
              "help": "Birim fiyat ya da satır tutarından en az biri gerekir."},
    "amount": {"label": "Satır tutarı", "required": False,
               "help": "Satırın toplam tutarı (adet × fiyat). Birim fiyat yoksa buradan hesaplanır."},
    "product_id": {"label": "Ürün kodu", "required": False, "help": "Ürün önerisi ekranı için gerekir."},
    "product_name": {"label": "Ürün adı", "required": False, "help": "Önerilerde kod yerine görünür."},
    "country": {"label": "Ülke / bölge", "required": False, "help": "İsteğe bağlı."},
}

# Normalised names (lower-case, Turkish letters folded, only a-z0-9).
ALIASES: Dict[str, List[str]] = {
    "customer_id": [
        "customerno", "customerid", "customer", "customercode", "customernumber", "clientid", "client", "userid",
        "memberid", "musterino", "musteriid", "musterikodu", "musterinumarasi", "musteri", "carikod", "carikodu",
        "carino", "cari", "uyeno", "uyeid", "kullaniciid", "email", "eposta", "mail",
    ],
    "transaction_id": [
        "transactionno", "transactionid", "transaction", "invoiceno", "invoice", "invoiceid", "invoicenumber",
        "orderno", "orderid", "ordernumber", "order", "receiptno", "receipt", "basketid", "islemno", "islemid",
        "siparisno", "siparisid", "siparis", "faturano", "fatura", "fisno", "fis", "belgeno", "evrakno", "sepetno",
    ],
    "date": [
        "date", "invoicedate", "orderdate", "transactiondate", "purchasedate", "salesdate", "datetime", "createdat",
        "tarih", "islemtarihi", "siparistarihi", "faturatarihi", "satistarihi", "belgetarihi", "fistarihi",
    ],
    "quantity": ["quantity", "qty", "units", "adet", "adeti", "miktar", "satismiktari", "satisadedi"],
    "price": [
        "price", "unitprice", "salesprice", "fiyat", "birimfiyat", "birimfiyati", "satisfiyati", "fiyati",
    ],
    "amount": [
        "amount", "total", "totalprice", "totalamount", "linetotal", "lineamount", "revenue", "sales", "salesamount",
        "netamount", "tutar", "toplam", "toplamtutar", "satistutari", "nettutar", "ciro", "satirtutari",
    ],
    "product_id": [
        "productno", "productid", "productcode", "stockcode", "sku", "itemid", "itemcode", "barcode", "urunno",
        "urunkodu", "urunid", "stokkodu", "stokno", "barkod", "malzemekodu", "malkodu",
    ],
    "product_name": [
        "productname", "description", "itemname", "product", "item", "urunadi", "urunismi", "urun", "stokadi",
        "malzemeadi", "aciklama",
    ],
    "country": ["country", "region", "ulke", "bolge", "sehir", "city", "il"],
}

_FOLD = str.maketrans({"ı": "i", "İ": "i", "ü": "u", "Ü": "u", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
                       "ç": "c", "Ç": "c", "ö": "o", "Ö": "o"})


def name_key(name: object) -> str:
    text = str(name).translate(_FOLD).lower()
    return "".join(ch for ch in text if ch.isascii() and ch.isalnum())


# ---------------------------------------------------------------- reading

@dataclass
class Table:
    df: pd.DataFrame
    sheets: List[str]
    sheet: Optional[str]
    header_row: int  # 0-based row index in the original sheet


def _decode(content: bytes) -> str:
    for enc in ("utf-8-sig", "cp1254", "latin-1"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _find_header_row(raw: pd.DataFrame, scan: int = 15) -> int:
    """Exports often start with a title, a date range or blank lines above
    the real header. The header is the first row that is mostly text and
    about as wide as the data below it."""
    head = raw.head(scan)
    width = int(raw.notna().sum(axis=1).max() or 0)
    if width == 0:
        return 0
    for i, row in head.iterrows():
        cells = row.dropna()
        texts = [c for c in cells if isinstance(c, str) and c.strip() and not _looks_numeric(c)]
        if len(cells) >= max(2, 0.6 * width) and len(texts) >= 0.8 * len(cells):
            return int(i)
    return 0


def _looks_numeric(text: str) -> bool:
    return bool(re.fullmatch(r"[\s\-+]?[\d.,]+", text.strip()))


def _frame_from_raw(raw: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
    raw = raw.dropna(how="all").dropna(axis=1, how="all")
    if raw.empty:
        return raw, 0
    header_pos = _find_header_row(raw.reset_index(drop=True))
    header_index = raw.index[header_pos]
    names, seen = [], {}
    for j, v in enumerate(raw.loc[header_index].tolist()):
        name = str(v).strip() if pd.notna(v) and str(v).strip() else f"Kolon {j + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name} ({seen[name]})"
        else:
            seen[name] = 1
        names.append(name)
    df = raw.loc[raw.index > header_index].copy()
    df.columns = names
    df = df.dropna(how="all").reset_index(drop=True)
    return df, int(header_index)


def read_table(content: bytes, filename: str, sheet: Optional[str] = None) -> Table:
    name = filename.lower()
    if name.endswith((".csv", ".txt", ".tsv")):
        text = _decode(content)
        try:
            raw = pd.read_csv(io.StringIO(text), sep=None, engine="python", header=None, dtype=str,
                              skip_blank_lines=False)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"CSV dosyası okunamadı: {exc}") from exc
        df, header = _frame_from_raw(raw)
        return Table(df, [], None, header)
    if name.endswith((".xlsx", ".xlsm", ".xls")):
        try:
            book = pd.read_excel(io.BytesIO(content), sheet_name=None, header=None)
        except ImportError as exc:
            raise ValueError("Eski .xls biçimi okunamadı. Dosyayı Excel'de .xlsx olarak kaydedip tekrar yükleyin.") from exc
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Excel dosyası okunamadı: {exc}") from exc
        sheets = list(book.keys())
        if sheet is None:
            # the sheet with the most filled rows is almost always the data
            sheet = max(sheets, key=lambda s: int(book[s].dropna(how="all").shape[0]))
        elif sheet not in book:
            raise ValueError(f"'{sheet}' adlı sayfa dosyada yok.")
        df, header = _frame_from_raw(book[sheet])
        return Table(df, [str(s) for s in sheets], str(sheet), header)
    raise ValueError("Desteklenmeyen dosya türü. Lütfen .xlsx, .xls ya da .csv yükleyin.")


# ---------------------------------------------------------------- values

_CURRENCY = re.compile(r"(?i)(₺|tl|try|usd|eur|gbp|\$|€|£|\s| )")


def to_number(series: pd.Series) -> pd.Series:
    """Numbers as people type them: '1.234,50 ₺', '1,234.50', '12,5', '$9.99'.
    Which of ',' and '.' is the decimal mark is decided per column, so
    '1.250' in a Turkish column is one thousand two hundred fifty."""
    if pd.api.types.is_numeric_dtype(series):
        return series.astype(float)
    numeric = pd.to_numeric(series, errors="coerce")
    is_text = series.map(lambda v: isinstance(v, str))
    text = series[is_text].astype(str).str.replace(_CURRENCY, "", regex=True)
    if text.empty:
        return numeric.astype(float)

    both = text[text.str.contains(",") & text.str.contains(r"\.")]
    comma_last = (both.str.rfind(",") > both.str.rfind(".")).mean() if len(both) else np.nan
    only_comma = text[text.str.contains(",") & ~text.str.contains(r"\.")]
    if not np.isnan(comma_last):
        comma_decimal = comma_last >= 0.5
    elif len(only_comma):
        thousands_like = only_comma.str.fullmatch(r"-?\d{1,3}(,\d{3})+").mean()
        comma_decimal = thousands_like < 0.9
    else:
        comma_decimal = False

    if comma_decimal:
        cleaned = text.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    else:
        cleaned = text.str.replace(",", "", regex=False)
    numeric.loc[text.index] = pd.to_numeric(cleaned, errors="coerce")
    return numeric.astype(float)


def _date_formats() -> List[Tuple[str, str]]:
    """(strptime format, human label) — day-first layouts before month-first,
    since Turkish files are day-first; month-first only wins when day-first
    can't read the column."""
    out = []
    times = ["", " %H:%M", " %H:%M:%S"]
    layouts = [
        ("%Y-%m-%d", "yıl-ay-gün (2026-10-22)"), ("%Y/%m/%d", "yıl/ay/gün (2026/10/22)"),
        ("%Y.%m.%d", "yıl.ay.gün (2026.10.22)"),
        ("%d.%m.%Y", "gün.ay.yıl (22.10.2026)"), ("%d/%m/%Y", "gün/ay/yıl (22/10/2026)"),
        ("%d-%m-%Y", "gün-ay-yıl (22-10-2026)"),
        ("%m/%d/%Y", "ay/gün/yıl (10/22/2026)"), ("%m-%d-%Y", "ay-gün-yıl (10-22-2026)"),
        ("%m.%d.%Y", "ay.gün.yıl (10.22.2026)"),
        ("%d.%m.%y", "gün.ay.yıl (22.10.26)"), ("%d/%m/%y", "gün/ay/yıl (22/10/26)"),
        ("%m/%d/%y", "ay/gün/yıl (10/22/26)"),
        ("%Y%m%d", "yılaygün (20261022)"),
    ]
    for fmt, label in layouts:
        for t in times:
            out.append((fmt + t, label))
    out.append(("%Y-%m-%dT%H:%M:%S", "ISO (2026-10-22T14:30:00)"))
    return out


DATE_FORMATS = _date_formats()
_DAY_FIRST = {"%d.%m", "%d/%m", "%d-%m"}
_MONTH_FIRST = {"%m/%d", "%m-%d", "%m.%d"}


def _plausible(parsed: pd.Series) -> pd.Series:
    """Keep dates between 1990 and 2100 (anything else is a number that
    happened to fit a format, e.g. invoice 581475 read as yyyymmdd) and
    return them in the nanosecond unit the rest of pandas expects."""
    parsed = pd.to_datetime(parsed, errors="coerce")
    years = parsed.dt.year
    return parsed.where((years >= 1990) & (years <= 2100)).astype("datetime64[ns]")


@dataclass
class DateParse:
    values: pd.Series
    share: float
    label: str
    ambiguous: bool = False  # both gün/ay and ay/gün read every value


def parse_date_column(series: pd.Series, order: str = "auto", allow_serial: bool = False) -> DateParse:
    """order: 'auto', 'dayfirst' or 'monthfirst' (used to settle ambiguous
    columns such as 03/04/2026 where every day is ≤ 12)."""
    s = series.dropna()
    if s.empty:
        return DateParse(pd.Series(pd.NaT, index=series.index), 0.0, "")
    if pd.api.types.is_datetime64_any_dtype(series):
        values = _plausible(series)
        return DateParse(values, float(values.notna().mean()), "Excel tarih hücresi")

    out = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    # Excel cells that already hold dates (mixed with text in object columns)
    is_dt = s.map(lambda v: isinstance(v, (pd.Timestamp, np.datetime64)) or hasattr(v, "year"))
    if is_dt.any():
        out.loc[s[is_dt].index] = _plausible(s[is_dt])
    rest = s[~is_dt]
    if rest.empty:
        return DateParse(out, float(out.notna().sum() / len(s)), "Excel tarih hücresi")

    numeric = pd.to_numeric(rest, errors="coerce")
    if allow_serial and numeric.notna().mean() > 0.98 and numeric.between(20000, 80000).mean() > 0.98:
        out.loc[rest.index] = _plausible(pd.to_datetime(numeric, unit="D", origin="1899-12-30"))
        return DateParse(out, float(out.notna().sum() / len(s)), "Excel seri numarası")

    text = rest.astype(str).str.strip()
    sample = text if len(text) <= 3000 else text.sample(3000, random_state=0)
    results = []
    for fmt, label in DATE_FORMATS:
        ok = _plausible(pd.to_datetime(sample, format=fmt, errors="coerce")).notna().mean()
        if ok > 0:
            results.append((ok, fmt, label))
    if not results:
        # Last resort for odd layouts ("22 Ekim 2026" excluded). dateutil is
        # slow and over-eager, so try it on a small sample first and only
        # trust it when nearly everything parses.
        dayfirst = order != "monthfirst"
        probe = _plausible(pd.to_datetime(sample.head(200), errors="coerce", format="mixed", dayfirst=dayfirst))
        if probe.notna().mean() < 0.9:
            return DateParse(out, float(out.notna().sum() / len(s)), "")
        out.loc[text.index] = _plausible(pd.to_datetime(text, errors="coerce", format="mixed", dayfirst=dayfirst))
        return DateParse(out, float(out.notna().sum() / len(s)), "karışık biçim")

    best_share = max(r[0] for r in results)
    top = [r for r in results if r[0] >= best_share - 1e-9]
    day = [r for r in top if r[1][:5] in _DAY_FIRST]
    month = [r for r in top if r[1][:5] in _MONTH_FIRST]
    ambiguous = bool(day and month)
    if ambiguous and order == "monthfirst":
        pick = month[0]
    elif ambiguous:
        pick = day[0]
    else:
        pick = top[0]
    out.loc[text.index] = _plausible(pd.to_datetime(text, format=pick[1], errors="coerce"))
    return DateParse(out, float(out.notna().sum() / len(s)), pick[2], ambiguous)


def normalize_ids(series: pd.Series) -> pd.Series:
    """Keep IDs as integers when every value is a plain whole number (so
    existing numeric IDs look the same as before), otherwise as trimmed
    text: 'C-1023', 'ahmet@x.com', '00123' (leading zeros kept)."""
    s = series.dropna()
    if s.empty:
        return series
    if pd.api.types.is_numeric_dtype(s) and (s == np.floor(s)).all():
        return series.astype("Int64")
    text = series.map(lambda v: v if pd.isna(v) else (str(int(v)) if isinstance(v, float) and v.is_integer() else str(v).strip()))
    text = text.str.replace(r"^(\d+)\.0+$", r"\1", regex=True)  # "12000.0" read from a CSV
    filled = text.dropna()
    filled = filled[filled != ""]
    if not filled.empty and filled.str.fullmatch(r"[1-9]\d{0,17}|0").all():
        return pd.to_numeric(text.replace("", np.nan), errors="coerce").astype("Int64")
    return text.replace("", np.nan)


# ---------------------------------------------------------------- profiling

@dataclass
class ColumnProfile:
    name: str
    samples: List[str]
    kind: str  # "tarih" | "sayı" | "metin"
    unique: int
    empty_share: float
    numeric_share: float
    integer_share: float
    median: Optional[float]
    date_share: float
    date_label: str
    date_ambiguous: bool
    letter_share: float
    avg_len: float


def _sample_text(v) -> str:
    if isinstance(v, pd.Timestamp) or hasattr(v, "strftime"):
        try:
            return v.strftime("%d.%m.%Y")
        except Exception:  # noqa: BLE001
            pass
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else f"{v:.10g}"
    return str(v)


def profile_columns(df: pd.DataFrame, date_order: str = "auto") -> List[ColumnProfile]:
    profiles = []
    n = max(len(df), 1)
    for col in df.columns:
        s = df[col]
        filled = s.dropna()
        if filled.dtype == object:
            filled = filled[filled.astype(str).str.strip() != ""]
        nums = to_number(filled) if len(filled) else pd.Series(dtype=float)
        numeric_share = float(nums.notna().mean()) if len(filled) else 0.0
        valid = nums.dropna()
        integer_share = float((valid == np.floor(valid)).mean()) if len(valid) else 0.0
        hint_date = any(a in name_key(col) for a in ("date", "tarih", "zaman", "time", "created"))
        # plain numbers (prices, IDs) can parse as yyyymmdd or Excel serials;
        # only treat a numeric column as a date when its name says so
        maybe_date = len(filled) and (hint_date or numeric_share <= 0.98 or pd.api.types.is_datetime64_any_dtype(filled))
        dp = parse_date_column(filled, order=date_order, allow_serial=hint_date) if maybe_date else None
        date_share = dp.share if dp else 0.0
        texts = filled.astype(str)
        letter_share = float(texts.str.contains(r"[A-Za-zÇĞİÖŞÜçğıöşü]").mean()) if len(texts) else 0.0
        kind = "tarih" if date_share >= 0.9 else ("sayı" if numeric_share >= 0.95 else "metin")
        samples = list(dict.fromkeys(_sample_text(v) for v in filled.head(50)))[:4]
        profiles.append(
            ColumnProfile(
                name=str(col),
                samples=samples,
                kind=kind,
                unique=int(filled.nunique()),
                empty_share=float(1 - len(filled) / n),
                numeric_share=numeric_share,
                integer_share=integer_share,
                median=float(valid.median()) if len(valid) else None,
                date_share=date_share,
                date_label=dp.label if dp and date_share >= 0.9 else "",
                date_ambiguous=bool(dp and dp.ambiguous and date_share >= 0.9),
                letter_share=letter_share,
                avg_len=float(texts.str.len().mean()) if len(texts) else 0.0,
            )
        )
    return profiles


# ---------------------------------------------------------------- matching

def _name_score(key: str, role: str) -> float:
    aliases = ALIASES[role]
    if key in aliases:
        return 3.0
    if any(len(a) >= 4 and (a in key or key in a) for a in aliases if len(key) >= 3):
        return 2.0
    if difflib.get_close_matches(key, aliases, n=1, cutoff=0.85):
        return 1.5
    return 0.0


def _content_fit(p: ColumnProfile, role: str, n_rows: int) -> Optional[float]:
    """None = this column can't play this role; otherwise a bonus."""
    if role == "date":
        return 2.0 if p.date_share >= 0.9 else None
    if p.kind == "tarih":
        return None
    if role in ("quantity", "price", "amount"):
        if p.numeric_share < 0.9:
            return None
        bonus = 0.5
        if role == "quantity" and p.integer_share >= 0.9 and (p.median or 0) <= 1000:
            bonus += 1.0
        if role in ("price", "amount") and p.integer_share < 0.9:
            bonus += 0.5
        return bonus
    if role in ("customer_id", "transaction_id", "product_id"):
        if p.numeric_share >= 0.95 and p.integer_share < 0.95:
            return None  # decimal numbers are amounts, not IDs
        if p.unique < 2:
            return None
        return 0.5 if p.unique < n_rows else 0.0
    if role == "product_name":
        return 1.0 if p.letter_share > 0.8 and p.avg_len >= 4 else (None if p.numeric_share > 0.95 else 0.0)
    if role == "country":
        return 0.5 if p.letter_share > 0.8 and p.unique <= 300 else None
    return 0.0


@dataclass
class Suggestion:
    column: Optional[str]
    confidence: str  # "yüksek" | "kontrol et" | "bulunamadı"
    reason: str


def suggest_mapping(df: pd.DataFrame, profiles: Optional[List[ColumnProfile]] = None) -> Dict[str, Suggestion]:
    profiles = profiles or profile_columns(df)
    n = len(df)
    candidates = []
    for p in profiles:
        key = name_key(p.name)
        for role in ROLES:
            fit = _content_fit(p, role, n)
            if fit is None:
                continue
            ns = _name_score(key, role)
            if ns == 0:
                continue
            candidates.append((ns + fit, ns, role, p))
    # a date column needs no name: if exactly one column reads as dates, use it
    date_cols = [p for p in profiles if p.date_share >= 0.9]
    if len(date_cols) == 1 and not any(c[2] == "date" for c in candidates):
        candidates.append((2.0, 0.0, "date", date_cols[0]))

    candidates.sort(key=lambda c: (-c[0], c[3].name))
    taken_roles, taken_cols, out = set(), set(), {}
    for total, ns, role, p in candidates:
        if role in taken_roles or p.name in taken_cols:
            continue
        taken_roles.add(role)
        taken_cols.add(p.name)
        if ns >= 3.0:
            conf, why = "yüksek", "kolon adı ve içeriği uyuyor"
        elif ns > 0:
            conf, why = "kontrol et", "kolon adı benziyor"
        else:
            conf, why = "kontrol et", "içeriği tarih olan tek kolon"
        out[role] = Suggestion(p.name, conf, why)

    _guess_numeric_roles(df, profiles, out, taken_cols)
    for role in ROLES:
        out.setdefault(role, Suggestion(None, "bulunamadı", ""))
    return out


def _guess_numeric_roles(df: pd.DataFrame, profiles: List[ColumnProfile], out: Dict[str, Suggestion], taken: set) -> None:
    """Columns with unhelpful names ('Kaç tane', 'Para'): guess from the
    numbers themselves, marked 'kontrol et'.

    quantity — small whole numbers.
    price vs line total — a unit price repeats across rows (same product,
    same price) while a line total varies with the quantity; so if dividing
    the column by the quantity makes it MORE repetitive, it was a total.
    """
    free = [p for p in profiles if p.name not in taken and p.kind == "sayı" and p.unique > 1]
    if "quantity" not in out:
        qty = [p for p in free if p.integer_share >= 0.98 and 0 < (p.median or 0) <= 100 and p.unique <= 1000]
        if qty:
            pick = min(qty, key=lambda p: p.unique)
            out["quantity"] = Suggestion(pick.name, "kontrol et", "küçük tam sayılar; adet gibi görünüyor")
            taken.add(pick.name)
            free = [p for p in free if p.name != pick.name]
    if "price" in out or "amount" in out:
        return
    money = [p for p in free if p.integer_share < 0.9 and (p.median or 0) > 0]
    if not money:
        return
    pick = max(money, key=lambda p: p.unique)
    role, why = "price", "ondalıklı tutarlar; birim fiyat gibi görünüyor"
    if "quantity" in out:
        values = to_number(df[pick.name])
        qty = to_number(df[out["quantity"].column])
        per_unit = (values / qty.where(qty > 0)).round(2)
        if per_unit.nunique() < 0.8 * values.round(2).nunique():
            role, why = "amount", "adede bölününce tekrar eden değerler çıkıyor; satır tutarı gibi görünüyor"
    out[role] = Suggestion(pick.name, "kontrol et", why)
    taken.add(pick.name)


def unreadable_hints(profiles: List[ColumnProfile], suggestions: Dict[str, Suggestion]) -> List[str]:
    """When a role wasn't found but a column is NAMED like it, the content
    is the problem — say which column and show a value, so the user knows
    what to fix instead of hunting for a 'missing' column."""
    hints = []
    checks = {"date": "tarih", "price": "sayı", "amount": "sayı", "quantity": "sayı"}
    for role, kind in checks.items():
        if suggestions[role].column:
            continue
        for p in profiles:
            if _name_score(name_key(p.name), role) >= 2 and p.name not in {s.column for s in suggestions.values()}:
                example = p.samples[0] if p.samples else ""
                what = "tarih" if kind == "tarih" else "sayı"
                hints.append(f"'{p.name}' kolonundaki değerler {what} olarak okunamadı (örnek: '{example}').")
                break
    return hints


def mapping_problems(mapping: Dict[str, Optional[str]]) -> List[str]:
    problems = []
    if not mapping.get("customer_id"):
        problems.append("Müşteriyi gösteren kolonu seçin.")
    if not mapping.get("date"):
        problems.append("Tarih kolonunu seçin.")
    if not mapping.get("price") and not mapping.get("amount"):
        problems.append("Birim fiyat ya da satır tutarı kolonlarından birini seçin.")
    used = [c for c in mapping.values() if c]
    dupes = sorted({c for c in used if used.count(c) > 1})
    if dupes:
        problems.append("Aynı kolon birden fazla role atanmış: " + ", ".join(dupes) + ".")
    return problems


# ---------------------------------------------------------------- building

@dataclass
class BuildReport:
    rows_total: int
    rows_used: int
    skipped: Dict[str, int] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
    date_min: Optional[str] = None
    date_max: Optional[str] = None
    n_customers: int = 0
    n_transactions: int = 0

    def as_dict(self) -> dict:
        return {
            "rows_total": self.rows_total,
            "rows_used": self.rows_used,
            "skipped": self.skipped,
            "notes": self.notes,
            "date_min": self.date_min,
            "date_max": self.date_max,
            "n_customers": self.n_customers,
            "n_transactions": self.n_transactions,
        }


def apply_mapping(
    df: pd.DataFrame,
    mapping: Dict[str, Optional[str]],
    config: AnalysisConfig = DEFAULT_CONFIG,
    date_order: str = "auto",
) -> Tuple[pd.DataFrame, BuildReport]:
    """Build the standard transaction table. Raises ValueError (Turkish
    message) if the result can't be analysed."""
    problems = mapping_problems(mapping)
    if problems:
        raise ValueError(" ".join(problems))
    for role, col in mapping.items():
        if col and col not in df.columns:
            raise ValueError(f"'{col}' kolonu dosyada yok.")

    cols = config.columns
    report = BuildReport(rows_total=len(df), rows_used=0)
    out = pd.DataFrame(index=df.index)

    out[cols.customer_id] = normalize_ids(df[mapping["customer_id"]])
    dp = parse_date_column(df[mapping["date"]], order=date_order, allow_serial=True)
    out[cols.date] = pd.to_datetime(dp.values, errors="coerce")
    if dp.label:
        report.notes.append(f"Tarih biçimi: {dp.label}.")

    qty = to_number(df[mapping["quantity"]]) if mapping.get("quantity") else pd.Series(1.0, index=df.index)
    if not mapping.get("quantity"):
        report.notes.append("Adet kolonu yok; her satır 1 adet sayıldı.")
    if mapping.get("price"):
        price = to_number(df[mapping["price"]])
    else:
        amount = to_number(df[mapping["amount"]])
        price = amount / qty.where(qty > 0)
        report.notes.append("Birim fiyat, satır tutarı ÷ adet olarak hesaplandı.")
    out[cols.quantity] = qty
    out[cols.price] = price

    for role, target in (("product_id", cols.product_id), ("product_name", cols.product_name), ("country", cols.country)):
        if mapping.get(role):
            values = df[mapping[role]]
            out[target] = (
                normalize_ids(values) if role == "product_id"
                else values.map(lambda v: str(v).strip() if pd.notna(v) and str(v).strip() else np.nan)
            )

    if not mapping.get("product_id") and mapping.get("product_name"):
        out[cols.product_id] = out[cols.product_name]
        report.notes.append("Ürün kodu yok; ürün önerileri için ürün adı kod olarak kullanıldı.")

    # --- drop what can't be used, counting why
    missing_customer = out[cols.customer_id].isna()
    bad_date = ~missing_customer & out[cols.date].isna()
    bad_numbers = ~missing_customer & ~bad_date & (out[cols.quantity].isna() | out[cols.price].isna())
    non_positive = ~missing_customer & ~bad_date & ~bad_numbers & ((out[cols.quantity] <= 0) | (out[cols.price] <= 0))
    for label, mask in (
        ("müşteri bilgisi boş", missing_customer),
        ("tarih okunamadı", bad_date),
        ("adet ya da fiyat sayı değil", bad_numbers),
        ("adet ya da fiyat 0 veya negatif (iade / iptal)", non_positive),
    ):
        if int(mask.sum()):
            report.skipped[label] = int(mask.sum())
    out = out[~(missing_customer | bad_date | bad_numbers | non_positive)].copy()
    if out.empty:
        raise ValueError(
            "Seçilen kolonlarla kullanılabilir satır kalmadı. Müşteri, tarih ve fiyat/tutar kolonlarının doğru "
            "seçildiğini kontrol edin."
        )

    # IDs became clean only after dropping empty rows
    out[cols.customer_id] = normalize_ids(out[cols.customer_id].astype(object))
    if cols.product_id in out:
        out[cols.product_id] = normalize_ids(out[cols.product_id].astype(object))

    if mapping.get("transaction_id"):
        out[cols.transaction_id] = normalize_ids(df.loc[out.index, mapping["transaction_id"]])
        missing_tx = out[cols.transaction_id].isna()
        if missing_tx.any():
            report.skipped["fatura no boş"] = int(missing_tx.sum())
            out = out[~missing_tx]
    else:
        day = out[cols.date].dt.normalize()
        keys = out[cols.customer_id].astype(str) + "|" + day.astype(str)
        out[cols.transaction_id] = pd.factorize(keys)[0] + 1
        report.notes.append("Fatura no yok; aynı müşterinin aynı gündeki satırları tek alışveriş sayıldı.")

    for c in (cols.customer_id, cols.transaction_id) + ((cols.product_id,) if cols.product_id in out else ()):
        if str(out[c].dtype) == "Int64":
            out[c] = out[c].astype("int64") if not out[c].isna().any() else out[c].astype(object).where(out[c].notna(), np.nan)
        elif not pd.api.types.is_numeric_dtype(out[c]):
            out[c] = out[c].where(out[c].isna(), out[c].astype(str))

    span = (out[cols.date].max() - out[cols.date].min()).days
    if span < MIN_HISTORY_DAYS:
        raise ValueError(
            f"Kullanılabilir satırlar yalnızca {span} günü kapsıyor. CLTV ve churn modelleri 90 günlük geçmişe bakıp "
            f"sonraki 90 günü tahmin ettiği için en az {MIN_HISTORY_DAYS} günlük (tercihen 1 yıllık) işlem verisi gerekir."
            + (" Tarih sırası (gün/ay) yanlış seçilmiş olabilir." if dp.ambiguous else "")
        )

    ordered = [c for c in (cols.transaction_id, cols.date, cols.customer_id, cols.product_id, cols.product_name,
                           cols.quantity, cols.price, cols.country) if c in out.columns]
    out = out[ordered].reset_index(drop=True)
    report.rows_used = len(out)
    report.date_min = out[cols.date].min().strftime("%d.%m.%Y")
    report.date_max = out[cols.date].max().strftime("%d.%m.%Y")
    report.n_customers = int(out[cols.customer_id].nunique())
    report.n_transactions = int(out[cols.transaction_id].nunique())
    if report.n_customers < 50:
        report.notes.append(
            f"Yalnızca {report.n_customers} müşteri var; segmentasyon çalışır ama CLTV ve churn tahminleri az veriyle "
            "güvenilir olmayabilir."
        )
    return out, report


def auto_build(content: bytes, filename: str, config: AnalysisConfig = DEFAULT_CONFIG) -> Tuple[pd.DataFrame, BuildReport]:
    """Read, guess and build in one go (no confirmation step)."""
    table = read_table(content, filename)
    profiles = profile_columns(table.df)
    suggestions = suggest_mapping(table.df, profiles)
    mapping = {role: s.column for role, s in suggestions.items()}
    problems = mapping_problems(mapping)
    if problems:
        found = ", ".join(f"{ROLES[r]['label']} → {c}" for r, c in mapping.items() if c) or "hiçbiri"
        hints = unreadable_hints(profiles, suggestions)
        raise ValueError(
            "Kolonlar otomatik eşleştirilemedi. " + " ".join(hints + problems) + f" Bulunanlar: {found}."
        )
    return apply_mapping(table.df, mapping, config)
