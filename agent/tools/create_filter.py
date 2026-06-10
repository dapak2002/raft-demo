import json
from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from agent.operators import FIELD_OPERATORS, Operator


class MixedOrFilter(BaseModel):
    field: Literal["orderID", "buyer", "state", "total"]
    operator: Literal["equals", "not_equals", "contains", "gt", "gte", "lt", "lte"]
    value: str | float | int


class AddMixedOrGroupInput(BaseModel):
    filters: list[MixedOrFilter] = Field(
        description="Two or more filters combined with OR; supports different fields"
    )


@tool
def begin_filter_group(logic: Literal["or"]) -> str:
    """Start an OR filter group for alternatives (e.g. Texas or Ohio)."""
    return json.dumps({"action": "begin_group", "logic": logic})


@tool
def add_filter(
    field: Literal["orderID", "buyer", "state", "total"],
    operator: Literal["equals", "not_equals", "contains", "gt", "gte", "lt", "lte"],
    value: str | float | int,
) -> str:
    """Add one AND filter condition. Call once per condition."""
    op = Operator(operator)
    if op not in FIELD_OPERATORS.get(field, frozenset()):
        return json.dumps(
            {
                "action": "error",
                "message": f"operator '{operator}' is not allowed for field '{field}'",
            }
        )

    return json.dumps(
        {
            "action": "add_filter",
            "field": field,
            "operator": operator,
            "value": value,
        }
    )


@tool
def add_or_filter_group(
    field: Literal["orderID", "buyer", "state", "total"],
    operator: Literal["equals", "not_equals", "contains"],
    values: list[str | float | int],
) -> str:
    """Add one OR group where the field matches any value (e.g. Texas or Ohio)."""
    op = Operator(operator)
    if op not in FIELD_OPERATORS.get(field, frozenset()):
        return json.dumps(
            {
                "action": "error",
                "message": f"operator '{operator}' is not allowed for field '{field}'",
            }
        )

    return json.dumps(
        {
            "action": "add_or_group",
            "field": field,
            "operator": operator,
            "values": values,
        }
    )


@tool(args_schema=AddMixedOrGroupInput)
def add_mixed_or_group(filters: list[MixedOrFilter]) -> str:
    """Add an OR group across one or more fields (e.g. buyer Chris OR state TX)."""
    if len(filters) < 2:
        return json.dumps(
            {"action": "error", "message": "add_mixed_or_group requires at least 2 filters"}
        )

    serialized = []
    for filt in filters:
        op = Operator(filt.operator)
        if op not in FIELD_OPERATORS.get(filt.field, frozenset()):
            return json.dumps(
                {
                    "action": "error",
                    "message": (
                        f"operator '{filt.operator}' is not allowed for field '{filt.field}'"
                    ),
                }
            )
        serialized.append(
            {
                "field": filt.field,
                "operator": filt.operator,
                "value": filt.value,
            }
        )

    return json.dumps({"action": "add_mixed_or_group", "filters": serialized})


PLAN_TOOLS = [begin_filter_group, add_filter, add_or_filter_group, add_mixed_or_group]
