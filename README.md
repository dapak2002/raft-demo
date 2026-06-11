# Raft AI Agent Coding Challenge

## Overview

The customer API returns orders as messy free-form text. This agent closes that gap: you ask a question, it fetches the raw records, structures them, applies your criteria, and returns JSON data.

The LLM is deliberately kept out of the final answer. It parses text and proposes filters; Python applies those filters and formats the response. That split keeps output deterministic and easier to reason about.

## Running locally

**1. Install dependencies**

```bash
pip install -r requirements.txt
```

**2. Run the agent**

Set `OPENROUTER_API_KEY` in your environment or a `.env` file in the project root. The agent expects a customer API at `CUSTOMER_API_URL` (default `http://localhost:5001`).

```bash
# Interactive CLI:
python main.py

# Pass a query directly:
python main.py "Show me all orders where the buyer was located in Ohio and total value was over 500."
```

## Configuration

All settings live in `config.py`. Environment variables are loaded via `python-dotenv` (from a `.env` file or your shell), but you can also edit `config.py` directly to change defaults — for example `MODEL`, `OPENROUTER_BASE_URL`, timeouts, parse window sizes, and retry limits.

| Variable                | Default                 | Description                                    |
| ----------------------- | ----------------------- | ---------------------------------------------- |
| `OPENROUTER_API_KEY`    | —                       | Required                                       |
| `CUSTOMER_API_URL`      | `http://localhost:5001` | Customer API base URL                          |
| `FETCH_TIMEOUT_SECONDS` | `30`                    | HTTP timeout for fetch                         |
| `LLM_TIMEOUT_SECONDS`   | `60`                    | OpenRouter request timeout                     |
| `LLM_MAX_RETRIES`       | `3`                     | OpenRouter retry count                         |
| `PARSE_MAX_CHARS`       | `4000`                  | Characters per parse window                    |
| `PARSE_CHUNK_OVERLAP`   | `500`                   | Overlap between windows                        |
| `PARSE_MAX_WORKERS`     | `5`                     | Max concurrent `Send(parse_record)` tasks      |
| `MAX_PLAN_ATTEMPTS`     | `3`                     | Review loop retry cap (enforced on graph edge) |

The graph compiles once at import and is reused across queries.

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
    "groups": [
      {
        "logic": "and",
        "filters": [
          { "field": "state", "operator": "equals", "value": "OH" },
          { "field": "total", "operator": "gt", "value": 500 }
        ]
      }
    ]
  },
  "orders": [
    { "orderId": "1001", "buyer": "John Davis", "state": "OH", "total": 742.1 },
    { "orderId": "1003", "buyer": "Mike Turner", "state": "OH", "total": 1299.99 },
    { "orderId": "1005", "buyer": "Chris Myers", "state": "OH", "total": 512.0 }
  ]
}
```

**OR query** — `orders from texas or ohio` uses `add_or_filter_group` and returns orders in TX and OH.

**Cross-field OR** — `orders from chris or texas` uses `add_mixed_or_group` on buyer and state.

**Match-all** — `show all orders` is detected during plan review (`match_all=true`); empty `data_query` returns every parsed order.

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

**LLM touchpoints:** `parse_record` (structured extraction), `plan` (tool-only filter planning), `review_plan` (plan completeness check). Everything else is Python.

**Routing:** conditional edge functions live in `agent/graph.py` alongside graph wiring.

### Ingest phase

| Node           | Role                                                                                                           |
| -------------- | -------------------------------------------------------------------------------------------------------------- |
| `fetch`        | Pulls raw order strings from the customer API; fans out one `Send` per record                                  |
| `parse_record` | LLM extraction into fixed fields, then normalization and grounding checks                                    |
| `merge_parse`  | Reduce step: dedupe by `orderId` (keep richest record), sort, replace `parsed_orders`; error if nothing parsed |

Long records are windowed with overlap (`PARSE_MAX_CHARS` / `PARSE_CHUNK_OVERLAP`). After extraction, `field_normalize.py` maps aliases to the fixed schema and logs schema drift for unknown fields. `parse_grounding.py` rejects records whose values are not supported by the source text (hallucination guard).

### Order Lookup Design Caveat

Single-order requests (e.g. "show order 1005") do not call the provided `GET /api/order/<id>` due to a known bug in the customer API. The agent bulk-fetches `/api/orders`, parses, and filters on `orderId`.

- A dedicated fetch-by-id tool would be the normal production pattern.
- The per-id route has a **known substring bug**, so lookup `1001` can also match `Order 10010`.
- Duplicate `orderId` values from bulk fetch are deduped in `merge_parse` (richest record wins).
- Single-order queries still work: filtering on one `orderId` returns exactly one order.

### Query phase

| Node            | Role                                                                                              |
| --------------- | ------------------------------------------------------------------------------------------------- |
| `plan`          | LLM tool-calling loop in one node; builds `plan` (`QueryPlan`)                                    |
| `review_plan`   | Validates plan completeness, detects match-all queries; retry cap enforced on graph edge          |
| `validate_plan` | Accepts match-all (clears stray filters); errors if a filtered query produced no filters            |
| `execute`       | Applies the plan in Python (`agent/services/filter_engine.py`)                                    |
| `respond`       | Sets final `status`                                                                               |

Filter groups are combined with **AND**. Within a group, conditions use **AND** or **OR** depending on group logic.

| Tool                  | Use                                                       |
| --------------------- | --------------------------------------------------------- |
| `add_filter`          | One AND condition (e.g. state = OH, total > 500)          |
| `add_or_filter_group` | Same-field OR in one call (e.g. Texas or Ohio)            |
| `add_mixed_or_group`  | Cross-field OR in one call (e.g. buyer Chris or state TX) |

Supported operators by field (defined in `agent/schema.py`):

| Field   | Operators                            |
| ------- | ------------------------------------ |
| orderId | equals, not_equals                   |
| buyer   | equals, not_equals, contains         |
| city    | equals, not_equals, contains         |
| state   | equals, not_equals                   |
| total   | equals, not_equals, gt, gte, lt, lte |
| items   | equals, not_equals, contains         |

## Project layout

```
agent/
  graph.py              # Graph wiring and conditional routing
  schema.py             # Order model, Operator enum, field schema (single source of truth)
  state.py              # AgentState, FilterGroup, QueryPlan, parsed_orders reducer
  llm.py                # OpenRouter client (openai/gpt-oss-120b:exacto)
  services/
    filter_engine.py    # Deterministic filter execution
    field_normalize.py  # Schema mapping, state normalization, drift logging
    parse_grounding.py  # Reject extracted values not present in source text
  nodes/
    fetch.py            # Customer API fetch
    parse.py            # parse_record node (one Send task per record)
    merge_parse.py      # Reduce step after Send fan-out
    plan.py             # Filter planning (internal tool loop)
    review_plan.py
    validate_plan.py
    execute.py
    respond.py
  tools/
    fetch_orders.py
    create_filter.py    # Filter tool schemas + execution helpers
config.py               # Settings — env-backed defaults, editable directly
main.py
```

## Future Improvements

- **Chat / session state** — add LangGraph checkpointer so follow-up messages can reuse cached `parsed_orders` without re-fetching
- **Semantic field/item search** — RAG tool so queries like "lighting" match orders with "lamp"
- **Input guardrails** — reject prompt injection and off-topic requests before the graph runs
- **Richer query options** — nested conditions, sorting, aggregates, order comparison
- **Eval harness** — unit tests per node so model/workflow changes do not regress behavior
