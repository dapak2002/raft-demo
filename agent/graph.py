from typing import Any

from langgraph.graph import END, START, StateGraph

from agent.nodes import (
    discover_node,
    execute_node,
    fetch_node,
    generate_query_node,
    parse_node,
    validate_node,
)
from agent.state import AgentState

_graph = None


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("fetch", fetch_node)
    graph.add_node("parse", parse_node)
    graph.add_node("discover", discover_node)
    graph.add_node("generate_query", generate_query_node)
    graph.add_node("execute", execute_node)
    graph.add_node("validate", validate_node)

    graph.add_edge(START, "fetch")
    graph.add_edge("fetch", "parse")
    graph.add_edge("parse", "discover")
    graph.add_edge("discover", "generate_query")
    graph.add_edge("generate_query", "execute")
    graph.add_edge("execute", "validate")
    graph.add_edge("validate", END)

    return graph.compile()


def run(query: str, limit: int | None = None) -> dict[str, list[dict[str, Any]]]:
    global _graph
    if _graph is None:
        _graph = build_graph()

    final = _graph.invoke({"query": query, "limit": limit})
    return final["result"]
