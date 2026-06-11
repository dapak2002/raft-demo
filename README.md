# Order Query Agent

## Overview

The customer API returns orders as messy free-form text. This agent closes that gap: you ask a question, it fetches the raw records, structures them, applies your criteria, and returns JSON data.

The LLM is deliberately kept out of the final answer. It parses text and proposes filters; Python applies those filters and formats the response. That split keeps output deterministic and easier to reason about.

## Quick start

**1. Install dependencies**

```bash
pip install -r requirements.txt
```

**2. Set credentials**

Create a `.env` file in the project root (or export in your shell):

```
OPENROUTER_API_KEY=your-key-here
CUSTOMER_API_URL=http://localhost:5001   # optional; this is the default
```

**3. Run the agent**

```bash
python main.py
# prompts: Enter your query:
```

**4. Web UI (optional)**

```bash
python web_app.py
# open http://localhost:8080
```

The UI streams an ordered execution trace (including plan/review loops), surfaces errors, and renders matching orders in a table.

## Example

**Input**

```
Show me all orders where the buyer was located in Ohio and total value was over 500.
```

**Output**

```json
{
  "status": "ok",
  "error": null,
  "user_query": "Show me all orders where the buyer was located in Ohio and total value was over 500.",
  "data_query": {
    "filter": {
      "operator": "and",
      "filters": [
        { "field": "state", "operator": "equals", "value": "OH" },
        { "field": "total", "operator": "gt", "value": 500 }
      ]
    }
  },
  "orders": [
    {
      "orderId": "1001",
      "buyer": "John Davis",
      "city": "Columbus",
      "state": "OH",
      "total": 742.1,
      "items": ["laptop", "hdmi cable"]
    },
    {
      "orderId": "1003",
      "buyer": "Mike Turner",
      "city": "Cleveland",
      "state": "OH",
      "total": 1299.99,
      "items": ["gaming pc", "mouse"]
    },
    {
      "orderId": "1005",
      "buyer": "Chris Myers",
      "city": "Cincinnati",
      "state": "OH",
      "total": 512.0,
      "items": ["monitor", "desk lamp"]
    }
  ]
}
```

**Error cases** — `status` is `"error"` with a message and empty `orders` when fetch fails, nothing could be parsed, or a filtered query could not produce any filter conditions. `main.py` exits with code 1 on error.

The upstream API response looks like this — the agent has to make sense of the text, not just read fields:

```json
{
  "status": "ok",
  "raw_orders": [
    "Order 1001: Buyer=John Davis, Location=Columbus, OH, Total=$742.10, Items: laptop, hdmi cable"
  ]
}
```

## Architecture

The graph has two phases — **ingest** (fetch → parse → merge) and **query** (plan → review → validate → execute). All paths route to a single `respond` node with `status` of `ok` or `error`.

```
fetch ──Send(parse_record)──▶ parse_record ──▶ merge_parse ──▶ plan ◀──┐
  │              │ (fan-out)      │ (reduce)       │                    │
  │              └─ one task      dedupe/sort      review_plan ─────────┘
  │                per record                      (max 3 attempts on edge)
  │                                                   │
  │                                                   ▼
  │                                             validate_plan ──▶ execute ──▶ respond
  │                                                   │
  └───────────────────────────────────────────────────┴──────────────────────────▶ respond
         (fetch / parse / plan errors)
```

**State flow:** `raw_orders` → `parsed_orders` → `plan` → `matched_orders`

**LangGraph patterns:**

- **Map-reduce parse** — `fetch` fans out with `Send("parse_record", …)`; each task appends to `parsed_orders` via a custom reducer. `merge_parse` dedupes by `orderId`, sorts, and replaces the list with `("replace", merged)`.
- **Single plan node** — `plan` runs the full LLM tool-calling loop internally (no separate tool-execution graph node).
- **Review loop on edges** — `review_plan` only judges completeness; the retry cap (`plan_attempts >= 3`) is enforced by a conditional edge in `graph.py`, so the limit is visible in the graph topology.
- **Fault tolerance** — I/O nodes (`fetch`, `parse_record`, `plan`, `review_plan`) use LangGraph `RetryPolicy`, `TimeoutPolicy`, and a shared `error_handler` that routes to `respond` after retries are exhausted. Deterministic nodes skip retries.

**LLM touchpoints:** `parse_record` (structured extraction), `plan` (tool-only filter planning), `review_plan` (plan completeness check). Everything else is Python.

**Routing:** conditional edge functions live in `agent/graph.py` alongside graph wiring.

### Ingest phase


| Node           | Role                                                                                                           |
| -------------- | -------------------------------------------------------------------------------------------------------------- |
| `fetch`        | Pulls raw order strings from the customer API; fans out one `Send` per record                                  |
| `parse_record` | LLM structured extraction into the six canonical `Order` fields (Pydantic)                                     |
| `merge_parse`  | Reduce step: dedupe by `orderId` (keep richest record), sort, replace `parsed_orders`; error if nothing parsed |


Long records are windowed with overlap (`PARSE_MAX_CHARS` / `PARSE_CHUNK_OVERLAP`), capped at `PARSE_MAX_WINDOWS` LLM calls per record. User queries and plan prompts are bounded via `agent/llm_limits.py`. The LLM maps source labels onto the six canonical fields defined in `agent/schema.py` (`Order` Pydantic model). Unmapped source labels (e.g. `Warehouse`) are captured in `additional_fields` and logged as schema drift — they do not affect filtering.

### Order Lookup Design Caveat

Single-order requests (e.g. "show order 1005") do not call the provided `GET /api/order/<id>` due to a known bug in the customer API. The agent bulk-fetches `/api/orders`, parses, and filters on `orderId`.

- A dedicated fetch-by-id tool would be the normal production pattern.
- The per-id route has a **known substring bug**, so lookup `1001` can also match `Order 10010`.
- Duplicate `orderId` values from bulk fetch are deduped in `merge_parse` (richest record wins).
- Single-order queries still work: filtering on one `orderId` returns exactly one order.

### Query phase


| Node            | Role                                                                                     |
| --------------- | ---------------------------------------------------------------------------------------- |
| `plan`          | LLM tool-calling loop in one node; builds `plan` (`QueryPlan`)                           |
| `review_plan`   | Validates plan completeness, detects match-all queries; retry cap enforced on graph edge |
| `validate_plan` | Accepts match-all (clears stray filters); errors if a filtered query produced no filters |
| `execute`       | Applies the plan in Python (`agent/services/filter_engine.py`)                           |
| `respond`       | Sets final `status`                                                                      |


The LLM builds a **boolean expression tree** for each query: `Filter` leaves hold field comparisons (`state equals OH`, `total gt 500`), and `FilterGroup` nodes combine children with **AND** or **OR**. That tree is stored in `QueryPlan` and walked deterministically by `filter_engine.py` at execute time — no LLM in the final filter step.


| Tool               | Use                                                                 |
| ------------------ | ------------------------------------------------------------------- |
| `add_filter`       | One condition (e.g. state = OH, total > 500)                        |
| `combine_filters`  | Group conditions with AND or OR — same-field or cross-field         |


Supported operators by field (defined in `agent/schema.py`):


| Field   | Operators                            |
| ------- | ------------------------------------ |
| orderId | equals, not_equals                   |
| buyer   | equals, not_equals, contains         |
| city    | equals, not_equals, contains         |
| state   | equals, not_equals                   |
| total   | equals, not_equals, gt, gte, lt, lte |
| items   | equals, not_equals, contains         |


## Configuration

Only two values come from the environment — the OpenRouter API key and the customer API URL. Everything else is a plain variable in `config.py`; edit the file directly to tune timeouts, retry limits, parse window sizes, and prompt bounds.

### Environment variables


| Variable             | Default                 | Description           |
| -------------------- | ----------------------- | --------------------- |
| `OPENROUTER_API_KEY` | —                       | Required              |
| `CUSTOMER_API_URL`   | `http://localhost:5001` | Customer API base URL |


### `config.py` variables


| Variable                     | Default                 | Description                                    |
| ---------------------------- | ----------------------- | ---------------------------------------------- |
| `OPENROUTER_BASE_URL`        | `https://openrouter.ai/api/v1` | OpenRouter API base URL                   |
| `MODEL`                      | `openai/gpt-oss-120b:exacto`   | LLM model ID                              |
| `FETCH_TIMEOUT_SECONDS`      | `30`                    | HTTP timeout for fetch                         |
| `LLM_TIMEOUT_SECONDS`        | `60`                    | OpenRouter request timeout                     |
| `LLM_MAX_RETRIES`            | `3`                     | OpenRouter retry count                         |
| `NODE_MAX_RETRIES`           | `3`                     | LangGraph per-node retry attempts (I/O nodes)  |
| `FETCH_NODE_TIMEOUT_SECONDS` | `45`                    | LangGraph wall-clock cap on `fetch` attempts   |
| `LLM_NODE_TIMEOUT_SECONDS`   | `90`                    | LangGraph wall-clock cap on LLM node attempts  |
| `PARSE_MAX_CHARS`            | `4000`                  | Characters per parse window                    |
| `PARSE_CHUNK_OVERLAP`        | `500`                   | Overlap between windows                        |
| `PARSE_MAX_WINDOWS`          | `20`                    | Max LLM parse calls per order record           |
| `PARSE_MAX_WORKERS`          | `5`                     | Max concurrent `Send(parse_record)` tasks      |
| `MAX_PLAN_ATTEMPTS`          | `3`                     | Review loop retry cap (enforced on graph edge) |
| `USER_QUERY_MAX_CHARS`       | `2000`                  | Max natural-language query length              |
| `PLAN_MAX_TOOL_TURNS`        | `8`                     | Max tool-calling rounds in `plan`              |
| `PLAN_FEEDBACK_MAX_CHARS`    | `500`                   | Max review feedback injected into re-plan      |
| `REVIEW_PLAN_MAX_JSON_CHARS` | `8000`                  | Max serialized filter tree in review prompt    |

## Project layout

```
agent/
  graph.py              # Graph wiring, routing, and fault-tolerance policies
  fault_tolerance.py    # RetryPolicy, TimeoutPolicy, and error handlers
  schema.py             # Order model, Operator enum, field schema (single source of truth)
  state.py              # AgentState, FilterGroup, QueryPlan, parsed_orders reducer
  llm.py                # OpenRouter client (openai/gpt-oss-120b:exacto)
  llm_limits.py         # Prompt truncation and parse/plan bounds
  services/
    filter_engine.py    # Boolean expression tree evaluation
    schema_drift.py     # Logs unexpected API / parse fields
  nodes/
    fetch.py            # Customer API fetch
    parse_record.py     # parse_record node (one Send task per record)
    merge_parse.py      # Reduce step after Send fan-out
    plan.py             # Filter planning (internal tool loop)
    review_plan.py      # LLM completeness check; sets plan_complete or plan_feedback
    validate_plan.py    # Rejects incomplete plans; allows match-all (empty filter tree)
    execute.py          # Applies filter tree in Python; sets matched_orders
    respond.py          # Terminal node; confirms final status before END
  tools/
    fetch_orders.py
    create_filter.py    # Filter tool schemas + execution helpers
config.py               # Settings — env for key/API URL; edit variables for tuning
main.py
web_app.py              # Flask UI with SSE node progress
static/                 # Frontend assets (index.html, app.js, style.css)
```

## Future Improvements

- **Chat / session state** — add LangGraph checkpointer so follow-up messages can reuse cached `parsed_orders` without re-fetching
- **Input guardrails** — reject prompt injection for each LLM call and could add an intent check for off-topic requests before the graph runs
- **Introduce Tokenizer** — use tokenizer instead of max characters for calculating input size
- **Richer query options** — nested conditions, sorting, aggregates, order comparison
- **Semantic field/item search** — RAG tool so queries like "lighting" match orders with "lamp"
- **Eval harness** — golden prompt sets per node so model/workflow changes do not regress behavior
