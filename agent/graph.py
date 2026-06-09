from typing import Any

from langgraph.graph import END, START, StateGraph

from agent.nodes.execute_data_query import execute_data_query_node
from agent.nodes.fetch import fetch_node
from agent.nodes.generate_data_query import generate_data_query_node
from agent.nodes.parse import parse_node
from agent.nodes.respond import respond_node
from agent.state import AgentState

_graph = None


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("fetch", fetch_node)
    graph.add_node("parse", parse_node)
    graph.add_node("generate_data_query", generate_data_query_node)
    graph.add_node("execute_data_query", execute_data_query_node)
    graph.add_node("respond", respond_node)

    graph.add_edge(START, "fetch")
    graph.add_edge("fetch", "parse")
    graph.add_edge("parse", "generate_data_query")
    graph.add_edge("generate_data_query", "execute_data_query")
    graph.add_edge("execute_data_query", "respond")
    graph.add_edge("respond", END)

    return graph.compile()


def run(user_query: str) -> dict[str, Any]:
    global _graph
    if _graph is None:
        _graph = build_graph()

    final = _graph.invoke({"user_query": user_query})

    data_query = final.get("data_query")
    return {
        "user_query": final["user_query"],
        "data_query": data_query.model_dump() if data_query else {"filters": []},
        "orders": final.get("orders", []),
    }
