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

from pathlib import Path
from dotenv import load_dotenv
import pytest
from unittest.mock import patch

# Load .env file at the root of the project to ensure API keys are populated during testing
_root_dir = Path(__file__).resolve().parent.parent
_env_path = _root_dir / ".env"
if _env_path.exists():
    load_dotenv(dotenv_path=_env_path)


# ── Mock Gemini API call endpoints to prevent hitting quota limit (429/503) ──

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
    # This must be a coroutine that returns an async generator (awaited by caller)
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

@pytest.fixture(autouse=True, scope="session")
def mock_gemini_api():
    with patch("google.genai.models.AsyncModels.generate_content", new=mock_generate_content), \
         patch("google.genai.models.AsyncModels.generate_content_stream", new=mock_generate_content_stream), \
         patch("google.genai.models.Models.generate_content", new=mock_generate_content_sync), \
         patch("google.genai.models.Models.generate_content_stream", new=mock_generate_content_stream_sync):
        yield
