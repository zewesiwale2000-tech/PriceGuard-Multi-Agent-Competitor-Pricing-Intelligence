# PriceGuard: Autonomous Multi-Agent Competitor Pricing Intelligence

**PriceGuard** is an automated multi-agent pricing pipeline built with Google's ADK and Gemini. It tracks competitor prices via SerpAPI, applies deterministic business logic against thresholds, and delivers instant alerts to Slack, preventing margin loss without manual input.

---

## 1. Problem Statement & Business Context

Small e-commerce sellers lose margin daily because manually checking competitor prices is slow, inconsistent, and deprioritized under operational pressure. A seller with 20 SKUs would need to visit dozens of retailer pages every morning, compare prices against their own cost structure, and decide whether to act — before the day's orders even begin. When this doesn't happen, they either undercut themselves unnecessarily or lose sales to a competitor who moved faster.

PriceGuard automates this entire workflow: it searches for current competitor prices, compares them against configurable business thresholds, and delivers a formatted alert or summary directly to Slack — with no manual input required once configured.

### Why Multi-Agent?
A single LLM call is not sufficient for this workflow, and the architecture is deliberately designed around that constraint:
* **Tool-Use Reliability**: Querying SerpAPI, parsing structured retail listings, and extracting a trustworthy price figure is a retrieval task, not a reasoning task. Delegating it to a free-form LLM response risks hallucinated prices — the worst possible failure mode for a financial decision tool.
* **Deterministic Logic**: Whether $899 is below a $900 threshold is arithmetic, not inference. This step must not be delegated to probabilistic generation.
* **Separation of Concerns**: The Drafting Agent needs to produce a human-readable, consistently structured Slack message and export clean CSV data — tasks that benefit from LLM language capabilities but must be scoped away from the data-extraction and comparison steps to prevent cross-contamination of concerns.

---

## 2. Project Structure

```
priceguard/
├── app/                  # Core agent code
│   ├── agent.py               # Main agent sequential orchestration
│   ├── antigravity_agent.py   # Enhanced reasoning agent using google-antigravity
│   ├── fast_api_app.py        # FastAPI server gateway with security shields
│   ├── mcp_server.py          # FastMCP server for IDE tool exposure
│   ├── tools.py               # Integrations (SerpAPI, Slack, ReportLab PDF)
│   └── app_utils/             # Security middleware and telemetry helpers
├── tests/                # Unit, integration, and load tests
├── data/                 # Persistent master price database
├── exports/              # Generated per-run CSV & PDF reports
├── GEMINI.md             # AI-assisted development guide
└── pyproject.toml        # Project dependencies
```

---

## 3. Requirements & Quick Start

### Prerequisites
Before you begin, ensure you have:
* **uv**: Python package manager - [Install](https://docs.astral.sh/uv/getting-started/installation/)
* **agents-cli**: Agents CLI - Install with `uv tool install google-agents-cli`
* **Google Cloud SDK**: For GCP services - [Install](https://cloud.google.com/sdk/docs/install)

### Setup & Play
1. Install dependencies:
   ```bash
   agents-cli install
   ```
2. Launch local interactive development environment (playground):
   ```bash
   agents-cli playground
   ```
3. Generate the BI dashboard from collected history:
   ```bash
   uv run python dashboard.py
   ```

---

## 4. Development Commands

| Command | Description |
| :--- | :--- |
| `agents-cli install` | Install dependencies using uv |
| `agents-cli playground` | Launch local development web interface |
| `agents-cli lint` | Run code quality checks |
| `uv run pytest tests/unit tests/integration` | Run offline unit and integration tests |
| `agents-cli eval` | Run agent quality evaluations (generate, grade, compare) |
| `agents-cli deploy` | Deploy code directly to Cloud Run |

---

## 5. Architectural Blueprint

The system is organized in four layers:

* **Trigger Layer** — A business owner or Cloud Scheduler initiates a run, either on demand or via a daily cron. The Slack webhook is configured once during setup.
* **Agent Orchestration Layer (Google ADK)** — Three specialized agents run in strict sequence, passing state between them:
  * **AnalystAgent**: SerpAPI lookup → listing scoring → price extraction.
  * **DraftingAgent**: Alert/memo formatting → Slack delivery.
  * **ExportAgent**: Master CSV append → per-run PDF export.
* **Tool & Data Layer** — The SerpAPI integration is wrapped as a reusable **MCP Server** tool (`mcp_server.py`), decoupling agent logic from the REST gateway and enabling native invocation from external IDEs. Price history is persisted in a rolling master CSV.
* **Delivery Layer** — Slack webhook push is the primary delivery channel. A PDF memo and CSV file are written to the output folder on every run as a secondary audit record.

### Failure Path
When the AnalystAgent's schema-constrained matcher cannot find a listing that meets the confidence threshold, it sets `match_status = FAILED_NO_MATCH` and short-circuits directly to the DraftingAgent. The DraftingAgent produces an explicit alert — *"No confident competitor match found today. Your price and threshold remain unchanged. No automated action was taken."* — rather than silently passing an untrustworthy figure downstream.

---

## 6. Key Rubrics & Concepts Demonstrated

| Component | Role | Rubric Concept |
|---|---|---|
| **ADK SequentialAgent** | Orchestrates Analyst → Drafting → Export in strict, auditable order | **Agent / Multi-agent (ADK)** |
| **MCP Server (`mcp_server.py`)** | Wraps SerpAPI as a reusable MCP tool; enables IDE-native invocation | **MCP Server** |
| **Schema-constrained matcher** | Gemini structured output scores each listing; sets `FAILED_NO_MATCH` on low confidence | **Agent reasoning / safety** |
| **Threshold comparison engine** | Deterministic Python logic compares extracted price to configured threshold | **Tool use / reliability** |
| **Triple-Shield Security (`security.py`)** | Layer 1: startup env validation; Layer 2: input sanitization; Layer 3: IP rate limiting | **Security** |
| **Master CSV + PDF (ExportAgent)** | Persistent price history enables trend descriptions; PDF provides human-readable audit record | **State / persistence** |

---

## 7. Demo Walkthrough

### Normal Case
A Cloud Scheduler trigger fires. The session is initialized with the target SKU (`Google Pixel 9 Pro 128GB`) and the configured threshold (`$900`).

The AnalystAgent queries SerpAPI, retrieves retail listings, and scores each against the product spec using schema-constrained structured output. It finds a listing at $899 with a match confidence above the threshold. The matched price is passed to state.

The DraftingAgent compares $899 against the $900 threshold, confirms the trigger condition is met, and formats a Slack alert:
> 🚨 **Price Alert: Google Pixel 9 Pro 128GB**
> Competitor price: **$899** — below your threshold of $900.
> Your current listing: $929. Recommended action: review pricing.

The ExportAgent appends the run to the master CSV and writes a PDF memo to the output folder.

---

## 8. Security & Deployment

Security is implemented as a three-layer model in `security.py`, verified in `test_security.py`:
* **Layer 1 — Startup validation**: Active environment placeholder detection prevents the system from running with unconfigured or example credentials.
* **Layer 2 — Input sanitization**: All user-supplied inputs are filtered for prompt-injection patterns and control characters.
* **Layer 3 — Rate limiting**: An IP-based sliding-window middleware prevents abuse of the API surface.

The pipeline is containerized and deployable to Cloud Run, with Cloud Scheduler as the trigger for daily automated runs.

