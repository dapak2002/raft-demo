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
        return "error"
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
        {
            "respond": "respond",
            "plan": "plan",
        },
    )
    graph.add_edge("plan", "review_plan")
    graph.add_conditional_edges(
        "review_plan",
        route_after_review_plan,
        {
            "plan": "plan",
            "validate_plan": "validate_plan",
        },
    )
    graph.add_conditional_edges(
        "validate_plan",
        route_after_validate_plan,
        {
            "execute": "execute",
            "error": "respond",
        },
    )
    graph.add_edge("execute", "respond")
    graph.add_edge("respond", END)

    return graph.compile()


_graph = build_graph()


def run(user_query: str) -> dict[str, Any]:
    safe_query = prepare_user_query(user_query)
    if not safe_query:
        return {
            "status": "error",
            "error": "No query provided.",
            "user_query": user_query,
            "data_query": QueryPlan().model_dump(mode="json"),
            "orders": [],
        }

    final = asyncio.run(
        _graph.ainvoke(
            {"user_query": safe_query},
            config={"max_concurrency": PARSE_MAX_WORKERS},
        )
    )

    status = final["status"]
    matched_orders = final.get("matched_orders") or []
    data_query = final.get("plan") or QueryPlan()

    return {
        "status": status,
        "error": final.get("error"),
        "user_query": safe_query,
        "data_query": data_query.model_dump(mode="json"),
        "orders": [
            order.to_json() if isinstance(order, Order) else order
            for order in matched_orders
        ],
    }
