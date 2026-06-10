import logging
from typing import Any

from langgraph.graph import END, START, StateGraph

from agent.nodes.execute import execute_node
from agent.nodes.fetch import fetch_node
from agent.nodes.parse import parse_node
from agent.nodes.plan_query import plan_query_node
from agent.nodes.plan_tools import plan_tools_node
from agent.nodes.respond import respond_node
from agent.nodes.review_plan import review_plan_node
from agent.nodes.validate_parse import validate_parse_node
from agent.nodes.validate_plan import validate_plan_node
from agent.state import AgentState, QueryPlan

logger = logging.getLogger(__name__)

def route_after_fetch(state: AgentState) -> str:
    if state.get("status") == "error":
        return "respond"
    return "parse"


def route_after_validate_parse(state: AgentState) -> str:
    if state.get("status") == "error":
        return "respond"
    return "plan_query"


def route_after_plan_query(state: AgentState) -> str:
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "plan_tools"

    if not state.get("plan_reviewed"):
        return "review_plan"

    return "validate_plan"


def route_after_review_plan(state: AgentState) -> str:
    if state.get("plan_reviewed"):
        return "validate_plan"

    if state.get("plan_attempts", 0) >= 3:
        logger.warning("Plan still incomplete after max attempts; proceeding")
        return "validate_plan"

    return "plan_query"


def route_after_validate_plan(state: AgentState) -> str:
    if state.get("status") == "error":
        return "error"
    return "execute"


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("fetch", fetch_node)
    graph.add_node("parse", parse_node)
    graph.add_node("validate_parse", validate_parse_node)
    graph.add_node("plan_query", plan_query_node)
    graph.add_node("plan_tools", plan_tools_node)
    graph.add_node("review_plan", review_plan_node)
    graph.add_node("validate_plan", validate_plan_node)
    graph.add_node("execute", execute_node)
    graph.add_node("respond", respond_node)

    graph.add_edge(START, "fetch")
    graph.add_conditional_edges(
        "fetch",
        route_after_fetch,
        {
            "respond": "respond",
            "parse": "parse",
        },
    )
    graph.add_edge("parse", "validate_parse")
    graph.add_conditional_edges(
        "validate_parse",
        route_after_validate_parse,
        {
            "respond": "respond",
            "plan_query": "plan_query",
        },
    )
    graph.add_conditional_edges(
        "plan_query",
        route_after_plan_query,
        {
            "plan_tools": "plan_tools",
            "review_plan": "review_plan",
            "validate_plan": "validate_plan",
        },
    )
    graph.add_edge("plan_tools", "plan_query")
    graph.add_conditional_edges(
        "review_plan",
        route_after_review_plan,
        {
            "plan_query": "plan_query",
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


def _serialize_query_plan(plan: QueryPlan | None) -> dict[str, Any]:
    if plan is None:
        return {"groups": []}
    return plan.model_dump(mode="json")


def run(user_query: str) -> dict[str, Any]:
    final = _graph.invoke(
        {
            "user_query": user_query,
            "parsed_orders": [],
        }
    )

    data_query = final.get("data_query")
    status = final["status"]
    matched_orders = final.get("matched_orders") or []

    return {
        "status": status,
        "error": final.get("error"),
        "user_query": user_query,
        "data_query": _serialize_query_plan(data_query),
        "orders": [order.model_dump(mode="json", by_alias=True) for order in matched_orders],
    }
