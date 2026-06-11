"""Filter planning tools for the fixed order schema."""

import logging
from collections.abc import Callable
from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel

from agent.schema import (
    CANONICAL_FIELDS,
    CanonicalField,
    Operator,
    is_allowed_field,
    normalize_state,
    operators_for,
)
from agent.state import Filter, FilterGroup, FilterNode

logger = logging.getLogger(__name__)


class FilterInput(BaseModel):
    field: CanonicalField
    operator: Operator
    value: str | float | int | bool


class FilterGroupInput(BaseModel):
    operator: Literal["and", "or"]
    filters: list["FilterNodeInput"]


FilterNodeInput = FilterInput | FilterGroupInput
FilterGroupInput.model_rebuild()


def _validate_field(field: str, operator: Operator) -> str | None:
    if not is_allowed_field(field):
        return f"Unknown field '{field}'. Use only: {', '.join(CANONICAL_FIELDS)}."

    allowed = operators_for(field)
    if operator not in allowed:
        allowed_str = ", ".join(op.value for op in sorted(allowed))
        return (
            f"Operator '{operator.value}' is not allowed for field '{field}'; "
            f"allowed: {allowed_str}"
        )
    return None


def _validate_node(node: FilterNode) -> str | None:
    if isinstance(node, Filter):
        return _validate_field(node.field, node.operator)
    for child in node.filters:
        if error := _validate_node(child):
            return error
    return None


def _coerce_operator(operator: Operator | str) -> Operator:
    return operator if isinstance(operator, Operator) else Operator(operator)


def _leaf(
    field: str, operator: Operator | str, value: str | float | int | bool
) -> Filter:
    op = _coerce_operator(operator)
    if field == "state" and isinstance(value, str):
        value = normalize_state(value) or value.strip().upper()
    return Filter(field=field, operator=op, value=value)


def _normalize_input(
    item: FilterNodeInput | FilterNode | dict,
) -> FilterNodeInput | FilterNode:
    if isinstance(item, (Filter, FilterGroup, FilterInput, FilterGroupInput, dict)):
        return item
    return FilterInput(**item)


def _parse_node(item: FilterNodeInput | FilterNode) -> FilterNode:
    if isinstance(item, (Filter, FilterGroup)):
        return item
    if isinstance(item, dict):
        if "filters" in item:
            return FilterGroup(
                operator=item["operator"],
                filters=[_parse_node(child) for child in item["filters"]],
            )
        return _leaf(item["field"], item["operator"], item["value"])
    if isinstance(item, FilterGroupInput):
        return FilterGroup(
            operator=item.operator,
            filters=[_parse_node(child) for child in item.filters],
        )
    return _leaf(item.field, item.operator, item.value)


def _exec_add_filter(args: dict) -> FilterNode | str:
    op = _coerce_operator(args["operator"])
    field = args["field"]
    if error := _validate_field(field, op):
        return error
    filt = _leaf(field, op, args["value"])
    logger.info("Filter: %s %s %s", filt.field, filt.operator.value, filt.value)
    return filt


def _exec_combine_filters(args: dict) -> FilterNode | str:
    raw = args["filters"]
    if len(raw) < 2:
        return "combine_filters requires at least 2 filters"

    group = FilterGroup(
        operator=args["operator"],
        filters=[_parse_node(_normalize_input(item)) for item in raw],
    )
    if error := _validate_node(group):
        return error
    logger.info(
        "Filter: %s group with %d child filter(s)",
        group.operator,
        len(group.filters),
    )
    return group


_TOOL_HANDLERS: dict[str, Callable[[dict], FilterNode | str]] = {
    "add_filter": _exec_add_filter,
    "combine_filters": _exec_combine_filters,
}


def execute_plan_tool(name: str, args: dict) -> FilterNode | str:
    handler = _TOOL_HANDLERS.get(name)
    if handler is None:
        return f"Unknown tool: {name}"
    return handler(args)


@tool
def add_filter(
    field: CanonicalField,
    operator: Operator,
    value: str | float | int | bool,
) -> str:
    """Add one filter condition (field, comparison operator, value)."""
    return "pending"


@tool
def combine_filters(
    operator: Literal["and", "or"],
    filters: list[FilterNodeInput],
) -> str:
    """Combine filters with and/or. Each entry is a filter or a nested filter group."""
    return "pending"


PLAN_TOOLS = [add_filter, combine_filters]
