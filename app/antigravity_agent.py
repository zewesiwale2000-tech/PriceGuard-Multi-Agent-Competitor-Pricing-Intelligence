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

"""Antigravity-powered analyst agent for PriceGuard.

This module wires up the ``google-antigravity`` SDK to give the
AnalystAgent enhanced reasoning capabilities:

* **Deep multi-step search** — Antigravity can decide to issue follow-up
  queries autonomously when the first search returns ambiguous results.
* **Structured extraction** — The SDK's built-in structured-output planner
  pulls price, merchant, and link into a typed ``PriceResult`` without
  brittle regex.
* **Fallback** — If the ``google-antigravity`` package is not installed the
  module degrades gracefully to the standard ADK ``Agent`` so the rest of
  the pipeline continues to work.

Usage (in ``agent.py``):
    from app.antigravity_agent import make_antigravity_analyst
    analyst_agent = make_antigravity_analyst()
"""

from __future__ import annotations

import importlib.util
import logging
import os
from typing import Any

from google.adk.agents import Agent
from google.adk.models import Gemini
from google.genai import types

from app.tools import search_prices

logger = logging.getLogger(__name__)

# ── Try to import the Antigravity SDK ────────────────────────────────────────

# Check if the 'antigravity' module exists and is a package (to avoid Python's built-in easter egg module)
_spec = importlib.util.find_spec("antigravity")
_ANTIGRAVITY_AVAILABLE = False

if _spec is not None and _spec.submodule_search_locations is not None:
    try:
        from antigravity import AntigravityClient  # type: ignore[import]
        from antigravity.adk import AntigravityAgent  # type: ignore[import]

        _ANTIGRAVITY_AVAILABLE = True
        logger.info("[antigravity] SDK loaded successfully.")
    except ImportError:
        pass

if not _ANTIGRAVITY_AVAILABLE:
    logger.warning(
        "[antigravity] google-antigravity package not found. "
        "Falling back to standard ADK Agent. "
        "Install with: uv add google-antigravity"
    )

# ── Shared agent instruction ─────────────────────────────────────────────────

_ANALYST_INSTRUCTION = """\
You are the AnalystAgent for PriceGuard — an expert price research assistant.

Your task:
1. Use the search_prices tool to find current retail prices for the requested product.
2. Examine BOTH shopping_results and organic_results carefully.
3. Identify the single LOWEST price currently available, along with the merchant name
   and a direct product link.
4. Compare the price to any user-specified threshold.
5. If the first search returns no useful price data, refine and retry the query
   (e.g. add "price" or the expected currency to the query string).

Provide a structured summary:
- **Product Name**: exact product name as found
- **Lowest Price**: price with currency symbol
- **Merchant**: store or retailer name
- **Link**: direct URL (or "Not found")
- **Threshold Status**: "✅ Below $<threshold>" | "❌ Above $<threshold>" | "N/A"
- **Confidence**: High / Medium / Low based on how many price data points were found
"""


# ── Antigravity client factory ───────────────────────────────────────────────


def _build_antigravity_client() -> Any | None:
    """Instantiate the AntigravityClient from env vars."""
    if not _ANTIGRAVITY_AVAILABLE:
        return None

    api_key = os.environ.get("ANTIGRAVITY_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.warning(
            "[antigravity] No ANTIGRAVITY_API_KEY or GEMINI_API_KEY found; "
            "falling back to standard agent."
        )
        return None

    try:
        client = AntigravityClient(api_key=api_key)
        logger.info("[antigravity] AntigravityClient initialised.")
        return client
    except Exception as exc:
        logger.warning("[antigravity] Failed to init client: %s", exc)
        return None


# ── Public factory ───────────────────────────────────────────────────────────


def make_antigravity_analyst(
    model: str = "gemini-flash-latest",
    output_key: str = "price_analysis_result",
) -> Agent:
    """Build and return the AnalystAgent, using Antigravity if available.

    When the ``google-antigravity`` SDK is installed and configured, this
    returns an ``AntigravityAgent`` that leverages enhanced multi-step
    reasoning.  Otherwise it returns a standard ``google.adk.agents.Agent``
    so the rest of the pipeline is unaffected.

    Args:
        model: Gemini model identifier to use.
        output_key: State key where the agent writes its analysis result.

    Returns:
        An ADK-compatible Agent (or AntigravityAgent subclass).
    """
    antigravity_client = _build_antigravity_client()

    if antigravity_client is not None:
        logger.info("[antigravity] Building AntigravityAgent (model=%s).", model)
        try:
            agent = AntigravityAgent(
                name="analyst_agent",
                client=antigravity_client,
                model=model,
                instruction=_ANALYST_INSTRUCTION,
                tools=[search_prices],
                output_key=output_key,
                # Antigravity-specific options
                max_reasoning_steps=2,  # allow up to 2 internal think steps
                enable_structured_output=True,  # extract fields into typed dict
            )
            logger.info("[antigravity] AntigravityAgent ready.")
            return agent
        except Exception as exc:
            logger.warning(
                "[antigravity] AntigravityAgent construction failed (%s); "
                "falling back to standard Agent.",
                exc,
            )

    # ── Fallback: standard ADK Agent ─────────────────────────────────────────
    logger.info("[antigravity] Using standard ADK Agent (model=%s).", model)
    return Agent(
        name="analyst_agent",
        model=Gemini(
            model=model,
            retry_options=types.HttpRetryOptions(
                attempts=6,
                initialDelay=1.0,
                maxDelay=15.0,
                httpStatusCodes=[429, 500, 503, 504],
            ),
        ),
        instruction=_ANALYST_INSTRUCTION,
        tools=[search_prices],
        output_key=output_key,
    )
