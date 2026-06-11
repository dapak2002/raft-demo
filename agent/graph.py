import logging
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

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
from config import MAX_PLAN_ATTEMPTS, PARSE_MAX_WORKERS

logger = logging.getLogger(__name__)


def route_after_fetch(state: AgentState) -> str | list[Send]:
    """Fan out one parse task per raw record (map step of map-reduce)."""
    if state.get("status") == "error":
        return "respond"
    return [
        Send("parse_record", {"text": text})
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
        logger.warning("Plan still incomplete after %d attempts; proceeding", MAX_PLAN_ATTEMPTS)
        return "validate_plan"

    return "plan"


def route_after_validate_plan(state: AgentState) -> str:
    if state.get("status") == "error":
        return "error"
    return "execute"


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("fetch", fetch_node)
    graph.add_node("parse_record", parse_record_node)
    graph.add_node("merge_parse", merge_parse_node)
    graph.add_node("plan", plan_node)
    graph.add_node("review_plan", review_plan_node)
    graph.add_node("validate_plan", validate_plan_node)
    graph.add_node("execute", execute_node)
    graph.add_node("respond", respond_node)

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
    final = _graph.invoke(
        {"user_query": user_query},
        config={"max_concurrency": PARSE_MAX_WORKERS},
    )

    status = final["status"]
    matched_orders = final.get("matched_orders") or []
    data_query = final.get("plan") or QueryPlan()

    return {
        "status": status,
        "error": final.get("error"),
        "user_query": user_query,
        "data_query": data_query.model_dump(mode="json"),
        "orders": [
            order.to_json() if isinstance(order, Order) else order
            for order in matched_orders
        ],
    }
