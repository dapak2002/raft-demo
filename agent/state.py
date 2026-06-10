from typing import Annotated, Any, Literal, NotRequired, TypedDict

from langgraph.graph.message import add_messages
from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent.operators import Operator

OrderField = Literal["orderID", "buyer", "state", "total"]
AgentStatus = Literal["ok", "error"]


def normalize_buyer(name: str) -> str:
    return " ".join(part.capitalize() for part in name.strip().split())


class Order(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    orderID: str = Field(serialization_alias="orderId")
    buyer: str
    state: str
    total: float

    @field_validator("buyer")
    @classmethod
    def normalize_buyer_field(cls, value: str) -> str:
        return normalize_buyer(value)


class Filter(BaseModel):
    field: OrderField = Field(description="The order field to filter on")
    operator: Operator = Field(description="The comparison operator")
    value: str | float | int | bool = Field(description="The value to compare against")


class FilterGroup(BaseModel):
    logic: Literal["and", "or"]
    filters: list[Filter] = Field(default_factory=list)


class QueryPlan(BaseModel):
    groups: list[FilterGroup] = Field(default_factory=list)


class AgentState(TypedDict):
    user_query: str
    raw_orders: NotRequired[list[str]]
    parsed_orders: NotRequired[list[Order]]
    matched_orders: NotRequired[list[Order]]
    data_query: NotRequired[QueryPlan]
    messages: Annotated[list[Any], add_messages]
    error: NotRequired[str | None]
    status: NotRequired[AgentStatus]
    plan_attempts: NotRequired[int]
    plan_reviewed: NotRequired[bool]
    match_all: NotRequired[bool]
    plan_feedback: NotRequired[str | None]
