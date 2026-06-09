from typing import Literal, NotRequired, TypedDict

from pydantic import BaseModel, Field

OrderField = Literal["orderID", "buyer", "state", "total"]
Operator = Literal["equals", "contains", "over", "under", "at_least", "at_most", "not"]


class Order(BaseModel):
    orderID: str
    buyer: str
    state: str
    total: float


class Filter(BaseModel):
    field: OrderField = Field(description="The order field to filter on")
    operator: Operator = Field(description="How to compare the field to the value")
    value: str | float | int | bool = Field(description="The value to compare against")


class QueryPlan(BaseModel):
    filters: list[Filter] = Field(default_factory=list)


class AgentState(TypedDict):
    user_query: str
    raw_orders: NotRequired[list[str]]
    orders: NotRequired[list[Order]]
    data_query: NotRequired[QueryPlan]
