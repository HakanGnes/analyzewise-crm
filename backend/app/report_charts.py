"""Static SVG charts for the CRM report.

Same color roles and mark rules as the React screens (frontend/src/charts/
theme.js): one brand hue for single-series marks, a muted gray for context,
status colors only for churn-risk bands, solid hairline grids, no top/right
spines, values labeled where the reader needs them. SVG text is kept as
text (svg.fonttype = none) so it stays sharp, searchable and small.
"""
from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

SERIES = "#4f46e5"
DOWN = "#d03b3b"
MUTED = "#c4c8d8"
GRID = "#eceef5"
AXIS = "#d5d8e4"
INK = "#111827"
INK_SOFT = "#6b7280"
STATUS = {
    "düşük risk": "#0ca30c",
    "orta risk": "#fab219",
    "yüksek risk": "#ec835a",
    "çok yüksek risk": "#d03b3b",
}
RAMP = LinearSegmentedColormap.from_list("aw_indigo", ["#eef2ff", "#312e81"])

plt.rcParams.update(
    {
        "svg.fonttype": "none",
        "font.family": ["Inter", "DejaVu Sans", "sans-serif"],
        "font.size": 9.5,
        "axes.edgecolor": AXIS,
        "axes.labelcolor": INK_SOFT,
        "axes.titlesize": 10,
        "xtick.color": INK_SOFT,
        "ytick.color": INK_SOFT,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": False,
        "figure.dpi": 100,
    }
)


def _tr_int(v: float) -> str:
    return f"{v:,.0f}".replace(",", ".")


def _tr_pct(v: float, digits: int = 0) -> str:
    return "%" + f"{v * 100:.{digits}f}".replace(".", ",")


def _svg(fig) -> str:
    buf = io.StringIO()
    fig.savefig(buf, format="svg", bbox_inches="tight", transparent=True)
    plt.close(fig)
    svg = buf.getvalue()
    return svg[svg.index("<svg"):]


def _hgrid(ax):
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


TR_MONTHS = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]


def _month_label(ym: str, first: bool) -> str:
    year, month = ym.split("-")
    label = TR_MONTHS[int(month) - 1]
    return f"{label}\n{year}" if first or month == "01" else label


def monthly_revenue(months: list[str], revenue: list[float]) -> str:
    fig, ax = plt.subplots(figsize=(7.2, 2.6))
    x = np.arange(len(months))
    ax.plot(x, revenue, color=SERIES, linewidth=2)
    step = 1 if len(months) <= 14 else 2 if len(months) <= 28 else 3
    ticks = list(range(0, len(months), step))
    ax.set_xticks(ticks, [_month_label(months[i], i == 0) for i in ticks])
    ax.tick_params(axis="x", length=0)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: _tr_int(v)))
    _hgrid(ax)
    if len(revenue):
        peak = int(np.argmax(revenue))
        ax.scatter([peak], [revenue[peak]], color=SERIES, s=28, zorder=3, edgecolor="white", linewidth=1.5)
        ax.annotate(_tr_int(revenue[peak]), (peak, revenue[peak]), xytext=(0, 8), textcoords="offset points",
                    ha="center", color=INK, fontsize=9, fontweight="bold")
    ax.set_ylim(bottom=0, top=max(revenue, default=1) * 1.15)
    return _svg(fig)


def horizontal_bars(labels: list[str], values: list[float], value_fmt=_tr_int, highlight: str | None = None,
                    width: float = 7.2) -> str:
    order = np.argsort(values)
    labels = [labels[i] for i in order]
    values = [values[i] for i in order]
    fig, ax = plt.subplots(figsize=(width, 0.36 * len(labels) + 0.5))
    colors = [SERIES if (highlight is None or lab == highlight) else MUTED for lab in labels]
    ax.barh(labels, values, color=colors, height=0.62)
    vmax = max(values) if values else 1
    for i, v in enumerate(values):
        ax.text(v + vmax * 0.01, i, value_fmt(v), va="center", fontsize=9, color=INK)
    ax.set_xlim(0, vmax * 1.18)
    ax.spines["bottom"].set_visible(False)
    ax.set_xticks([])
    ax.tick_params(axis="y", length=0, labelcolor=INK)
    return _svg(fig)


def segment_heatmap(segments: list[str], columns: list[tuple[str, str, bool]], values: np.ndarray,
                    formats: list) -> str:
    """columns: (key, label, higher_is_better). Each column scaled on its own range."""
    norm = np.zeros_like(values, dtype=float)
    for j, (_, _, hib) in enumerate(columns):
        col = values[:, j]
        lo, hi = np.nanmin(col), np.nanmax(col)
        t = (col - lo) / (hi - lo) if hi > lo else np.full_like(col, 0.5)
        norm[:, j] = t if hib else 1 - t
    norm = 0.08 + norm * 0.84

    fig, ax = plt.subplots(figsize=(7.2, 0.42 * len(segments) + 0.7))
    ax.imshow(norm, cmap=RAMP, vmin=0, vmax=1, aspect="auto")
    for i in range(len(segments)):
        for j in range(len(columns)):
            ax.text(j, i, formats[j](values[i, j]), ha="center", va="center", fontsize=9,
                    color="white" if norm[i, j] > 0.5 else INK)
    ax.set_xticks(range(len(columns)), [c[1] for c in columns])
    ax.set_yticks(range(len(segments)), segments)
    ax.xaxis.tick_top()
    ax.tick_params(length=0, labelcolor=INK)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xticks(np.arange(-0.5, len(columns)), minor=True)
    ax.set_yticks(np.arange(-0.5, len(segments)), minor=True)
    ax.grid(which="minor", color="white", linewidth=2)
    ax.tick_params(which="minor", length=0)
    return _svg(fig)


def pareto(values: np.ndarray, mark: float = 0.2) -> tuple[str, float]:
    v = np.sort(np.asarray(values, dtype=float))[::-1]
    total = v.sum() or 1.0
    x = np.arange(1, len(v) + 1) / len(v)
    y = np.cumsum(v) / total
    share = float(np.interp(mark, x, y)) if len(v) else 0.0

    fig, ax = plt.subplots(figsize=(4.6, 3.0))
    ax.plot([0, 1], [0, 1], color=MUTED, linewidth=1)
    ax.plot(np.r_[0, x], np.r_[0, y], color=SERIES, linewidth=2)
    ax.axvline(mark, color=AXIS, linewidth=1)
    ax.scatter([mark], [share], color=SERIES, s=32, zorder=3, edgecolor="white", linewidth=1.5)
    ax.annotate(_tr_pct(share), (mark, share), xytext=(8, -4), textcoords="offset points", fontsize=9.5,
                fontweight="bold", color=INK)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.02)
    pct = FuncFormatter(lambda v, _: _tr_pct(v))
    ax.xaxis.set_major_formatter(pct)
    ax.yaxis.set_major_formatter(pct)
    ax.set_xlabel("Müşterilerin payı (en değerliden başlayarak)")
    ax.set_ylabel("Tahmini değerin payı")
    _hgrid(ax)
    return _svg(fig), share


def risk_share(counts: dict) -> str:
    """One 100% bar, 2px surface gaps, legend row underneath so even a
    narrow band keeps its label (labels never squeezed inside segments)."""
    order = list(STATUS.keys())
    vals = np.array([counts.get(k, 0) for k in order], dtype=float)
    total = vals.sum() or 1.0
    fig, ax = plt.subplots(figsize=(7.2, 1.05))
    left, gap = 0.0, 0.003
    for k, v in zip(order, vals):
        w = v / total
        if w > 0:
            ax.barh(0.6, max(w - gap, 0.001), left=left, color=STATUS[k], height=0.5)
        left += w
    for i, (k, v) in enumerate(zip(order, vals)):
        x0 = i * 0.25
        ax.add_patch(plt.Rectangle((x0, -0.42), 0.018, 0.22, color=STATUS[k], transform=ax.transData, clip_on=False))
        ax.text(x0 + 0.028, -0.31, f"{k}", va="center", fontsize=9, color=INK)
        ax.text(x0 + 0.028, -0.68, f"{_tr_int(v)} ({_tr_pct(v / total)})", va="center", fontsize=9, color=INK_SOFT)
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.9, 0.9)
    ax.axis("off")
    return _svg(fig)


def value_risk_scatter(prob, spend, quadrant, risk_cut: float, value_cut: float) -> str:
    prob, spend, quadrant = np.asarray(prob), np.asarray(spend), np.asarray(quadrant)
    keep = spend > 0
    prob, spend, quadrant = prob[keep], spend[keep], quadrant[keep]
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    groups = [
        (~np.isin(quadrant, ["değerli, riskte", "değerli, güvende"]), MUTED, 0.5, "Diğer müşteriler"),
        (quadrant == "değerli, güvende", SERIES, 0.7, "Değerli, güvende"),
        (quadrant == "değerli, riskte", DOWN, 0.95, "Değerli, riskte"),
    ]
    for mask, color, alpha, label in groups:
        ax.scatter(prob[mask], spend[mask], s=16, color=color, alpha=alpha, linewidth=0.6, edgecolor="white",
                   label=f"{label} ({_tr_int(mask.sum())})")
    ax.set_yscale("log")
    ax.axvline(risk_cut, color=AXIS, linewidth=1)
    ax.axhline(value_cut, color=AXIS, linewidth=1)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: _tr_pct(v)))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: _tr_int(v)))
    ax.set_xlim(-0.02, 1.02)
    ax.set_xlabel("Churn olasılığı")
    ax.set_ylabel("Geçmiş toplam harcama (log)")
    _hgrid(ax)
    ax.legend(frameon=False, loc="lower left", fontsize=8.5, bbox_to_anchor=(0, 1.0), ncol=3, handletextpad=0.3)
    return _svg(fig)


def slopegraph(names: list[str], first: list[float], second: list[float], periods: list[str],
               threshold: float = 0.03) -> str:
    n = len(names)
    height = max(3.0, 0.3 * n + 1.4)
    fig, ax = plt.subplots(figsize=(7.2, height))
    xs = (0.0, 1.0)
    top = max(max(first, default=0), max(second, default=0)) * 1.08 or 1
    # Minimum label spacing of ~13pt, converted to data units for this figure.
    plot_pts = height * 72 * 0.82
    gap = top * 13 / plot_pts

    def spread(vals):
        idx = list(np.argsort(vals))
        placed = np.array(vals, dtype=float)
        for a, b in zip(idx[:-1], idx[1:]):
            if placed[b] - placed[a] < gap:
                placed[b] = placed[a] + gap
        overflow = placed.max() - top if len(placed) else 0
        if overflow > 0:
            placed -= overflow
            for a, b in zip(reversed(idx[1:]), reversed(idx[:-1])):
                if placed[a] - placed[b] < gap:
                    placed[b] = placed[a] - gap
        return placed

    ly, ry = spread(first), spread(second)
    for i, name in enumerate(names):
        d = second[i] - first[i]
        color = SERIES if d >= threshold else DOWN if d <= -threshold else MUTED
        ink = INK if abs(d) >= threshold else INK_SOFT
        weight = "bold" if abs(d) >= threshold else "normal"
        ax.plot(xs, (first[i], second[i]), color=color, linewidth=2, solid_capstyle="round", zorder=2 if color == MUTED else 3)
        ax.scatter(xs, (first[i], second[i]), color=color, s=24, zorder=4, edgecolor="white", linewidth=1.5)
        for x_dot, y_dot, y_lab, ha, text in (
            (0.0, first[i], ly[i], "right", f"{name}  {_tr_pct(first[i])}"),
            (1.0, second[i], ry[i], "left", f"{_tr_pct(second[i])}  {name}"),
        ):
            x_lab = -0.05 if ha == "right" else 1.05
            if abs(y_lab - y_dot) > gap * 0.35:  # leader line when a label had to move
                ax.plot([x_dot, x_lab * 0.6 + x_dot * 0.4], [y_dot, y_lab], color=AXIS, linewidth=0.8, zorder=1)
            ax.text(x_lab, y_lab, text, ha=ha, va="center", fontsize=8.8, color=ink, fontweight=weight)
    lo = min(ly.min(), ry.min(), 0) - gap
    ax.set_xlim(-1.05, 2.05)
    ax.set_ylim(lo, top + gap * 2.6)
    for x, title, period in ((0, "İlk yarı", periods[0]), (1, "İkinci yarı", periods[1])):
        ax.text(x, top + gap * 2.4, title, ha="center", va="top", fontsize=9, fontweight="bold", color=INK)
        ax.text(x, top + gap * 1.3, period, ha="center", va="top", fontsize=8, color=INK_SOFT)
    ax.axis("off")
    return _svg(fig)
