import asyncio
import logging
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from agent.fault_tolerance import (
    build_retry_policy,
    build_timeout_policy,
    node_error_handler,
)
from agent.llm_limits import prepare_user_query
from agent.nodes.execute import execute_node
from agent.nodes.fetch import fetch_node
from agent.nodes.merge_parse import merge_parse_node
from agent.nodes.parse_record import parse_record_node
from agent.nodes.plan import plan_node
from agent.nodes.respond import respond_node
from agent.nodes.review_plan import review_plan_node
from agent.nodes.validate_plan import validate_plan_node
from agent.schema import Order
from agent.state import AgentState, QueryPlan
from config import (
    FETCH_NODE_TIMEOUT_SECONDS,
    LLM_NODE_TIMEOUT_SECONDS,
    MAX_PLAN_ATTEMPTS,
    NODE_MAX_RETRIES,
    PARSE_MAX_WORKERS,
)

logger = logging.getLogger(__name__)

_TRANSIENT_RETRY = build_retry_policy(max_attempts=NODE_MAX_RETRIES)
_FETCH_TIMEOUT = build_timeout_policy(FETCH_NODE_TIMEOUT_SECONDS)
_LLM_TIMEOUT = build_timeout_policy(LLM_NODE_TIMEOUT_SECONDS)


def route_after_fetch(state: AgentState) -> str | list[Send]:
    """Fan out one parse task per raw record (map step of map-reduce)."""
    if state.get("status") == "error":
        return "respond"
    return [
        Send(
            "parse_record",
            {"text": text},
            timeout=_LLM_TIMEOUT,
        )
        for text in state.get("raw_orders") or []
    ]


def route_after_merge_parse(state: AgentState) -> str:
    if state.get("status") == "error":
        return "respond"
    return "plan"


def route_after_review_plan(state: AgentState) -> str:
    if state.get("plan_complete"):
        return "validate_plan"

    if state.get("plan_attempts", 0) >= MAX_PLAN_ATTEMPTS:
        logger.warning(
            "Plan review loop exhausted after %d attempts; proceeding to validate",
            MAX_PLAN_ATTEMPTS,
        )
        return "validate_plan"

    logger.warning(
        "Plan incomplete (review attempt %d/%d); looping back to plan",
        state.get("plan_attempts", 0),
        MAX_PLAN_ATTEMPTS,
    )
    return "plan"


def route_after_validate_plan(state: AgentState) -> str:
    if state.get("status") == "error":
        return "respond"
    return "execute"


def build_graph():
    graph = StateGraph(AgentState)

    graph.set_node_defaults(
        retry_policy=_TRANSIENT_RETRY,
        error_handler=node_error_handler,
    )

    graph.add_node(
        "fetch",
        fetch_node,
        timeout=_FETCH_TIMEOUT,
    )
    graph.add_node(
        "parse_record",
        parse_record_node,
        timeout=_LLM_TIMEOUT,
    )
    graph.add_node(
        "merge_parse",
        merge_parse_node,
        retry_policy=None,
    )
    graph.add_node(
        "plan",
        plan_node,
        timeout=_LLM_TIMEOUT,
    )
    graph.add_node(
        "review_plan",
        review_plan_node,
        timeout=_LLM_TIMEOUT,
    )
    graph.add_node(
        "validate_plan",
        validate_plan_node,
        retry_policy=None,
    )
    graph.add_node(
        "execute",
        execute_node,
        retry_policy=None,
    )
    graph.add_node(
        "respond",
        respond_node,
        retry_policy=None,
        error_handler=None,
    )

    graph.add_edge(START, "fetch")
    graph.add_conditional_edges(
        "fetch",
        route_after_fetch,
        ["respond", "parse_record"],
    )
    graph.add_edge("parse_record", "merge_parse")
    graph.add_conditional_edges(
        "merge_parse",
        route_after_merge_parse,
        ["respond", "plan"],
    )
    graph.add_edge("plan", "review_plan")
    graph.add_conditional_edges(
        "review_plan",
        route_after_review_plan,
        ["plan", "validate_plan"],
    )
    graph.add_conditional_edges(
        "validate_plan",
        route_after_validate_plan,
        ["execute", "respond"],
    )
    graph.add_edge("execute", "respond")
    graph.add_edge("respond", END)

    return graph.compile()


_graph = build_graph()

#FRONTEND STREAMING NODE ACTIVITY

# Nodes omitted from the live execution trace (internal routing / recovery).
_SKIP_TRACE_NODES = frozenset({"__default_error_handler__"})
_SKIP_TRACE_ON_ERROR = frozenset({"respond"})

# Human-readable labels for trace events (mirrors fault_tolerance._NODE_LABELS).
TRACE_NODE_LABELS: dict[str, str] = {
    "fetch": "Fetch orders",
    "parse_record": "Parse records",
    "merge_parse": "Merge parsed data",
    "plan": "Build filter plan",
    "review_plan": "Review plan",
    "validate_plan": "Validate plan",
    "execute": "Apply filters",
    "respond": "Complete",
}


def _resolve_trace_node(node: str, patch: dict[str, Any]) -> str | None:
    """Map LangGraph internal nodes to user-facing trace steps."""
    if node in _SKIP_TRACE_NODES:
        return patch.get("failed_node") or "fetch"
    if patch.get("status") == "error" and node in _SKIP_TRACE_ON_ERROR:
        return None
    return node


PIPELINE_NODES: tuple[str, ...] = (
    "fetch",
    "parse_record",
    "merge_parse",
    "plan",
    "review_plan",
    "validate_plan",
    "execute",
    "respond",
)

PIPELINE_STEP_NUMBERS: dict[str, int] = {
    node: index + 1 for index, node in enumerate(PIPELINE_NODES)
}


def _empty_result(user_query: str, error: str) -> dict[str, Any]:
    return {
        "status": "error",
        "error": error,
        "user_query": user_query,
        "data_query": QueryPlan().model_dump(mode="json"),
        "orders": [],
    }


def format_result(final: dict[str, Any], safe_query: str) -> dict[str, Any]:
    matched_orders = final.get("matched_orders") or []
    data_query = final.get("plan") or QueryPlan()
    return {
        "status": final.get("status", "ok"),
        "error": final.get("error"),
        "user_query": safe_query,
        "data_query": data_query.model_dump(mode="json"),
        "orders": [
            order.to_json() if isinstance(order, Order) else order
            for order in matched_orders
        ],
    }


def _patch_list_len(value: Any) -> int | None:
    """Length of a list patch, including reducer replace tuples."""
    if value is None:
        return None
    if isinstance(value, tuple) and len(value) == 2 and value[0] == "replace":
        items = value[1]
        return len(items) if items is not None else 0
    if isinstance(value, list):
        return len(value)
    return None


def _node_start_event(node: str, visit: int) -> dict[str, Any]:
    event: dict[str, Any] = {
        "event": "node_start",
        "node": node,
        "visit": visit,
        "label": TRACE_NODE_LABELS.get(node, node.replace("_", " ")),
    }
    if step := PIPELINE_STEP_NUMBERS.get(node):
        event["step"] = step
    return event


def _node_event(node: str, patch: dict[str, Any]) -> dict[str, Any]:
    event: dict[str, Any] = {"event": "node", "node": node}
    if step := PIPELINE_STEP_NUMBERS.get(node):
        event["step"] = step
    if patch.get("status") == "error":
        event["status"] = "error"
    if patch.get("error"):
        event["error"] = patch["error"]
    if "raw_orders" in patch:
        event["raw_count"] = len(patch["raw_orders"] or [])
    if "parsed_orders" in patch:
        parsed_count = _patch_list_len(patch["parsed_orders"])
        if parsed_count is not None:
            event["parsed_count"] = parsed_count
    if "matched_orders" in patch:
        event["order_count"] = len(patch["matched_orders"] or [])
    if patch.get("plan_feedback"):
        event["plan_feedback"] = patch["plan_feedback"]
    if patch.get("plan_attempts") is not None:
        event["plan_attempts"] = patch["plan_attempts"]
    return event


async def stream_run(user_query: str):
    """Yield SSE-friendly events: node updates and a final done payload."""
    safe_query = prepare_user_query(user_query)
    if not safe_query:
        yield {"event": "error", "message": "No query provided."}
        yield {
            "event": "done",
            "result": _empty_result(user_query, "No query provided."),
        }
        return

    final: dict[str, Any] | None = None
    visit_counts: dict[str, int] = {}
    async for mode, chunk in _graph.astream(
        {"user_query": safe_query},
        stream_mode=["tasks", "updates", "values"],
        config={"max_concurrency": PARSE_MAX_WORKERS},
    ):
        if mode == "tasks":
            if "result" in chunk:
                continue
            trace_node = chunk.get("name")
            if not trace_node or trace_node in _SKIP_TRACE_NODES:
                continue
            if trace_node == "parse_record":
                visit = 1
            else:
                visit_counts[trace_node] = visit_counts.get(trace_node, 0) + 1
                visit = visit_counts[trace_node]
            yield _node_start_event(trace_node, visit)
        elif mode == "updates":
            for node, patch in chunk.items():
                patch = patch if isinstance(patch, dict) else {}
                trace_node = _resolve_trace_node(node, patch)
                if trace_node is None:
                    continue
                event = _node_event(trace_node, patch)
                if trace_node == "parse_record":
                    event["visit"] = 1
                else:
                    event["visit"] = visit_counts.get(trace_node, 1)
                event["label"] = TRACE_NODE_LABELS.get(
                    trace_node, trace_node.replace("_", " ")
                )
                yield event
        else:
            final = chunk

    if final is None:
        yield {
            "event": "error",
            "message": "Agent finished without a final state.",
        }
        yield {
            "event": "done",
            "result": _empty_result(
                safe_query, "Agent finished without a final state."
            ),
        }
        return

    yield {"event": "done", "result": format_result(final, safe_query)}


def iter_stream_events(user_query: str):
    """Bridge async stream_run to a sync iterator (for Flask SSE)."""

    async def _consume():
        async for event in stream_run(user_query):
            yield event

    loop = asyncio.new_event_loop()
    agen = _consume().__aiter__()
    try:
        while True:
            try:
                yield loop.run_until_complete(agen.__anext__())
            except StopAsyncIteration:
                break
    finally:
        loop.close()


def run(user_query: str) -> dict[str, Any]:
    safe_query = prepare_user_query(user_query)
    if not safe_query:
        return _empty_result(user_query, "No query provided.")

    final = asyncio.run(
        _graph.ainvoke(
            {"user_query": safe_query},
            config={"max_concurrency": PARSE_MAX_WORKERS},
        )
    )
    return format_result(final, safe_query)
