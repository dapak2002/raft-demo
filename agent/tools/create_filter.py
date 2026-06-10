"""Filter planning tools for the fixed order schema."""

import logging

from langchain_core.tools import tool
from pydantic import BaseModel

from agent.schema import (
    CANONICAL_FIELDS,
    CanonicalField,
    Operator,
    is_allowed_field,
    operators_for,
)
from agent.services.field_normalize import normalize_state
from agent.state import Filter, FilterGroup

logger = logging.getLogger(__name__)


class MixedOrFilter(BaseModel):
    field: CanonicalField
    operator: Operator
    value: str | float | int | bool


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


def _coerce_operator(operator: Operator | str) -> Operator:
    return operator if isinstance(operator, Operator) else Operator(operator)


def _make_filter(field: str, operator: Operator, value: str | float | int | bool) -> Filter:
    if field == "state" and isinstance(value, str):
        if code := normalize_state(value):
            value = code
    return Filter(field=field, operator=operator, value=value)


def run_add_filter(
    field: str,
    operator: Operator | str,
    value: str | float | int | bool,
) -> FilterGroup | str:
    op = _coerce_operator(operator)
    if error := _validate_field(field, op):
        return error

    filt = _make_filter(field, op, value)
    logger.info("Filter: %s %s %s", filt.field, filt.operator.value, filt.value)
    return FilterGroup(logic="and", filters=[filt])


def run_add_or_filter_group(
    field: str,
    operator: Operator | str,
    values: list[str | float | int | bool],
) -> FilterGroup | str:
    op = _coerce_operator(operator)
    if error := _validate_field(field, op):
        return error

    group = FilterGroup(
        logic="or",
        filters=[_make_filter(field, op, value) for value in values],
    )
    logger.info("Filter: OR group with %d filters on %s", len(group.filters), field)
    return group


def run_add_mixed_or_group(filters: list[MixedOrFilter]) -> FilterGroup | str:
    if len(filters) < 2:
        return "add_mixed_or_group requires at least 2 filters"

    for item in filters:
        if error := _validate_field(item.field, item.operator):
            return error

    group = FilterGroup(
        logic="or",
        filters=[_make_filter(item.field, item.operator, item.value) for item in filters],
    )
    logger.info("Filter: mixed OR group with %d filters", len(group.filters))
    return group


def execute_plan_tool(name: str, args: dict) -> FilterGroup | str:
    if name == "add_filter":
        return run_add_filter(**args)
    if name == "add_or_filter_group":
        return run_add_or_filter_group(**args)
    if name == "add_mixed_or_group":
        raw = args["filters"]
        filters = [
            item if isinstance(item, MixedOrFilter) else MixedOrFilter(**item)
            for item in raw
        ]
        return run_add_mixed_or_group(filters)
    return f"Unknown tool: {name}"


@tool
def add_filter(
    field: CanonicalField,
    operator: Operator,
    value: str | float | int | bool,
) -> str:
    """Add one AND filter condition. Call once per condition."""
    return "pending"


@tool
def add_or_filter_group(
    field: CanonicalField,
    operator: Operator,
    values: list[str | float | int | bool],
) -> str:
    """Add one OR group where the field matches any value (e.g. TX or OH)."""
    return "pending"


@tool
def add_mixed_or_group(filters: list[MixedOrFilter]) -> str:
    """Add an OR group across one or more fields (e.g. buyer Chris OR state TX)."""
    return "pending"


PLAN_TOOLS = [add_filter, add_or_filter_group, add_mixed_or_group]
