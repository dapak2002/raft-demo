from typing import Literal

from langchain_core.tools import tool

from agent.operators import FIELD_OPERATORS, Operator
from agent.state import Filter


def build_create_filter_tool(filters: list[Filter]):
    @tool
    def create_filter(
        field: Literal["orderID", "buyer", "state", "total"],
        operator: Literal[
            "equals", "not_equals", "contains", "gt", "gte", "lt", "lte"
        ],
        value: str | float | int,
    ) -> str:
        """Add one filter condition on order data. Call once per condition in the user's request."""
        op = Operator(operator)
        if op not in FIELD_OPERATORS.get(field, frozenset()):
            return f"Error: operator '{operator}' is not allowed for field '{field}'"

        filters.append(Filter(field=field, operator=op, value=value))
        return f"Added filter: {field} {operator} {value}"

    return create_filter
