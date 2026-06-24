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

"""PriceGuard MCP Server.

Exposes `search_prices` and `send_to_slack` as MCP tools so that any
MCP-compatible client (e.g. Claude Desktop, Cursor, VS Code extensions)
can use PriceGuard capabilities directly.

Run locally:
    uv run python -m app.mcp_server

Or add to an MCP client config:
    {
      "mcpServers": {
        "priceguard": {
          "command": "uv",
          "args": ["run", "python", "-m", "app.mcp_server"],
          "env": {
            "SERP_API_KEY": "<your-key>",
            "SLACK_WEBHOOK_URL": "<your-webhook>"
          }
        }
      }
    }
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

# Load .env automatically when running the server standalone
try:
    from dotenv import load_dotenv

    _env_path = Path(__file__).resolve().parent.parent / ".env"
    if _env_path.exists():
        load_dotenv(dotenv_path=_env_path)
except ImportError:
    pass  # python-dotenv is optional; env vars may already be set

from mcp.server.fastmcp import FastMCP

from app.tools import search_prices as _search_prices
from app.tools import send_to_slack as _send_to_slack

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── MCP server instance ──────────────────────────────────────────────────────

mcp = FastMCP(
    name="priceguard",
    instructions=(
        "PriceGuard MCP Server — search for real-time product prices via SerpAPI "
        "and deliver formatted alerts to Slack."
    ),
)

# ── Input validation helpers ─────────────────────────────────────────────────

_MAX_QUERY_LEN = 300
_MAX_MESSAGE_LEN = 4000
_BLOCKED_PATTERNS = re.compile(
    r"(ignore previous|disregard|system prompt|jailbreak|<script|javascript:)",
    re.IGNORECASE,
)


def _sanitize_query(query: str) -> str:
    """Strip control characters and enforce length limit."""
    # Remove ASCII control characters (except space/tab)
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", query)
    cleaned = cleaned.strip()[:_MAX_QUERY_LEN]
    if _BLOCKED_PATTERNS.search(cleaned):
        raise ValueError("Query contains disallowed content.")
    return cleaned


def _sanitize_message(message: str) -> str:
    """Strip control characters and enforce length limit for Slack messages."""
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", message)
    cleaned = cleaned.strip()[:_MAX_MESSAGE_LEN]
    if _BLOCKED_PATTERNS.search(cleaned):
        raise ValueError("Message contains disallowed content.")
    return cleaned


# ── MCP Tools ────────────────────────────────────────────────────────────────


@mcp.tool(
    name="search_prices",
    description=(
        "Search the web for current retail prices of a product using SerpAPI. "
        "Returns shopping results and organic search results containing price data. "
        "Requires the SERP_API_KEY environment variable to be set."
    ),
)
def search_prices(query: str) -> dict:
    """Search for product prices.

    Args:
        query: The product search query (e.g. "Google Pixel 9 Pro 128GB price").
               Max 300 characters.

    Returns:
        Dictionary with status and results containing shopping_results /
        organic_results / answer_box fields.
    """
    try:
        sanitized = _sanitize_query(query)
    except ValueError as e:
        return {"status": "error", "message": str(e)}

    logger.info("[MCP] search_prices called with query=%r", sanitized)
    return _search_prices(sanitized)


@mcp.tool(
    name="send_to_slack",
    description=(
        "Deliver a formatted price alert or report to the configured Slack channel "
        "via an Incoming Webhook. Requires the SLACK_WEBHOOK_URL environment variable "
        "to be set. Supports Slack mrkdwn formatting."
    ),
)
def send_to_slack(message: str) -> dict:
    """Send a message to Slack.

    Args:
        message: The Slack-formatted message text (mrkdwn). Max 4 000 characters.

    Returns:
        Dictionary with status and delivery confirmation.
    """
    try:
        sanitized = _sanitize_message(message)
    except ValueError as e:
        return {"status": "error", "message": str(e)}

    logger.info("[MCP] send_to_slack called (message_len=%d)", len(sanitized))
    return _send_to_slack(sanitized)


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Default transport: stdio (standard for local MCP clients)
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    logger.info("Starting PriceGuard MCP server (transport=%s)", transport)
    mcp.run(transport=transport)
