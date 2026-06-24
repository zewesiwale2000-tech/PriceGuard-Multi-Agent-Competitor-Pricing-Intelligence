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

import csv
import datetime
import os
import re
import uuid
from pathlib import Path

import requests
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def search_prices(query: str) -> dict:
    """Searches the web using SerpAPI to find prices and listings for a product.

    Args:
        query: The search query string (e.g. "Google Pixel 9 Pro 128GB price").

    Returns:
        A dictionary containing the search results including organic or shopping results.
    """
    api_key = os.environ.get("SERP_API_KEY")
    if not api_key:
        return {
            "status": "error",
            "message": "SERP_API_KEY environment variable is not set.",
        }

    params = {"q": query, "api_key": api_key, "engine": "google"}

    try:
        response = requests.get(
            "https://serpapi.com/search.json", params=params, timeout=15
        )
        response.raise_for_status()
        data = response.json()

        results = {}
        if "shopping_results" in data:
            results["shopping_results"] = [
                {
                    "title": item.get("title"),
                    "link": item.get("link"),
                    "price": item.get("price"),
                    "source": item.get("source"),
                }
                for item in data["shopping_results"][:5]
            ]
        if "organic_results" in data:
            results["organic_results"] = [
                {
                    "title": item.get("title"),
                    "link": item.get("link"),
                    "snippet": item.get("snippet"),
                    "price": item.get("price"),
                }
                for item in data["organic_results"][:5]
            ]
        if "answer_box" in data:
            results["answer_box"] = data["answer_box"]

        return {"status": "success", "results": results}
    except Exception as e:
        return {"status": "error", "message": f"HTTP request failed: {e}"}


def send_to_slack(message: str) -> dict:
    """Delivers a drafted price report or alert to a Slack channel via Webhook.

    Args:
        message: The formatted markdown message text to deliver to Slack.

    Returns:
        A dictionary indicating the delivery status of the alert.
    """
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        return {
            "status": "error",
            "message": "SLACK_WEBHOOK_URL environment variable is not set.",
        }

    try:
        response = requests.post(webhook_url, json={"text": message}, timeout=15)
        response.raise_for_status()
        return {
            "status": "success",
            "message": "Alert delivered successfully to Slack.",
        }
    except Exception as e:
        return {"status": "error", "message": f"HTTP request failed: {e}"}


def export_to_csv(
    product_name: str,
    price_display: str,
    merchant: str,
    link: str = "",
    query: str = "",
    threshold_value: float = 0.0,
    below_threshold: bool = False,
) -> dict:
    """Exports the price analysis results to a human-readable CSV file.

    Each argument corresponds to a clean, structured field so the output
    CSV has clear, labelled columns that any person can open and read.

    Args:
        product_name: Clean product name (e.g. "Nike Air Force 1 '07").
        price_display: Lowest price as a display string (e.g. "$115.00").
        merchant: Merchant or store name (e.g. "Finish Line").
        link: Direct URL to the product listing.
        query: The original search query used.
        threshold_value: User-specified price threshold (0.0 if not set).
        below_threshold: Whether this price is at or below the threshold.

    Returns:
        A dictionary with status and the path to the saved CSV file.
    """
    try:
        exports_dir = Path("exports")
        exports_dir.mkdir(exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c if c.isalnum() else "_" for c in product_name)
        file_path = exports_dir / f"{safe_name}_{timestamp}.csv"

        # Parse numeric price for the dedicated column
        nums = re.findall(r"[\d]+\.?\d*", price_display.replace(",", ""))
        price_value = float(nums[0]) if nums else ""

        # Determine a human-friendly threshold string
        threshold_str = f"{threshold_value:.2f}" if threshold_value else "Not specified"
        below_str = "Yes" if below_threshold else ("No" if threshold_value else "N/A")

        fieldnames = [
            "Product Name",
            "Search Query",
            "Lowest Price",
            "Price (numeric)",
            "Merchant / Store",
            "Product Link",
            "Price Threshold",
            "Below Threshold?",
            "Date & Time",
        ]
        row = {
            "Product Name": product_name.strip(),
            "Search Query": query.strip(),
            "Lowest Price": price_display.strip(),
            "Price (numeric)": price_value,
            "Merchant / Store": merchant.strip(),
            "Product Link": link.strip(),
            "Price Threshold": threshold_str,
            "Below Threshold?": below_str,
            "Date & Time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow(row)

        return {
            "status": "success",
            "message": "CSV saved successfully.",
            "file_path": str(file_path.resolve()),
        }
    except Exception as e:
        return {"status": "error", "message": f"CSV export failed: {e}"}


def export_to_pdf(
    product_name: str,
    price_display: str,
    merchant: str,
    link: str = "",
    query: str = "",
    threshold_value: float = 0.0,
    below_threshold: bool = False,
) -> dict:
    """Exports the price analysis results to a styled, human-readable PDF report.

    Each argument corresponds to a clean, structured field so the PDF renders
    a clear label-value layout that any person can open and understand.

    Args:
        product_name: Clean product name (e.g. "Nike Air Force 1 '07").
        price_display: Lowest price as a display string (e.g. "$115.00").
        merchant: Merchant or store name (e.g. "Finish Line").
        link: Direct URL to the product listing.
        query: The original search query used.
        threshold_value: User-specified price threshold (0.0 if not set).
        below_threshold: Whether this price is at or below the threshold.

    Returns:
        A dictionary with status and the path to the saved PDF file.
    """
    try:
        exports_dir = Path("exports")
        exports_dir.mkdir(exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c if c.isalnum() else "_" for c in product_name)
        file_path = exports_dir / f"{safe_name}_{timestamp}.pdf"

        doc = SimpleDocTemplate(
            str(file_path),
            pagesize=A4,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
        )
        styles = getSampleStyleSheet()
        elements = []

        # ── Header banner ────────────────────────────────────────────────────
        header_data = [
            [
                Paragraph(
                    "<font color='white'><b>🛡️ PriceGuard — Price Report</b></font>",
                    styles["Title"],
                )
            ]
        ]
        header_table = Table(header_data, colWidths=[A4[0] - 4 * cm])
        header_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#1a73e8")),
                    ("TOPPADDING", (0, 0), (-1, -1), 14),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
                    ("LEFTPADDING", (0, 0), (-1, -1), 18),
                    ("ROUNDEDCORNERS", [8, 8, 8, 8]),
                ]
            )
        )
        elements.append(header_table)
        elements.append(Spacer(1, 0.4 * cm))

        # ── Generated timestamp ──────────────────────────────────────────────
        elements.append(
            Paragraph(
                f"<font color='#5f6368' size='9'>Generated: "
                f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</font>",
                styles["Normal"],
            )
        )
        elements.append(Spacer(1, 0.6 * cm))

        # ── Price details table ──────────────────────────────────────────────
        threshold_str = f"{threshold_value:.2f}" if threshold_value else "Not specified"
        if below_threshold and threshold_value:
            threshold_status = "✅  Yes — price is at or below target"
            status_color = colors.HexColor("#137333")
        elif threshold_value:
            threshold_status = "❌  No — price is above target"
            status_color = colors.HexColor("#c5221f")
        else:
            threshold_status = "N/A"
            status_color = colors.HexColor("#5f6368")

        link_text = link.strip() if link.strip() else "—"

        label_style = styles["Normal"].clone("LabelStyle")
        label_style.fontName = "Helvetica-Bold"
        label_style.fontSize = 10
        label_style.textColor = colors.HexColor("#202124")

        value_style = styles["Normal"].clone("ValueStyle")
        value_style.fontSize = 10
        value_style.textColor = colors.HexColor("#3c4043")

        link_style = styles["Normal"].clone("LinkStyle")
        link_style.fontSize = 9
        link_style.textColor = colors.HexColor("#1a73e8")

        details_data = [
            [
                Paragraph("<b>Field</b>", label_style),
                Paragraph("<b>Value</b>", label_style),
            ],
            [
                Paragraph("Product Name", label_style),
                Paragraph(product_name.strip(), value_style),
            ],
            [
                Paragraph("Search Query", label_style),
                Paragraph(query.strip() or "—", value_style),
            ],
            [
                Paragraph("Lowest Price", label_style),
                Paragraph(f"<b>{price_display.strip()}</b>", label_style),
            ],
            [
                Paragraph("Merchant / Store", label_style),
                Paragraph(merchant.strip() or "—", value_style),
            ],
            [Paragraph("Product Link", label_style), Paragraph(link_text, link_style)],
            [
                Paragraph("Price Threshold", label_style),
                Paragraph(threshold_str, value_style),
            ],
            [
                Paragraph("Below Threshold?", label_style),
                Paragraph(threshold_status, value_style),
            ],
        ]

        col_w = A4[0] - 4 * cm
        details_table = Table(
            details_data,
            colWidths=[col_w * 0.32, col_w * 0.68],
            repeatRows=1,
        )
        details_table.setStyle(
            TableStyle(
                [
                    # Header row
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f0fe")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1a73e8")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 10),
                    # Data rows — alternating
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#f8f9fa")],
                    ),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dadce0")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    # Highlight the price row
                    ("BACKGROUND", (0, 3), (-1, 3), colors.HexColor("#e6f4ea")),
                    # Threshold status row colour
                    ("TEXTCOLOR", (1, 7), (1, 7), status_color),
                ]
            )
        )
        elements.append(details_table)

        elements.append(Spacer(1, 1 * cm))
        elements.append(
            Paragraph(
                "<i><font color='#80868b' size='8'>Generated by PriceGuard Agent</font></i>",
                styles["Italic"],
            )
        )

        doc.build(elements)

        return {
            "status": "success",
            "message": "PDF saved successfully.",
            "file_path": str(file_path.resolve()),
        }
    except Exception as e:
        return {"status": "error", "message": f"PDF export failed: {e}"}


# ── Master Analytics CSV ────────────────────────────────────────────────────────

MASTER_CSV_COLUMNS = [
    "session_id",  # short UUID grouping one search run
    "timestamp",  # ISO-8601 datetime
    "product_name",  # clean product name
    "query",  # original search query
    "price_value",  # numeric price (float)
    "price_display",  # raw price string e.g. "$299.99"
    "currency",  # USD / EUR / GBP / etc.
    "merchant",  # store / source name
    "link",  # product URL
    "threshold_value",  # user price target (empty if none)
    "below_threshold",  # True / False / N/A
]


def insert_to_master_csv(
    product_name: str,
    price_display: str,
    merchant: str,
    link: str = "",
    query: str = "",
    threshold_value: float = 0.0,
    below_threshold: bool = False,
) -> dict:
    """Inserts a collected price data point into the persistent master analytics CSV.

    This CSV is the single source of truth for all historical price data collected
    by the agent. It is used to power the business intelligence dashboard.

    Args:
        product_name: Clean product name (e.g. "iPhone 15 Pro 256GB").
        price_display: Price as a display string (e.g. "$899.00").
        merchant: Merchant or store name (e.g. "Amazon").
        link: URL to the product listing.
        query: The original search query used.
        threshold_value: User-specified price threshold (0.0 if not set).
        below_threshold: Whether this price is at or below the threshold.

    Returns:
        A dictionary with status and the master CSV file path.
    """
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    master_path = data_dir / "priceguard_data.csv"

    # Parse numeric price value from display string
    nums = re.findall(r"[\d]+\.?\d*", price_display.replace(",", ""))
    price_value = float(nums[0]) if nums else None

    # Infer currency from symbol
    currency = "USD"
    if "€" in price_display:
        currency = "EUR"
    elif "£" in price_display:
        currency = "GBP"
    elif "R" in price_display and "$" not in price_display:
        currency = "ZAR"

    row = {
        "session_id": str(uuid.uuid4())[:8],
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "product_name": product_name.strip(),
        "query": query.strip(),
        "price_value": price_value if price_value is not None else "",
        "price_display": price_display.strip(),
        "currency": currency,
        "merchant": merchant.strip(),
        "link": link.strip(),
        "threshold_value": threshold_value if threshold_value else "",
        "below_threshold": below_threshold,
    }

    file_exists = master_path.exists() and master_path.stat().st_size > 0

    try:
        with open(master_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=MASTER_CSV_COLUMNS)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)
        return {
            "status": "success",
            "message": "Data inserted into master analytics CSV.",
            "file_path": str(master_path.resolve()),
            "record": {k: v for k, v in row.items() if k != "link"},
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed to insert into master CSV: {e}"}
