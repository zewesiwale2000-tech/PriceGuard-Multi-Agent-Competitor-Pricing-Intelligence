#!/usr/bin/env python3
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
PriceGuard Business Intelligence Dashboard
==========================================
Reads data/priceguard_data.csv and generates a self-contained HTML dashboard
with interactive charts and a data table for small business decision-making.

Usage:
    uv run python dashboard.py

Output:
    exports/dashboard_YYYYMMDD_HHMMSS.html   (open in any browser)
"""

import base64
import io
import sys
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # non-interactive backend — must be before pyplot import
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

# ── Constants ───────────────────────────────────────────────────────────────────

MASTER_CSV = Path("data/priceguard_data.csv")
EXPORTS_DIR = Path("exports")

PALETTE = ["#1a73e8", "#34a853", "#fbbc04", "#ea4335", "#9c27b0", "#00acc1", "#ff6d00"]
BG = "#f8f9fa"
DARK = "#202124"
GREY = "#80868b"

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "grid.alpha": 0.35,
        "grid.color": "#dadce0",
    }
)


# ── Data loading ─────────────────────────────────────────────────────────────────


def load_data() -> pd.DataFrame:
    df = pd.read_csv(MASTER_CSV)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["price_value"] = pd.to_numeric(df["price_value"], errors="coerce")
    df["threshold_value"] = pd.to_numeric(
        df["threshold_value"], errors="coerce"
    ).fillna(0)
    df = df.dropna(subset=["price_value"])
    return df


# ── Chart helpers ─────────────────────────────────────────────────────────────────


def _b64(fig: plt.Figure) -> str:
    """Convert a matplotlib figure to a base-64 PNG string."""
    buf = io.BytesIO()
    fig.savefig(
        buf, format="png", dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor()
    )
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode()
    plt.close(fig)
    return encoded


def _styled_fig(w: float = 11, h: float = 5) -> tuple[plt.Figure, plt.Axes]:
    fig, ax = plt.subplots(figsize=(w, h), facecolor=BG)
    ax.set_facecolor(BG)
    ax.tick_params(colors=GREY)
    for spine in ax.spines.values():
        spine.set_edgecolor("#dadce0")
    return fig, ax


# ── Individual chart builders ─────────────────────────────────────────────────────


def chart_price_history(df: pd.DataFrame) -> tuple[str, str] | None:
    """Line chart: price over time per product."""
    if len(df) < 2:
        return None
    fig, ax = _styled_fig(12, 5)
    products = df["product_name"].unique()
    for i, product in enumerate(products[:6]):
        pdf = df[df["product_name"] == product].sort_values("timestamp")
        ax.plot(
            pdf["timestamp"],
            pdf["price_value"],
            marker="o",
            linewidth=2.5,
            markersize=7,
            color=PALETTE[i % len(PALETTE)],
            label=product[:32],
        )
    ax.set_title(
        "📈  Price History Over Time",
        fontsize=14,
        fontweight="bold",
        color=DARK,
        pad=14,
    )
    ax.set_xlabel("Date / Time", fontsize=10, color=GREY)
    ax.set_ylabel("Price ($)", fontsize=10, color=GREY)
    ax.legend(fontsize=9, framealpha=0.9)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d\n%H:%M"))
    fig.autofmt_xdate(rotation=0)
    ax.grid(True)
    return ("Price History Over Time", _b64(fig))


def chart_min_avg_max(df: pd.DataFrame) -> tuple[str, str] | None:
    """Grouped bar chart: min / avg / max price per product."""
    agg = (
        df.groupby("product_name")["price_value"]
        .agg(Min="min", Avg="mean", Max="max")
        .reset_index()
        .sort_values("Avg")
    )
    if agg.empty:
        return None
    n = len(agg)
    x = range(n)
    w = 0.26
    fig, ax = _styled_fig(max(8, n * 1.6), 5)
    ax.bar(
        [i - w for i in x],
        agg["Min"],
        width=w,
        label="Min",
        color=PALETTE[1],
        alpha=0.88,
    )
    ax.bar(x, agg["Avg"], width=w, label="Avg", color=PALETTE[0], alpha=0.88)
    ax.bar(
        [i + w for i in x],
        agg["Max"],
        width=w,
        label="Max",
        color=PALETTE[3],
        alpha=0.88,
    )
    ax.set_xticks(list(x))
    ax.set_xticklabels([p[:22] for p in agg["product_name"]], rotation=15, ha="right")
    ax.set_title(
        "📉  Min / Avg / Max Price per Product",
        fontsize=14,
        fontweight="bold",
        color=DARK,
        pad=14,
    )
    ax.set_ylabel("Price ($)", fontsize=10, color=GREY)
    ax.legend(fontsize=10)
    ax.grid(True, axis="y")
    return ("Min / Avg / Max Prices", _b64(fig))


def chart_merchant_comparison(df: pd.DataFrame) -> tuple[str, str] | None:
    """Horizontal bar chart: latest price per merchant."""
    latest = (
        df.sort_values("timestamp")
        .groupby("merchant", as_index=False)
        .last()
        .sort_values("price_value")
    )
    if latest.empty:
        return None
    fig, ax = _styled_fig(10, max(4, len(latest) * 0.55 + 1.5))
    max_val = latest["price_value"].max()
    bars = ax.barh(
        latest["merchant"],
        latest["price_value"],
        color=PALETTE[0],
        alpha=0.88,
        edgecolor="white",
        linewidth=0.5,
    )
    for bar, val in zip(bars, latest["price_value"], strict=False):
        ax.text(
            bar.get_width() + max_val * 0.01,
            bar.get_y() + bar.get_height() / 2,
            f"${val:,.2f}",
            va="center",
            fontsize=10,
            color=DARK,
        )
    ax.set_title(
        "🏪  Price Comparison by Merchant (Latest Data)",
        fontsize=14,
        fontweight="bold",
        color=DARK,
        pad=14,
    )
    ax.set_xlabel("Price ($)", fontsize=10, color=GREY)
    ax.grid(True, axis="x")
    return ("Merchant Price Comparison", _b64(fig))


def chart_price_distribution(df: pd.DataFrame) -> tuple[str, str] | None:
    """Box plot: price spread per product."""
    products = df["product_name"].unique()
    if len(df) < 3 or len(products) == 0:
        return None
    groups = [
        (p, df[df["product_name"] == p]["price_value"].dropna().values)
        for p in products[:6]
    ]
    groups = [(p, v) for p, v in groups if len(v) > 0]
    if not groups:
        return None
    labels, data = zip(*groups, strict=False)
    fig, ax = _styled_fig(10, 5)
    bp = ax.boxplot(
        data,
        tick_labels=[lbl[:18] for lbl in labels],
        patch_artist=True,
        medianprops={"color": "white", "linewidth": 2.5},
        whiskerprops={"color": GREY, "alpha": 0.6},
        capprops={"color": GREY, "alpha": 0.6},
        flierprops={"marker": "o", "color": GREY, "alpha": 0.4, "markersize": 5},
    )
    for patch, color in zip(bp["boxes"], PALETTE, strict=False):
        patch.set_facecolor(color)
        patch.set_alpha(0.75)
    ax.set_title(
        "📊  Price Distribution by Product",
        fontsize=14,
        fontweight="bold",
        color=DARK,
        pad=14,
    )
    ax.set_ylabel("Price ($)", fontsize=10, color=GREY)
    ax.tick_params(axis="x", rotation=15)
    ax.grid(True, axis="y")
    return ("Price Distribution", _b64(fig))


def chart_savings_vs_threshold(df: pd.DataFrame) -> tuple[str, str] | None:
    """Bar chart: savings (or over-spend) versus user threshold."""
    tdf = df[df["threshold_value"] > 0].copy()
    if tdf.empty:
        return None
    tdf["savings"] = tdf["threshold_value"] - tdf["price_value"]
    tdf = tdf.sort_values("timestamp")
    x_labels = (
        tdf["product_name"].str[:18] + "\n" + tdf["timestamp"].dt.strftime("%m/%d")
    )
    bar_colors = [PALETTE[1] if s >= 0 else PALETTE[3] for s in tdf["savings"]]
    fig, ax = _styled_fig(max(8, len(tdf) * 1.2), 5)
    bars = ax.bar(
        x_labels,
        tdf["savings"],
        color=bar_colors,
        alpha=0.88,
        edgecolor="white",
        width=0.6,
    )
    ax.axhline(0, color=DARK, linewidth=0.8, linestyle="--", alpha=0.4)
    for bar, val in zip(bars, tdf["savings"], strict=False):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            val + (0.5 if val >= 0 else -0.5),
            f"${val:+.2f}",
            ha="center",
            va="bottom" if val >= 0 else "top",
            fontsize=9,
            color=DARK,
        )
    ax.set_title(
        "💰  Savings vs. Price Threshold\nGreen = Below Target  •  Red = Above Target",
        fontsize=13,
        fontweight="bold",
        color=DARK,
        pad=14,
    )
    ax.set_ylabel("Savings ($)", fontsize=10, color=GREY)
    ax.grid(True, axis="y")
    return ("Savings vs Threshold", _b64(fig))


def chart_search_frequency(df: pd.DataFrame) -> tuple[str, str] | None:
    """Donut chart: which products were searched most."""
    counts = df["product_name"].value_counts()
    if len(counts) < 2:
        return None
    fig, ax = plt.subplots(figsize=(8, 6), facecolor=BG)
    ax.set_facecolor(BG)
    _, texts, autotexts = ax.pie(
        counts.values,
        labels=[lbl[:24] for lbl in counts.index],
        autopct="%1.1f%%",
        colors=PALETTE,
        startangle=90,
        pctdistance=0.82,
    )
    for t in texts:
        t.set_fontsize(9)
        t.set_color(DARK)
    for at in autotexts:
        at.set_fontsize(8)
        at.set_color("white")
        at.set_fontweight("bold")
    # Donut hole
    ax.add_artist(plt.Circle((0, 0), 0.60, fc=BG))
    ax.set_title(
        "🔍  Most Tracked Products", fontsize=14, fontweight="bold", color=DARK, pad=14
    )
    return ("Most Tracked Products", _b64(fig))


# ── HTML building ─────────────────────────────────────────────────────────────────


def _summary_cards(df: pd.DataFrame) -> str:
    total = len(df)
    products = df["product_name"].nunique()
    merchants = df["merchant"].nunique()
    below = int((df["below_threshold"].astype(str).str.lower() == "true").sum())
    best_row = df.loc[df["price_value"].idxmin()] if not df.empty else None
    best_html = (
        f"<b>{best_row['price_display']}</b><br>"
        f"<small style='font-size:0.7rem'>{best_row['product_name'][:24]}<br>@ {best_row['merchant']}</small>"
        if best_row is not None
        else "—"
    )
    cards = [
        (str(total), "Price Records"),
        (str(products), "Products Tracked"),
        (str(merchants), "Merchants Found"),
        (str(below), "Below-Threshold Deals"),
        (best_html, "Best Deal Found"),
    ]
    html = '<div class="stats-grid">'
    for num, label in cards:
        html += f'<div class="stat-card"><div class="stat-num">{num}</div><div class="stat-label">{label}</div></div>'
    html += "</div>"
    return html


def _data_table(df: pd.DataFrame) -> str:
    recent = df.sort_values("timestamp", ascending=False).head(25)
    rows = ""
    for _, row in recent.iterrows():
        bt = str(row.get("below_threshold", "")).lower()
        if bt == "true":
            badge = '<span class="badge green">✅ Below Target</span>'
        elif bt == "false":
            badge = '<span class="badge red">❌ Above Target</span>'
        else:
            badge = '<span class="badge grey">—</span>'
        link = (
            f'<a href="{row["link"]}" target="_blank">🔗</a>'
            if str(row.get("link", "")).startswith("http")
            else "—"
        )
        ts = (
            row["timestamp"].strftime("%Y-%m-%d %H:%M")
            if pd.notna(row["timestamp"])
            else "—"
        )
        thresh = (
            f"${float(row['threshold_value']):,.2f}"
            if row.get("threshold_value")
            else "—"
        )
        rows += (
            f"<tr>"
            f"<td>{ts}</td>"
            f"<td><b>{row.get('product_name', '')}</b></td>"
            f"<td class='price'>{row.get('price_display', '')}</td>"
            f"<td>{row.get('merchant', '')}</td>"
            f"<td>{thresh}</td>"
            f"<td>{badge}</td>"
            f"<td>{link}</td>"
            f"</tr>"
        )
    return f"""
    <table class="data-table">
      <thead><tr>
        <th>Timestamp</th><th>Product</th><th>Price</th>
        <th>Merchant</th><th>Target</th><th>vs Target</th><th>Link</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>"""


def _build_html(charts: list[tuple[str, str]], df: pd.DataFrame) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    records_cnt = len(df)

    charts_html = "".join(
        f'<div class="chart-card"><p class="chart-label">{title}</p>'
        f'<img src="data:image/png;base64,{b64}" alt="{title}" class="chart-img"/></div>'
        for title, b64 in charts
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>PriceGuard — Business Intelligence Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet"/>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Inter', sans-serif;
      background: #f0f4f8;
      color: #202124;
      min-height: 100vh;
    }}

    /* ── Header ── */
    header {{
      background: linear-gradient(135deg, #1a73e8 0%, #0d47a1 100%);
      color: #fff;
      padding: 2rem 3rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
      box-shadow: 0 4px 24px rgba(26,115,232,.35);
    }}
    .header-left h1 {{ font-size: 1.75rem; font-weight: 800; letter-spacing: -.5px; }}
    .header-left p  {{ font-size: .85rem; opacity: .75; margin-top: .3rem; }}
    .header-badge {{
      background: rgba(255,255,255,.15);
      border: 1px solid rgba(255,255,255,.25);
      border-radius: 20px;
      padding: .4rem 1.1rem;
      font-size: .8rem;
      white-space: nowrap;
    }}

    /* ── Layout ── */
    main {{ max-width: 1400px; margin: 0 auto; padding: 2rem 1.5rem 3rem; }}
    section {{ margin-bottom: 2.5rem; }}
    .section-title {{
      font-size: .75rem; font-weight: 700; color: #5f6368;
      text-transform: uppercase; letter-spacing: 1.2px;
      margin-bottom: 1rem;
      display: flex; align-items: center; gap: .5rem;
    }}
    .section-title::after {{
      content: ''; flex: 1; height: 1px; background: #dadce0;
    }}

    /* ── Stat cards ── */
    .stats-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 1rem;
    }}
    .stat-card {{
      background: #fff;
      border-radius: 16px;
      padding: 1.5rem 1rem;
      text-align: center;
      box-shadow: 0 2px 12px rgba(0,0,0,.06);
      border: 1px solid rgba(0,0,0,.05);
      transition: transform .2s, box-shadow .2s;
    }}
    .stat-card:hover {{ transform: translateY(-3px); box-shadow: 0 8px 28px rgba(0,0,0,.1); }}
    .stat-num   {{ font-size: 2rem; font-weight: 700; color: #1a73e8; line-height: 1.2; }}
    .stat-label {{ font-size: .75rem; color: #80868b; margin-top: .4rem; font-weight: 600; }}

    /* ── Charts grid ── */
    .charts-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(520px, 1fr));
      gap: 1.5rem;
    }}
    .chart-card {{
      background: #fff;
      border-radius: 16px;
      padding: 1.25rem 1.25rem 1rem;
      box-shadow: 0 2px 12px rgba(0,0,0,.06);
      border: 1px solid rgba(0,0,0,.05);
    }}
    .chart-label {{ font-size: .8rem; font-weight: 600; color: #5f6368; margin-bottom: .6rem; }}
    .chart-img   {{ width: 100%; height: auto; border-radius: 8px; }}

    /* ── Data table ── */
    .table-wrapper {{
      background: #fff;
      border-radius: 16px;
      box-shadow: 0 2px 12px rgba(0,0,0,.06);
      overflow-x: auto;
    }}
    .data-table {{ width: 100%; border-collapse: collapse; font-size: .84rem; }}
    .data-table th {{
      background: #1a73e8; color: #fff;
      padding: .8rem 1rem;
      text-align: left; font-weight: 600;
      font-size: .75rem; text-transform: uppercase; letter-spacing: .6px;
    }}
    .data-table td {{ padding: .75rem 1rem; border-bottom: 1px solid #f1f3f4; vertical-align: middle; }}
    .data-table tr:last-child td {{ border-bottom: none; }}
    .data-table tr:hover td {{ background: #f8f9fa; }}
    .data-table a {{ color: #1a73e8; font-size: 1.1rem; }}
    .price {{ font-weight: 700; color: #137333; }}
    .badge {{
      display: inline-block; padding: .22rem .65rem;
      border-radius: 20px; font-size: .73rem; font-weight: 700;
    }}
    .badge.green {{ background: #e6f4ea; color: #137333; }}
    .badge.red   {{ background: #fce8e6; color: #c5221f; }}
    .badge.grey  {{ background: #f1f3f4; color: #80868b; }}

    /* ── Footer ── */
    footer {{
      text-align: center; padding: 2rem;
      color: #80868b; font-size: .78rem;
    }}
  </style>
</head>
<body>

<header>
  <div class="header-left">
    <h1>🛡️ PriceGuard Intelligence Dashboard</h1>
    <p>Business Price Analytics &amp; Market Intelligence for Smart Procurement</p>
  </div>
  <div class="header-badge">📅 {now} &nbsp;|&nbsp; {records_cnt} records</div>
</header>

<main>

  <section>
    <div class="section-title">Summary Statistics</div>
    {_summary_cards(df)}
  </section>

  <section>
    <div class="section-title">Visual Analytics</div>
    <div class="charts-grid">
      {charts_html}
    </div>
  </section>

  <section>
    <div class="section-title">Recent Price Records (last 25)</div>
    <div class="table-wrapper">
      {_data_table(df)}
    </div>
  </section>

</main>

<footer>
  PriceGuard Business Intelligence &nbsp;•&nbsp;
  Auto-generated report &nbsp;•&nbsp; {now}
</footer>

</body>
</html>"""


# ── Entry point ───────────────────────────────────────────────────────────────────


def main() -> None:
    if not MASTER_CSV.exists():
        print(f"❌  Master CSV not found: {MASTER_CSV}")
        print("   Run the PriceGuard agent first to collect price data.")
        sys.exit(1)

    df = load_data()
    if df.empty:
        print("❌  No valid price data in the CSV yet.")
        print("   Ask the agent to search for a product first.")
        sys.exit(1)

    EXPORTS_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = EXPORTS_DIR / f"dashboard_{ts}.html"

    print(
        f"📊  Building dashboard from {len(df)} records across "
        f"{df['product_name'].nunique()} products…"
    )

    chart_fns = [
        chart_price_history,
        chart_min_avg_max,
        chart_merchant_comparison,
        chart_price_distribution,
        chart_savings_vs_threshold,
        chart_search_frequency,
    ]

    charts = []
    for fn in chart_fns:
        result = fn(df)
        if result:
            charts.append(result)
            print(f"   ✅  {result[0]}")

    html = _build_html(charts, df)
    output_path.write_text(html, encoding="utf-8")

    abs_path = output_path.resolve()
    print(f"\n✅  Dashboard saved → {abs_path}")
    print(f"   Open in browser:   file:///{abs_path}")


if __name__ == "__main__":
    main()
