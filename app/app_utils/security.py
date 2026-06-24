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

"""Security utilities for the PriceGuard FastAPI application.

Provides three layers of protection:

1. **Startup key validation** — `validate_required_secrets()` is called once at
   startup and raises `RuntimeError` if any mandatory env var is missing or looks
   like a placeholder, preventing the server from starting in a broken state.

2. **Input sanitisation** — `sanitize_text()` strips control characters and
   rejects known prompt-injection patterns.

3. **Rate limiting** — `RateLimitMiddleware` enforces a sliding-window limit
   (default: 60 requests / 60 seconds) per client IP.  Requests that exceed the
   limit receive a `429 Too Many Requests` response with a `Retry-After` header.
"""

from __future__ import annotations

import collections
import logging
import os
import re
import time
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# ── 1. Startup key validation ─────────────────────────────────────────────────

# Secrets that MUST be present and non-placeholder for the agent to function.
_REQUIRED_SECRETS: list[str] = [
    "GEMINI_API_KEY",
    "SERP_API_KEY",
    "SLACK_WEBHOOK_URL",
]

# Simple heuristics for detecting default / placeholder values.
_PLACEHOLDER_PATTERNS = re.compile(
    r"^(your[-_]?.+|<.+>|changeme|placeholder|example|replace[-_]?me|todo|xxx+)$",
    re.IGNORECASE,
)


def validate_required_secrets(extras: list[str] | None = None) -> None:
    """Verify that all required environment secrets are present and non-trivial.

    Args:
        extras: Additional env-var names to validate beyond the built-in list.

    Raises:
        RuntimeError: If any secret is missing or looks like a placeholder.
    """
    names = _REQUIRED_SECRETS + (extras or [])
    missing: list[str] = []
    placeholders: list[str] = []

    for name in names:
        value = os.environ.get(name, "").strip()
        if not value:
            missing.append(name)
        elif _PLACEHOLDER_PATTERNS.match(value):
            placeholders.append(name)

    errors: list[str] = []
    if missing:
        errors.append(f"Missing required env vars: {', '.join(missing)}")
    if placeholders:
        errors.append(
            f"Env vars still contain placeholder values: {', '.join(placeholders)}"
        )

    if errors:
        raise RuntimeError(
            "PriceGuard startup failed — secrets not configured correctly:\n"
            + "\n".join(f"  • {e}" for e in errors)
        )

    logger.info("[security] All required secrets validated (%d checked).", len(names))


# ── 2. Input sanitisation ─────────────────────────────────────────────────────

_MAX_INPUT_LEN = 2000

# Patterns that indicate prompt-injection or XSS attempts.
_INJECTION_PATTERNS = re.compile(
    r"(ignore\s+(?:previous|all|above)|disregard|system\s+prompt"
    r"|jailbreak|<script[\s>]|javascript:|data:text/html)",
    re.IGNORECASE,
)

# ASCII control characters (excluding \t, \n, \r which are legitimate in text).
_CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_text(text: str, max_len: int = _MAX_INPUT_LEN) -> str:
    """Sanitize a user-supplied text string.

    Strips control characters, truncates to *max_len*, and raises
    ``ValueError`` if injection patterns are detected.

    Args:
        text: The raw input string.
        max_len: Maximum allowed length after stripping (default 2 000).

    Returns:
        The cleaned, truncated string.

    Raises:
        ValueError: If the text contains disallowed injection patterns.
    """
    cleaned = _CONTROL_CHAR_PATTERN.sub("", text)
    cleaned = cleaned.strip()[:max_len]

    if _INJECTION_PATTERNS.search(cleaned):
        logger.warning("[security] Injection pattern detected in input.")
        raise ValueError(
            "Input contains disallowed content. Please rephrase your request."
        )

    return cleaned


# ── 3. Rate limiting middleware ───────────────────────────────────────────────


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window per-IP rate limiter.

    Args:
        app: The ASGI app to wrap.
        max_requests: Maximum number of requests allowed in the window.
        window_seconds: Length of the sliding window in seconds.
        exempt_paths: URL paths to skip (e.g. health-check endpoints).
    """

    def __init__(
        self,
        app,
        max_requests: int = 60,
        window_seconds: int = 60,
        exempt_paths: list[str] | None = None,
    ) -> None:
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.exempt_paths: set[str] = set(exempt_paths or ["/healthz", "/readyz"])
        # {ip: deque of request timestamps}
        self._windows: dict[str, collections.deque] = collections.defaultdict(
            collections.deque
        )
        logger.info(
            "[security] RateLimitMiddleware: %d req / %ds window",
            max_requests,
            window_seconds,
        )

    def _get_client_ip(self, request: Request) -> str:
        """Extract the real client IP, respecting X-Forwarded-For."""
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # Take the leftmost (original client) IP
            return forwarded_for.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in self.exempt_paths:
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        now = time.monotonic()
        window_start = now - self.window_seconds

        dq = self._windows[client_ip]

        # Evict timestamps outside the current window
        while dq and dq[0] < window_start:
            dq.popleft()

        if len(dq) >= self.max_requests:
            retry_after = int(self.window_seconds - (now - dq[0])) + 1
            logger.warning(
                "[security] Rate limit exceeded for IP %s (%d req in window)",
                client_ip,
                len(dq),
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too many requests. Please slow down.",
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        dq.append(now)
        return await call_next(request)
