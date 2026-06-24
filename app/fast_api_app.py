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
import os
from pathlib import Path
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent.parent / ".env"
    if _env_path.exists():
        load_dotenv(dotenv_path=_env_path)
except ImportError:
    pass

if os.getenv("INTEGRATION_TEST") == "TRUE":
    import unittest.mock
    
    async def mock_generate_content(*args, **kwargs):
        from google.genai import types
        return types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(
                        parts=[types.Part.from_text(text="Mocked Gemini response: Product Name: Mock Product, Lowest Price: $100.00, Merchant: Amazon, Link: http://example.com/mock")]
                    )
                )
            ]
        )

    async def mock_generate_content_stream(*args, **kwargs):
        async def stream_generator():
            from google.genai import types
            yield types.GenerateContentResponse(
                candidates=[
                    types.Candidate(
                        content=types.Content(
                            parts=[types.Part.from_text(text="Mocked Gemini response stream chunk")]
                        )
                    )
                ]
            )
        return stream_generator()

    def mock_generate_content_sync(*args, **kwargs):
        from google.genai import types
        return types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(
                        parts=[types.Part.from_text(text="Mocked Gemini response: Product Name: Mock Product, Lowest Price: $100.00, Merchant: Amazon, Link: http://example.com/mock")]
                    )
                )
            ]
        )

    def mock_generate_content_stream_sync(*args, **kwargs):
        from google.genai import types
        yield types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(
                        parts=[types.Part.from_text(text="Mocked Gemini response stream chunk")]
                    )
                )
            ]
        )

    unittest.mock.patch("google.genai.models.AsyncModels.generate_content", new=mock_generate_content).start()
    unittest.mock.patch("google.genai.models.AsyncModels.generate_content_stream", new=mock_generate_content_stream).start()
    unittest.mock.patch("google.genai.models.Models.generate_content", new=mock_generate_content_sync).start()
    unittest.mock.patch("google.genai.models.Models.generate_content_stream", new=mock_generate_content_stream_sync).start()


import google.auth
from fastapi import FastAPI
from google.adk.cli.fast_api import get_fast_api_app
from google.cloud import logging as google_cloud_logging

from app.app_utils.security import RateLimitMiddleware, validate_required_secrets
from app.app_utils.telemetry import setup_telemetry
from app.app_utils.typing import Feedback

# ── Startup security checks ─────────────────────────────────────────────────
# Validate all required secrets before anything else is initialised.
# This prevents the server from starting in a silently broken state.
try:
    validate_required_secrets()
except RuntimeError as _secret_error:
    import logging as _logging

    _logging.getLogger(__name__).critical("[startup] %s", _secret_error)
    # Re-raise so Cloud Run / the process supervisor sees a non-zero exit.
    raise

setup_telemetry()
import logging
try:
    _, project_id = google.auth.default()
    logging_client = google_cloud_logging.Client()
    logger = logging_client.logger(__name__)
    _use_gcp_logging = True
except Exception:
    project_id = None
    logger = logging.getLogger(__name__)
    _use_gcp_logging = False
allow_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else None
)

# Artifact bucket for ADK (created by Terraform, passed via env var)
logs_bucket_name = os.environ.get("LOGS_BUCKET_NAME")

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# In-memory session configuration - no persistent storage
session_service_uri = None

artifact_service_uri = f"gs://{logs_bucket_name}" if logs_bucket_name else None

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=True,
    artifact_service_uri=artifact_service_uri,
    allow_origins=allow_origins,
    session_service_uri=session_service_uri,
    otel_to_cloud=_use_gcp_logging,
)
app.title = "priceguard"
app.description = "API for interacting with the Agent priceguard"

# ── Security middleware ──────────────────────────────────────────────────────
# Per-IP sliding-window rate limiter: 60 requests per 60 seconds by default.
# Override via RATE_LIMIT_MAX_REQUESTS / RATE_LIMIT_WINDOW_SECONDS env vars.
app.add_middleware(
    RateLimitMiddleware,
    max_requests=int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "60")),
    window_seconds=int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60")),
    exempt_paths=["/healthz", "/readyz", "/docs", "/openapi.json"],
)


@app.post("/feedback")
def collect_feedback(feedback: Feedback) -> dict[str, str]:
    """Collect and log feedback.

    Args:
        feedback: The feedback data to log

    Returns:
        Success message
    """
    if _use_gcp_logging:
        logger.log_struct(feedback.model_dump(), severity="INFO")
    else:
        logger.info("Feedback received: %s", feedback.model_dump())
    return {"status": "success"}


# Main execution
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
