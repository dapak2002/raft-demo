import operator
from typing import Annotated, Any, Literal, NotRequired, TypedDict

from pydantic import BaseModel, Field

from agent.schema import Operator, Order

AgentStatus = Literal["ok", "error"]
ParsedOrdersUpdate = list[Order] | tuple[Literal["replace"], list[Order]]


def parsed_orders_reducer(
    left: list[Order] | None,
    right: ParsedOrdersUpdate,
) -> list[Order]:
    """Append single-record batches from Send(); replace with deduped list from merge_parse."""
    if isinstance(right, tuple) and right[0] == "replace":
        return right[1]
    return (left or []) + right


class Filter(BaseModel):
    field: str = Field(description="The record field to filter on")
    operator: Operator = Field(description="The comparison operator")
    value: str | float | int | bool = Field(description="The value to compare against")


class FilterGroup(BaseModel):
    logic: Literal["and", "or"]
    filters: list[Filter] = Field(default_factory=list)


class QueryPlan(BaseModel):
    groups: list[FilterGroup] = Field(default_factory=list)


class AgentState(TypedDict):
    # ingest
    raw_orders: NotRequired[list[str]]
    parsed_orders: Annotated[list[Order], parsed_orders_reducer]

    # query
    user_query: str
    plan: NotRequired[QueryPlan | None]
    plan_attempts: NotRequired[int]
    plan_feedback: NotRequired[str | None]
    plan_complete: NotRequired[bool]
    match_all: NotRequired[bool]

    # output
    matched_orders: NotRequired[list[Order]]
    status: NotRequired[AgentStatus]
    error: NotRequired[str | None]


class ParseRecordState(TypedDict):
    """Input payload for one Send(parse_record) task."""

    text: str
