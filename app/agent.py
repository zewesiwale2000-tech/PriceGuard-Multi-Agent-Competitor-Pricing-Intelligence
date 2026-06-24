# ruff: noqa
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

import datetime
from zoneinfo import ZoneInfo
import os

from google.adk.agents import Agent, SequentialAgent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

import google.auth
from app.antigravity_agent import make_antigravity_analyst
from app.tools import (
    export_to_csv,
    export_to_pdf,
    insert_to_master_csv,
    search_prices,
    send_to_slack,
)

try:
    _, project_id = google.auth.default()
    if project_id:
        os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
except Exception:
    pass

os.environ["GOOGLE_CLOUD_LOCATION"] = "global"

if os.environ.get("GEMINI_API_KEY"):
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "False"
else:
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"


# Build analyst agent — uses google-antigravity SDK when available,
# falls back transparently to a standard ADK Agent otherwise.
analyst_agent = make_antigravity_analyst(
    model="gemini-flash-latest",
    output_key="price_analysis_result",
)


drafting_agent = Agent(
    name="drafting_agent",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(
            attempts=6,
            initialDelay=1.0,
            maxDelay=15.0,
            httpStatusCodes=[429, 500, 503, 504],
        ),
    ),
    instruction="""You are the DraftingAgent for PriceGuard. Your role is to format a premium-looking price notification message and deliver it to Slack.

Retrieve the analysis from the state: {price_analysis_result}

Format a beautiful Slack message. Use emojis (e.g. 🚨, 💰, 🛒, 📈) to highlight key information.
Ensure the message contains:
- A clear headline (e.g. "Price Alert" or "Price Report")
- Product Name
- Current Lowest Price
- Merchant/Source (with link if available)
- Whether it's below the threshold (if a threshold was specified in the original request)

Once formatted, use the send_to_slack tool to deliver the message.
Report back to the user that the alert/report has been successfully sent to Slack, including a preview of the message content.
""",
    tools=[send_to_slack],
)


export_agent = Agent(
    name="export_agent",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(
            attempts=6,
            initialDelay=1.0,
            maxDelay=15.0,
            httpStatusCodes=[429, 500, 503, 504],
        ),
    ),
    instruction="""You are the ExportAgent for PriceGuard. Your job is to persist and export the price analysis results.

Retrieve the analysis from the state: {price_analysis_result}

Extract the following from the analysis:
- product_name: the clean product name (e.g. "iPhone 15 Pro 256GB")
- price_display: the lowest price found as a string (e.g. "$899.00")
- merchant: the merchant or store name (e.g. "Amazon")
- link: the product URL (if available, else empty string)
- query: re-state the original search query used
- threshold_value: the numeric threshold if the user specified one (else 0.0)
- below_threshold: True if the price is at or below the threshold, else False

Then perform ALL of the following steps in order:

1. Call insert_to_master_csv with the extracted fields above.
   This saves the data to the persistent analytics database for charting and trends.

2. Call export_to_csv with EXACTLY these keyword arguments (NOT the raw analysis text):
   product_name, price_display, merchant, link, query, threshold_value, below_threshold.
   This saves a human-readable per-run CSV snapshot with clear column headers.

3. Call export_to_pdf with EXACTLY the same keyword arguments as step 2:
   product_name, price_display, merchant, link, query, threshold_value, below_threshold.
   This saves a human-readable per-run PDF report with a labelled table layout.

Finally, report back to the user:
- Confirm all three exports succeeded.
- Show the file paths for the CSV and PDF.
- Remind the user they can run `uv run python dashboard.py` to generate
  the full BI dashboard with charts from all accumulated data.
""",
    tools=[insert_to_master_csv, export_to_csv, export_to_pdf],
)


root_agent = SequentialAgent(
    name="priceguard_pipeline",
    sub_agents=[analyst_agent, drafting_agent, export_agent],
)

app = App(
    root_agent=root_agent,
    name="app",
)
