"""Automatic CRM report.

Assembles what the user explored on the screens — with the settings they
chose there (segment count, CLTV approach) — into one document:

  1. Yönetici özeti   rule-based sentences built from the numbers
  2. Genel görünüm    KPIs + monthly revenue
  3. Segmentler       sizes, profile heatmap, suggested action per segment
  4. Müşteri değeri   Pareto concentration of predicted CLTV
  5. Churn riski      risk bands + risk × value matrix
  6. Öncelikli liste  valuable customers likely to leave
  7. Ürünler          strongest pairings + trend for the best seller
  8. Model kalitesi   how far to trust the numbers, and how they were tested

Every chart title states its finding (Wilke, "Fundamentals of Data
Visualization", ch. 22 and 29: a figure should make one point, and say it).

Outputs: a self-contained HTML page (charts inlined as SVG, opens offline,
print stylesheet for "Save as PDF") and an Excel workbook of the lists.
"""
from __future__ import annotations

import html
import io
from datetime import datetime

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from analyzewise_crm import DEFAULT_CONFIG
from analyzewise_crm.data import prepare_transactions
from analyzewise_crm.recommender import copurchase_trend, top_rules

from . import analysis
from . import report_charts as charts
from .store import Session

COLS = DEFAULT_CONFIG.columns

SEGMENT_ACTIONS = {
    "şampiyonlar": "Ayrıcalıkla ödüllendirin: yeni ürünlere erken erişim, sadakat programının üst kademesi. İndirim gerekmez.",
    "sadık müşteriler": "Çapraz satış önerileri ve kademeli sadakat ödülleriyle sepet değerini büyütün.",
    "potansiyel sadıklar": "Sadakat programına davet edin; üçüncü alışverişi teşvik eden kişisel teklif sunun.",
    "yeni müşteriler": "Hoş geldin serisi başlatın; ilk 30 gün içinde ikinci alışverişe yönlendirin.",
    "umut veren": "Ücretsiz kargo eşiği veya küçük bir teklifle alışveriş sıklığını artırın.",
    "ilgi gerek": "Kişiselleştirilmiş ürün önerileri ve sınırlı süreli kampanyalarla yeniden ilgilendirin.",
    "uykuya yakın": "Daha önce aldıkları ürünlerle ilgili hatırlatma ve kişisel indirim gönderin.",
    "riskte olanlar": "Kişisel geri kazanım mesajı ve yenileme teklifiyle hemen iletişime geçin.",
    "kaybedilmemeli": "Birebir iletişim kurun; güçlü bir geri kazanım teklifi sunun ve neden uzaklaştıklarını sorun.",
    "kış uykusundakiler": "Düşük maliyetli bir yeniden aktivasyon denemesi yapın; yanıt yoksa kampanya listesinden çıkarın.",
}

RISK_ORDER = ["düşük risk", "orta risk", "yüksek risk", "çok yüksek risk"]


def _int(v: float) -> str:
    return f"{v:,.0f}".replace(",", ".")


def _money(v: float) -> str:
    return _int(v)


def _pct(v: float, digits: int = 0) -> str:
    return "%" + f"{v * 100:.{digits}f}".replace(".", ",")


def _dec(v: float, digits: int = 2) -> str:
    return f"{v:.{digits}f}".replace(".", ",")


def cap(text: str) -> str:
    """Sentence-case a segment name at the start of a sentence (Turkish-aware for i/ı)."""
    if not text:
        return text
    first = {"i": "İ", "ı": "I"}.get(text[0], text[0].upper())
    return first + text[1:]


def revenue_change(revenue: list[float]) -> float:
    """Average of the last three months vs the first three. A single first
    month is often partial or unrepresentative, so comparing it with the
    last month exaggerates growth."""
    if len(revenue) < 2:
        return 0.0
    w = 3 if len(revenue) >= 6 else 1
    start, end = float(np.mean(revenue[:w])), float(np.mean(revenue[-w:]))
    return end / start - 1 if start else 0.0


# --------------------------------------------------------------------------- context


def build_context(session_id: str, session: Session, k: int | None, auto: bool, approach: str) -> dict:
    raw = session.raw_df
    names = analysis.product_names(session)
    tx = prepare_transactions(raw, DEFAULT_CONFIG)

    # overview
    monthly = tx.set_index(COLS.date).resample("MS").agg(revenue=("TotalPrice", "sum"))
    months = [d.strftime("%Y-%m") for d in monthly.index]
    revenue = monthly["revenue"].tolist()
    overview = {
        "customers": int(tx[COLS.customer_id].nunique()),
        "transactions": int(tx[COLS.transaction_id].nunique()),
        "revenue": float(tx["TotalPrice"].sum()),
        "aov": float(tx.groupby(COLS.transaction_id)["TotalPrice"].sum().mean()),
        "date_min": tx[COLS.date].min().strftime("%Y-%m-%d"),
        "date_max": tx[COLS.date].max().strftime("%Y-%m-%d"),
        "months": months,
        "monthly_revenue": revenue,
        "revenue_change": revenue_change(revenue),
    }

    # segments
    seg = analysis.segments(session_id, session, k, auto)
    seg_table = (
        seg.groupby("segment")
        .agg(customers=("recency", "size"), recency=("recency", "mean"), frequency=("frequency", "mean"),
             monetary=("monetary", "mean"))
        .sort_values("monetary", ascending=False)
    )
    seg_table["share"] = seg_table["customers"] / seg_table["customers"].sum()
    seg_table["action"] = [SEGMENT_ACTIONS.get(s, "") for s in seg_table.index]

    # value
    cltv = analysis.cltv(session_id, session, approach)
    cltv_m = analysis.cltv_metrics(session_id, session, approach)

    # churn
    churn = analysis.churn(session_id, session)
    churn_m = analysis.churn_metrics(session_id, session)
    risk_counts = churn["risk_segment"].astype(str).value_counts().to_dict()
    at_risk = risk_counts.get("yüksek risk", 0) + risk_counts.get("çok yüksek risk", 0)

    # risk × value
    vr = analysis.value_risk(session_id, session, approach)
    priority = vr[vr["quadrant"] == "değerli, riskte"].sort_values("historical_spend", ascending=False)

    # products
    has_products = COLS.product_id in raw.columns
    pairs = pd.DataFrame()
    trend = {"rows": pd.DataFrame(), "periods": []}
    best_seller = None
    if has_products:
        pairs = top_rules(analysis.rules(session_id, session), 10)
        if not pairs.empty:
            pairs["antecedent_name"] = pairs["antecedent"].map(lambda p: names.get(p, str(p)))
            pairs["consequent_name"] = pairs["consequent"].map(lambda p: names.get(p, str(p)))
        # Of the ten best sellers, show the one whose pairings moved most —
        # a flat slopegraph has nothing to say.
        basket_counts = raw.groupby(COLS.product_id)[COLS.transaction_id].nunique().sort_values(ascending=False)
        best_move = -1.0
        for candidate in basket_counts.index[:10]:
            t = copurchase_trend(raw, DEFAULT_CONFIG, candidate, 8)
            if len(t["rows"]) < 3:
                continue
            move = float((t["rows"]["rate_second"] - t["rows"]["rate_first"]).abs().max())
            if move > best_move:
                best_move, trend, best_seller = move, t, candidate

    return {
        "session": session,
        "names": names,
        "is_demo": session.filename.startswith("demo_"),
        "settings": {"k": "otomatik" if auto else (k or 6), "approach": approach},
        "overview": overview,
        "segments": seg,
        "seg_table": seg_table,
        "cltv": cltv,
        "cltv_metrics": cltv_m,
        "churn": churn,
        "churn_metrics": churn_m,
        "risk_counts": risk_counts,
        "at_risk": at_risk,
        "value_risk": vr,
        "priority": priority,
        "pairs": pairs,
        "trend": trend,
        "best_seller": best_seller,
        "generated_at": datetime.now(),
    }


def summary_sentences(ctx: dict) -> list[str]:
    o, st = ctx["overview"], ctx["seg_table"]
    n = o["customers"]
    out = [
        f"{o['date_min']} ile {o['date_max']} arasında {_int(n)} müşteri {_int(o['transactions'])} alışveriş yaptı; "
        f"toplam gelir {_money(o['revenue'])}, ortalama sepet {_money(o['aov'])}.",
    ]
    ch = o["revenue_change"]
    if abs(ch) >= 0.05:
        out.append(
            f"Son üç ayın ortalama aylık geliri, ilk üç aya göre {_pct(abs(ch))} {'yüksek' if ch > 0 else 'düşük'}."
        )

    largest = st["customers"].idxmax()
    top = st.index[0]
    out.append(
        f"Müşteriler {len(st)} segmente ayrıldı. En büyük grup {largest} ({_pct(st.loc[largest, 'share'])}); "
        f"en değerli grup ortalama {_money(st.loc[top, 'monetary'])} harcamayla {top}."
    )

    values = ctx["cltv"]["predicted_cltv"].to_numpy()
    if values.sum() > 0:
        v = np.sort(values)[::-1]
        top20 = v[: max(1, int(len(v) * 0.2))].sum() / v.sum()
        out.append(f"En değerli %20 müşteri, önümüzdeki 90 günün tahmini değerinin {_pct(top20)} kadarını getiriyor.")

    out.append(f"{_int(ctx['at_risk'])} müşteri ({_pct(ctx['at_risk'] / max(n, 1))}) yüksek veya çok yüksek churn riskinde.")

    pr = ctx["priority"]
    if len(pr):
        out.append(
            f"Bunların {_int(len(pr))} tanesi en çok harcayan %25'te: geçmişte toplam {_money(pr['historical_spend'].sum())} "
            f"harcamışlar. Öncelikli geri kazanım listesi 6. bölümde."
        )

    pairs = ctx["pairs"]
    if not pairs.empty:
        p = pairs.iloc[0]
        out.append(
            f"En güçlü ürün birlikteliği {p['antecedent_name']} ile {p['consequent_name']}: birlikte alınma olasılığı, "
            f"bağımsız olsalardı beklenenin {_dec(p['lift'], 1)} katı."
        )
    return out


def trend_headline(rows: pd.DataFrame, anchor: str, names: dict, threshold: float = 0.03) -> str:
    delta = rows["rate_second"] - rows["rate_first"]
    i_up, i_down = int(delta.idxmax()), int(delta.idxmin())
    name = lambda i: names.get(rows.loc[i, "product"], str(rows.loc[i, "product"]))  # noqa: E731
    up, down = delta.loc[i_up] >= threshold, delta.loc[i_down] <= -threshold
    if up and down:
        return (f"{anchor} alanlarda {name(i_up)} yükseliyor ({_pct(rows.loc[i_up, 'rate_first'])} → "
                f"{_pct(rows.loc[i_up, 'rate_second'])}), {name(i_down)} düşüyor ({_pct(rows.loc[i_down, 'rate_first'])} → "
                f"{_pct(rows.loc[i_down, 'rate_second'])})")
    if up:
        return (f"{anchor} alanlar arasında {name(i_up)} giderek daha çok tercih ediliyor "
                f"({_pct(rows.loc[i_up, 'rate_first'])} → {_pct(rows.loc[i_up, 'rate_second'])})")
    if down:
        return (f"{anchor} ile {name(i_down)} birlikteliği zayıflıyor "
                f"({_pct(rows.loc[i_down, 'rate_first'])} → {_pct(rows.loc[i_down, 'rate_second'])})")
    return f"{anchor} ile birlikte alınan ürünler iki dönemde de benzer"


# --------------------------------------------------------------------------- HTML


def _table(headers: list[str], rows: list[list], numeric: set[int] | None = None) -> str:
    numeric = numeric or set()
    head = "".join(f"<th{' class=num' if i in numeric else ''}>{html.escape(h)}</th>" for i, h in enumerate(headers))
    body = "".join(
        "<tr>" + "".join(f"<td{' class=num' if i in numeric else ''}>{html.escape(str(c))}</td>" for i, c in enumerate(r)) + "</tr>"
        for r in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _figure(title: str, svg: str, caption: str = "") -> str:
    cap = f"<figcaption>{html.escape(caption)}</figcaption>" if caption else ""
    return f'<figure><h3>{html.escape(title)}</h3><div class="chart">{svg}</div>{cap}</figure>'


def render_html(ctx: dict) -> str:
    o, st = ctx["overview"], ctx["seg_table"]
    cm, chm = ctx["cltv_metrics"], ctx["churn_metrics"]
    approach_label = "iki aşamalı (hurdle)" if ctx["settings"]["approach"] == "hurdle" else "tek aşamalı"
    sections: list[str] = []

    # 1 — summary
    bullets = "".join(f"<li>{html.escape(s)}</li>" for s in summary_sentences(ctx))
    kpis = "".join(
        f'<div class="kpi"><span>{label}</span><strong>{value}</strong></div>'
        for label, value in [
            ("Müşteri", _int(o["customers"])),
            ("Alışveriş", _int(o["transactions"])),
            ("Toplam gelir", _money(o["revenue"])),
            ("Ortalama sepet", _money(o["aov"])),
        ]
    )
    sections.append(f'<section><h2>1. Yönetici özeti</h2><ul class="summary">{bullets}</ul><div class="kpis">{kpis}</div></section>')

    # 2 — overview
    sections.append(
        "<section><h2>2. Genel görünüm</h2>"
        + _figure(
            (f"Son üç ayın aylık geliri ilk üç aydan {_pct(abs(o['revenue_change']))} "
             + ("yüksek" if o["revenue_change"] >= 0 else "düşük")),
            charts.monthly_revenue(o["months"], o["monthly_revenue"]),
            "Aylık toplam gelir; işaretli nokta en yüksek ay. Karşılaştırma ilk ve son üç ayın ortalamasıyla yapıldı.",
        )
        + "</section>"
    )

    # 3 — segments
    largest = st["customers"].idxmax()
    seg_rows = [
        [s, _int(r.customers), _pct(r.share), _int(r.recency), _dec(r.frequency, 1), _money(r.monetary), r.action]
        for s, r in st.iterrows()
    ]
    heat_values = st[["recency", "frequency", "monetary"]].to_numpy(dtype=float)
    sections.append(
        "<section><h2>3. Müşteri segmentleri</h2>"
        f"<p>K-Means kümeleme, {ctx['settings']['k']} segment. Segmentler son alışveriş zamanı, alışveriş sayısı ve toplam harcamaya göre oluştu.</p>"
        + _figure(
            f"En büyük grup {largest}: müşterilerin {_pct(st.loc[largest, 'share'])} kadarı",
            charts.horizontal_bars(list(st.index), st["customers"].tolist()),
            "Segmentlere göre müşteri sayısı.",
        )
        + _figure(
            f"{cap(st.index[0])} ortalama {_money(st.iloc[0]['monetary'])} harcamayla en değerli grup",
            charts.segment_heatmap(
                list(st.index),
                [("recency", "Son alışveriş (gün)", False),
                 ("frequency", "Alışveriş sayısı", True), ("monetary", "Ortalama harcama", True)],
                heat_values,
                [_int, lambda v: _dec(v, 1), _money],
            ),
            "Her sütun kendi aralığında renklendirildi; koyu renk o sütunda daha iyi müşteri demek.",
        )
        + "<h3>Segment bazında önerilen aksiyonlar</h3>"
        + _table(["Segment", "Müşteri", "Pay", "Son alışveriş (gün)", "Alışveriş", "Ort. harcama", "Önerilen aksiyon"],
                 seg_rows, numeric={1, 2, 3, 4, 5})
        + "</section>"
    )

    # 4 — value
    values = ctx["cltv"]["predicted_cltv"].to_numpy()
    pareto_svg, share20 = charts.pareto(values)
    top_cust = ctx["cltv"].sort_values("predicted_cltv", ascending=False).head(10)
    sections.append(
        "<section><h2>4. Müşteri değeri (CLTV)</h2>"
        f"<p>Önümüzdeki 90 gün için XGBoost tahmini, {approach_label} yaklaşım. Toplam tahmini değer {_money(values.sum())}.</p>"
        + '<div class="two">'
        + _figure(f"En değerli %20 müşteri, değerin {_pct(share20)} kadarını getiriyor", pareto_svg,
                  "Müşteriler değere göre sıralandığında birikimli pay. Gri köşegen, değerin eşit dağıldığı durum.")
        + "<div><h3>En yüksek tahmini değerli 10 müşteri</h3>"
        + _table(["Müşteri No", "Tahmini CLTV", "Alışveriş"],
                 [[str(i), _money(r.predicted_cltv), _int(r.frequency)] for i, r in top_cust.iterrows()], numeric={1, 2})
        + "</div></div></section>"
    )

    # 5 — churn
    vr = ctx["value_risk"]
    sections.append(
        "<section><h2>5. Churn riski</h2>"
        + _figure(
            f"Müşterilerin {_pct(ctx['at_risk'] / max(o['customers'], 1))} kadarı yüksek veya çok yüksek riskte",
            charts.risk_share(ctx["risk_counts"]),
            "Önümüzdeki 90 günde geri gelmeme olasılığına göre risk grupları.",
        )
        + _figure(
            (f"{_int(len(ctx['priority']))} değerli müşteri gitmek üzere" if len(ctx["priority"]) else "Gitmek üzere olan değerli müşteri yok"),
            charts.value_risk_scatter(vr["churn_probability"], vr["historical_spend"], vr["quadrant"],
                                      analysis.HIGH_RISK, vr.attrs.get("value_cut", 0.0)),
            "Kırmızı: harcaması en üst %25'te ve churn olasılığı %50 ve üzeri. %100'deki dikey sütun son 90 günde hiç "
            "alışveriş yapmamış müşterilerdir. Değer ekseni geçmiş harcamadır; tahmini CLTV zaten gitme ihtimalini "
            "içerdiği için riskli müşterilerde hep düşük çıkar.",
        )
        + "</section>"
    )

    # 6 — priority list
    pr = ctx["priority"].head(25)
    if len(pr):
        rows = [[str(i), _money(r.historical_spend), _pct(r.churn_probability), _int(r.recency), _int(r.frequency)]
                for i, r in pr.iterrows()]
        sections.append(
            "<section><h2>6. Öncelikli geri kazanım listesi</h2>"
            f"<p>Geçmişte çok harcamış ve gitme olasılığı yüksek {_int(len(ctx['priority']))} müşteri, geçmiş harcamaya göre sıralı"
            f"{' (ilk 25)' if len(ctx['priority']) > 25 else ''}. Tam liste Excel çıktısında.</p>"
            + _table(["Müşteri No", "Geçmiş harcama", "Churn olasılığı", "Son alışveriş (gün)", "Alışveriş"], rows,
                     numeric={1, 2, 3, 4})
            + "</section>"
        )
    else:
        sections.append("<section><h2>6. Öncelikli geri kazanım listesi</h2><p>Bu dönemde hem değerli hem yüksek riskli müşteri bulunmadı.</p></section>")

    # 7 — products
    if ctx["pairs"] is not None and not ctx["pairs"].empty:
        pairs = ctx["pairs"]
        labels = [f"{a} + {b}" for a, b in zip(pairs["antecedent_name"], pairs["consequent_name"])]
        body = _figure(
            f"En güçlü birliktelik: {labels[0]} ({_dec(pairs.iloc[0]['lift'], 1)} kat)",
            charts.horizontal_bars(labels, pairs["lift"].tolist(), value_fmt=lambda v: _dec(v, 1) + "×"),
            "Lift: iki ürünün aynı sepette görülme olasılığı, bağımsız olsalardı beklenenin kaç katı.",
        )
        t = ctx["trend"]
        if ctx["best_seller"] is not None and len(t["rows"]):
            rows = t["rows"]
            anchor = ctx["names"].get(ctx["best_seller"], str(ctx["best_seller"]))
            title = trend_headline(rows, anchor, ctx["names"])
            body += _figure(
                title,
                charts.slopegraph([ctx["names"].get(p, str(p)) for p in rows["product"]],
                                  rows["rate_first"].tolist(), rows["rate_second"].tolist(), t["periods"]),
                f"En çok satan on üründen, birliktelikleri en çok değişen {anchor}: onu içeren sepetlerin yüzde kaçında diğer ürün de vardı. "
                "Mavi yükselen, kırmızı düşen eşleşme; gri belirgin değişim yok.",
            )
        sections.append(f"<section><h2>7. Ürün önerileri</h2>{body}</section>")

    # 8 — model quality
    demo_note = (
        '<p class="note">Bu rapor dahili sentetik demo verisiyle üretildi; rakamlar gerçek bir işletmeyi yansıtmaz.</p>'
        if ctx["is_demo"] else ""
    )
    sections.append(
        "<section><h2>8. Model kalitesi ve yöntem</h2>"
        + _table(
            ["Model", "Ölçüt", "Sonuç", "Nasıl okunur"],
            [
                ["Churn (XGBoost sınıflandırıcı)", "ROC AUC", _dec(chm["roc_auc"], 2),
                 "0,50 rastgele tahmin, 1,00 kusursuz ayrım. 0,70 üstü iyi."],
                ["CLTV (XGBoost, " + approach_label + ")", "Ortalama mutlak hata", _dec(cm["mae"], 1),
                 f"Herkese ortalamayı söylemek {_dec(cm['baseline_mae'], 1)} hata yapardı."],
                ["CLTV", "Basit yaklaşıma göre iyileşme", _pct(cm["improvement_over_baseline"]),
                 "%20 üstü, modelin gerçek bir sinyal yakaladığını gösterir."],
            ],
            numeric={2},
        )
        + "<p>Modeller kayan pencerelerle eğitildi: müşterinin son 90 gününe bakılıp sonraki 90 günü tahmin edildi. "
        "Skorlar eğitimde hiç görülmemiş müşteriler üzerinde ölçüldü; bir müşterinin farklı dönemleri hiçbir zaman hem "
        "eğitimde hem testte yer almadı, bu yüzden veri sızıntısı içermez.</p>"
        + demo_note
        + "</section>"
    )

    title = "CRM Raporu"
    source = "Demo veri seti" if ctx["is_demo"] else ctx["session"].filename
    generated = ctx["generated_at"].strftime("%d.%m.%Y %H:%M")
    return REPORT_TEMPLATE.format(
        title=html.escape(title),
        source=html.escape(source),
        period=f"{o['date_min']} – {o['date_max']}",
        generated=generated,
        sections="\n".join(sections),
    )


REPORT_TEMPLATE = """<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — AnalyzeWise</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {{ --ink:#111827; --soft:#4b5563; --faint:#6b7280; --line:#e5e7eb; --brand:#4f46e5; --mist:#f5f6fa; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--mist); color:var(--ink); font:14px/1.6 Inter, "Segoe UI", system-ui, sans-serif; }}
  .page {{ max-width: 860px; margin: 32px auto; background:#fff; border:1px solid var(--line); border-radius:12px; padding: 48px 56px; }}
  header.cover {{ border-bottom:1px solid var(--line); padding-bottom:20px; margin-bottom:8px; display:flex; justify-content:space-between; gap:24px; align-items:flex-end; flex-wrap:wrap; }}
  .brand {{ font-weight:700; font-size:15px; color:var(--brand); margin:0 0 10px; }}
  h1 {{ font-size:30px; margin:0; letter-spacing:-0.01em; }}
  .meta {{ color:var(--faint); font-size:13px; margin:6px 0 0; }}
  .toolbar button {{ font:inherit; font-weight:600; background:var(--brand); color:#fff; border:0; border-radius:8px; padding:9px 16px; cursor:pointer; }}
  section {{ padding: 26px 0 8px; border-bottom:1px solid var(--line); }}
  section:last-child {{ border-bottom:0; }}
  h2 {{ font-size:20px; margin:0 0 10px; }}
  h3 {{ font-size:14.5px; margin:18px 0 8px; }}
  p {{ color:var(--soft); margin: 6px 0 10px; max-width: 72ch; }}
  ul.summary {{ margin:0; padding-left:18px; }}
  ul.summary li {{ margin: 0 0 8px; max-width: 72ch; }}
  .kpis {{ display:grid; grid-template-columns: repeat(4, 1fr); gap:12px; margin:18px 0 10px; }}
  .kpi {{ border:1px solid var(--line); border-radius:8px; padding:12px 14px; }}
  .kpi span {{ display:block; color:var(--faint); font-size:12px; }}
  .kpi strong {{ font-size:20px; }}
  figure {{ margin: 8px 0 18px; break-inside: avoid; }}
  figure .chart svg {{ width:100%; height:auto; display:block; }}
  figcaption {{ color:var(--faint); font-size:12px; margin-top:4px; max-width: 80ch; }}
  .two {{ display:grid; grid-template-columns: 1fr 1fr; gap:24px; align-items:start; }}
  table {{ width:100%; border-collapse:collapse; font-size:12.5px; margin: 4px 0 14px; break-inside: auto; }}
  th {{ text-align:left; color:var(--faint); font-weight:600; font-size:11.5px; border-bottom:1px solid var(--line); padding:7px 8px; }}
  td {{ border-bottom:1px solid var(--line); padding:7px 8px; vertical-align:top; }}
  tr {{ break-inside: avoid; }}
  .num {{ text-align:right; font-variant-numeric: tabular-nums; white-space:nowrap; }}
  .note {{ background:#fffbeb; border:1px solid #fde68a; color:#92400e; padding:10px 12px; border-radius:8px; }}
  footer {{ color:var(--faint); font-size:12px; margin-top:18px; }}
  @media (max-width: 720px) {{ .page {{ padding: 24px 18px; margin:0; border-radius:0; }} .kpis, .two {{ grid-template-columns: 1fr 1fr; }} .two {{ grid-template-columns: 1fr; }} }}
  @media print {{
    @page {{ size: A4; margin: 14mm; }}
    body {{ background:#fff; }}
    .page {{ margin:0; border:0; padding:0; max-width:none; }}
    .toolbar {{ display:none; }}
    section {{ break-inside: auto; }}
    h2, h3 {{ break-after: avoid; }}
  }}
</style>
</head>
<body>
<div class="page">
  <header class="cover">
    <div>
      <p class="brand">AnalyzeWise CRM</p>
      <h1>{title}</h1>
      <p class="meta">Kaynak: {source}<br>Veri dönemi: {period}<br>Oluşturulma: {generated}</p>
    </div>
    <div class="toolbar"><button onclick="window.print()">Yazdır / PDF olarak kaydet</button></div>
  </header>
  {sections}
  <footer>AnalyzeWise CRM tarafından otomatik oluşturuldu.</footer>
</div>
</body>
</html>
"""


# --------------------------------------------------------------------------- Excel


def render_xlsx(ctx: dict) -> bytes:
    wb = Workbook()
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="4F46E5")

    def sheet(title: str, headers: list[str], rows: list[list], widths: list[int] | None = None, first: bool = False):
        ws = wb.active if first else wb.create_sheet()
        ws.title = title
        ws.append(headers)
        for cell in ws[1]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(vertical="center")
        for r in rows:
            ws.append(r)
        ws.freeze_panes = "A2"
        for i, w in enumerate(widths or [], start=1):
            ws.column_dimensions[get_column_letter(i)].width = w
        return ws

    sheet("Özet", ["Bulgu"], [[s] for s in summary_sentences(ctx)], [120], first=True)

    st = ctx["seg_table"]
    sheet(
        "Segmentler",
        ["Segment", "Müşteri", "Pay", "Ort. son alışveriş (gün)", "Ort. alışveriş sayısı", "Ort. harcama", "Önerilen aksiyon"],
        [[s, int(r.customers), round(float(r.share), 4), round(float(r.recency), 1), round(float(r.frequency), 2),
          round(float(r.monetary), 2), r.action] for s, r in st.iterrows()],
        [22, 10, 8, 22, 20, 14, 90],
    )

    seg = ctx["segments"]
    vr = ctx["value_risk"]
    cust = seg[["segment", "recency", "frequency", "monetary"]].join(
        vr[["predicted_cltv", "churn_probability", "historical_spend", "quadrant"]], how="left"
    ).join(ctx["churn"][["risk_segment"]], how="left")
    sheet(
        "Müşteriler",
        ["Müşteri No", "Segment", "Son alışveriş (gün)", "Alışveriş sayısı", "Harcama", "Tahmini CLTV (90 gün)",
         "Churn olasılığı", "Risk grubu", "Geçmiş toplam harcama", "Risk × değer"],
        [[int(i) if str(i).isdigit() else str(i), r.segment, int(r.recency), int(r.frequency), round(float(r.monetary), 2),
          round(float(r.predicted_cltv), 2) if pd.notna(r.predicted_cltv) else None,
          round(float(r.churn_probability), 4) if pd.notna(r.churn_probability) else None,
          str(r.risk_segment) if pd.notna(r.risk_segment) else None,
          round(float(r.historical_spend), 2) if pd.notna(r.historical_spend) else None,
          r.quadrant if pd.notna(r.quadrant) else None]
         for i, r in cust.iterrows()],
        [12, 22, 18, 16, 12, 20, 15, 16, 20, 22],
    )

    pr = ctx["priority"]
    sheet(
        "Geri kazanım listesi",
        ["Müşteri No", "Geçmiş toplam harcama", "Churn olasılığı", "Son alışveriş (gün)", "Alışveriş sayısı"],
        [[int(i) if str(i).isdigit() else str(i), round(float(r.historical_spend), 2), round(float(r.churn_probability), 4),
          int(r.recency), int(r.frequency)] for i, r in pr.iterrows()],
        [12, 22, 16, 18, 16],
    )

    pairs = ctx["pairs"]
    if pairs is not None and not pairs.empty:
        sheet(
            "Ürün birliktelikleri",
            ["Ürün A", "Ürün B", "Lift", "Güven (A → B)", "Destek"],
            [[a, b, round(float(l), 3), round(float(c), 4), round(float(s), 4)]
             for a, b, l, c, s in zip(pairs["antecedent_name"], pairs["consequent_name"], pairs["lift"],
                                      pairs["confidence"], pairs["support"])],
            [26, 26, 10, 16, 10],
        )

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
