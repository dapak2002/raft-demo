from typing import Literal, NotRequired, TypedDict

from pydantic import BaseModel, Field, field_validator

from agent.operators import Operator

OrderField = Literal["orderID", "buyer", "state", "total"]


def normalize_buyer(name: str) -> str:
    return " ".join(part.capitalize() for part in name.strip().split())


class Order(BaseModel):
    orderID: str
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


class QueryPlan(BaseModel):
    filters: list[Filter] = Field(default_factory=list)


class AgentState(TypedDict):
    user_query: str
    raw_orders: NotRequired[list[str]]
    orders: NotRequired[list[Order]]
    data_query: NotRequired[QueryPlan]
