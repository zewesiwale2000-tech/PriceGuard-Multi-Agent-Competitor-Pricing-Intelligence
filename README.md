# PriceGuard-Multi-Agent-Competitor-Pricing-Intelligence
**PriceGuard** is an automated multi-agent pricing pipeline built with Google's ADK and Gemini. It tracks competitor prices via an MCP-wrapped SerpAPI, applies deterministic business logic against thresholds, and delivers instant alerts to Slack, preventing margin loss without manual input.

---

## Problem Statement

Small e-commerce sellers lose margin daily because manually checking competitor prices is slow, inconsistent, and deprioritized under operational pressure. A seller with 20 SKUs would need to visit dozens of retailer pages every morning, compare prices against their own cost structure, and decide whether to act — before the day's orders even begin. When this doesn't happen, they either undercut themselves unnecessarily or lose sales to a competitor who moved faster.

PriceGuard automates this entire workflow: it searches for current competitor prices, compares them against configurable business thresholds, and delivers a formatted alert or summary directly to Slack — with no manual input required once configured.

---

## Why Agents

A single LLM call is not sufficient for this workflow, and the architecture is deliberately designed around that constraint.

Price lookup requires **tool-use reliability**: querying SerpAPI, parsing structured retail listings, and extracting a trustworthy price figure is a retrieval task, not a reasoning task. Delegating it to a free-form LLM response risks hallucinated prices — the worst possible failure mode for a financial decision tool.

Threshold comparison requires **deterministic logic**: whether $899 is below a $900 threshold is arithmetic, not inference. This step must not be delegated to probabilistic generation.

Alert formatting and delivery require a **different output contract**: the Drafting Agent needs to produce a human-readable, consistently structured Slack message and export clean CSV data — tasks that benefit from LLM language capabilities but must be scoped away from the data-extraction and comparison steps to prevent cross-contamination of concerns.

Splitting these into specialized agents — each with a defined input contract, tool set, and output responsibility — is what makes the system auditable, testable, and safe to run autonomously on a schedule.

---

## Solution Overview

PriceGuard is a three-agent pipeline orchestrated with Google's Agent Development Kit (ADK). A scheduler (or manual trigger) initiates a run. The **AnalystAgent** queries SerpAPI via an MCP Server tool, scores retrieved listings against the target product spec using schema-constrained structured output, and produces either a matched price or a `FAILED_NO_MATCH` flag. If a confident match is found, the matched price is compared against the configured threshold. The **DraftingAgent** then formats the result — a price alert, a summary memo, or an explicit no-match alert — and delivers it to Slack. The **ExportAgent** persists all run data to a rolling master CSV and a per-run PDF, creating a durable audit trail and enabling trend descriptions over time.

---

## Architecture

The system is organized in four layers:

**Trigger Layer** — A business owner or Cloud Scheduler initiates a run, either on demand or via a daily cron. No contact information is requested at runtime; the Slack webhook is configured once during setup.

**Agent Orchestration Layer (Google ADK)** — Three specialized agents run in strict sequence, passing state between them:

| Agent | Responsibility |
|---|---|
| AnalystAgent | SerpAPI lookup → listing scoring → price extraction |
| DraftingAgent | Alert/memo formatting → Slack delivery |
| ExportAgent | Master CSV append → per-run PDF export |

**Tool & Data Layer** — The SerpAPI integration is wrapped as a reusable **MCP Server** tool (`mcp_server.py`), decoupling agent logic from the REST gateway and enabling native invocation from external IDEs such as Cursor and VS Code. Price history is persisted in a rolling master CSV, giving the DraftingAgent the data it needs to describe trends across runs. API credentials are stored outside source control in environment variables.

**Delivery Layer** — Slack webhook push is the primary delivery channel. A PDF memo and CSV file are written to the output folder on every run as a secondary audit record.

### Failure Path

When the AnalystAgent's schema-constrained matcher cannot find a listing that meets the confidence threshold, it sets `match_status = FAILED_NO_MATCH` and short-circuits directly to the DraftingAgent. The DraftingAgent produces an explicit alert — *"No confident competitor match found today. Your price and threshold remain unchanged. No automated action was taken."* — rather than silently passing an untrustworthy figure downstream. This is enforced structurally by ADK's SequentialAgent: the Financial comparison step is simply skipped; it cannot be accidentally entered on a failed match.

---

## Key Concepts Demonstrated

| Component | Role | Rubric Concept |
|---|---|---|
| ADK SequentialAgent | Orchestrates Analyst → Drafting → Export in strict, auditable order | **Agent / Multi-agent (ADK)** |
| MCP Server (`mcp_server.py`) | Wraps SerpAPI as a reusable MCP tool; enables IDE-native invocation | **MCP Server** |
| Schema-constrained matcher (`antigravity_agent.py`) | Gemini structured output scores each listing; sets `FAILED_NO_MATCH` on low confidence; degrades gracefully to standard ADK if package unavailable | **Agent reasoning / safety** |
| Threshold comparison engine | Deterministic Python logic compares extracted price to configured threshold — not delegated to the LLM | **Tool use / reliability** |
| Triple-Shield Security (`security.py`) | Layer 1: env placeholder detection at startup; Layer 2: prompt-injection + control-character filtering; Layer 3: IP-based sliding-window rate limiting | **Security** |
| Master CSV + per-run PDF (ExportAgent) | Persistent price history enables trend descriptions; PDF provides human-readable audit record | **State / persistence** |
| Slack webhook delivery | Configured once at setup; agent never requests contact info at runtime | **Delivery / privacy** |

---

## Demo Walkthrough

### Normal Case

A Cloud Scheduler trigger fires at 06:00. The session is initialized with the target SKU (`Google Pixel 9 Pro 128GB`) and the configured threshold (`$900`).

The AnalystAgent queries SerpAPI, retrieves retail listings, and scores each against the product spec using schema-constrained structured output. It finds a listing at $899 with a match confidence above the threshold. The matched price is passed to state.

The DraftingAgent compares $899 against the $900 threshold, confirms the trigger condition is met, and formats a Slack alert:

> 🚨 **Price Alert: Google Pixel 9 Pro 128GB**
> Competitor price: **$899** — below your threshold of $900.
> Your current listing: $929. Recommended action: review pricing.

The ExportAgent appends the run to the master CSV and writes a PDF memo to the output folder. Total elapsed time: under 30 seconds.

### Failure Case

The AnalystAgent retrieves listings but none score above the confidence threshold — results are either a different storage tier, a bundle, or a third-party seller the spec excludes. `match_status` is set to `FAILED_NO_MATCH`.

The DraftingAgent receives the flag, skips the comparison step entirely, and delivers to Slack:

> ⚠️ **Audit Alert: Google Pixel 9 Pro 128GB**
> No confident competitor match found today.
> Your price and threshold remain unchanged. No automated action was taken.

The ExportAgent still logs the failed run to the master CSV, preserving the audit trail.

---

## Security & Deployment

Security is implemented as a three-layer model in `security.py`, verified in `test_security.py`:

- **Layer 1 — Startup validation**: Active environment placeholder detection prevents the system from running with unconfigured or example credentials.
- **Layer 2 — Input sanitization**: All user-supplied inputs (SKU names, thresholds) are filtered for prompt-injection patterns and control characters before reaching any agent.
- **Layer 3 — Rate limiting**: An IP-based sliding-window middleware prevents abuse of the API surface.

All credentials (`SERP_API_KEY`, `GEMINI_API_KEY`, `SLACK_WEBHOOK_URL`) are stored in environment variables outside source control. The agent never requests or logs credentials at runtime.

The pipeline is containerized and deployable to Cloud Run, with Cloud Scheduler as the trigger for daily automated runs.

---

## Build Process

The project was built using Google ADK as the orchestration framework, with Gemini as the underlying model for both agents. SerpAPI provides the price-data retrieval layer. The MCP Server implementation in `mcp_server.py` was the most significant architectural decision: wrapping the SerpAPI integration as an MCP tool rather than a private agent function means the capability is reusable, testable in isolation, and invocable from external tooling — a meaningful structural choice, not a cosmetic one.

The `antigravity_agent.py` implementation required careful handling: the `google-antigravity` framework enables schema-constrained structured output and multi-step reasoning, but the system degrades gracefully to standard ADK models if the package is unavailable. This fallback was tested explicitly.

The dashboard (`dashboard.py`) was added to close the business intelligence loop — moving beyond isolated alerts to surface price spreads, historical trends, and savings-vs-threshold analytics directly from the persistent master dataset.

---

## Limitations & Future Work

**Current limitations:**
- SerpAPI rate limits constrain how frequently the pipeline can run or how many SKUs it can process in a single batch; high-volume use cases would need a direct retailer API integration or a crawl-based alternative.
- Trend analysis is limited to data accumulated since the master CSV was initialized — there is no pre-populated historical dataset, so trend descriptions are thin in the first week of deployment.
- Slack is the only supported delivery channel in the current release; email and webhook alternatives are architecturally straightforward but not yet implemented.
- Match confidence thresholds are currently hardcoded; a future version would expose these as per-SKU configurable parameters.

**Planned extensions:**
- Per-SKU threshold configuration via a simple inventory CSV, enabling the system to manage a full product catalogue in a single run.
- A lightweight web UI for manual trigger and run-history review, removing the need for direct file-system access to view past memos.
- Multi-retailer scoring in a single run, so the AnalystAgent can report not just the lowest price found but the distribution across named competitors.
