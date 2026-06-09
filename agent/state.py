from typing import Any, TypedDict

from agent.schema import QueryPlan, Record


class AgentState(TypedDict, total=False):
    query: str
    limit: int | None
    raw_orders: list[str]
    records: list[Record]
    field_samples: str
    plan: QueryPlan
    matched: list[Record]
    result: dict[str, list[dict[str, Any]]]
