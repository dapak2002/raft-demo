import logging
import re
from typing import Any

from agent.state import AgentState, Filter, Operator, Order, QueryPlan

logger = logging.getLogger(__name__)


def _coerce_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = re.sub(r"[$,\s]", "", value.strip())
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _get_field(order: Order, field: str) -> Any:
    return order.model_dump().get(field)


def _equals(actual: Any, expected: Any) -> bool:
    actual_num = _coerce_number(actual)
    expected_num = _coerce_number(expected)
    if actual_num is not None and expected_num is not None:
        return actual_num == expected_num
    return str(actual).strip().lower() == str(expected).strip().lower()


def _contains(actual: Any, expected: Any) -> bool:
    return str(expected).strip().lower() in str(actual).strip().lower()


def _compare_numeric(actual: Any, expected: Any, operator: Operator) -> bool:
    actual_num = _coerce_number(actual)
    expected_num = _coerce_number(expected)
    if actual_num is None or expected_num is None:
        return False
    if operator == "over":
        return actual_num > expected_num
    if operator == "under":
        return actual_num < expected_num
    if operator == "at_least":
        return actual_num >= expected_num
    return actual_num <= expected_num


def _matches_value(actual: Any, operator: Operator, expected: str | float | int | bool) -> bool:
    if operator in {"over", "under", "at_least", "at_most"}:
        return _compare_numeric(actual, expected, operator)
    if operator == "contains":
        return _contains(actual, expected)
    if operator == "not":
        return not _equals(actual, expected)
    return _equals(actual, expected)


def _matches_filter(order: Order, filt: Filter) -> bool:
    actual = _get_field(order, filt.field)
    if actual is None:
        return False

    return _matches_value(actual, filt.operator, filt.value)


def _apply_query(orders: list[Order], data_query: QueryPlan) -> list[Order]:
    if not data_query.filters:
        return sorted(orders, key=lambda o: o.orderID)

    matched = [
        order
        for order in orders
        if all(_matches_filter(order, filt) for filt in data_query.filters)
    ]
    return sorted(matched, key=lambda o: o.orderID)


def execute_data_query_node(state: AgentState) -> AgentState:
    orders = state.get("orders") or []
    data_query = state.get("data_query") or QueryPlan()

    if not data_query.filters:
        logger.info("No filters — returning all %d orders", len(orders))
    else:
        logger.info("Applying %d filters to %d orders", len(data_query.filters), len(orders))

    matched = _apply_query(orders, data_query)
    logger.info("Matched %d/%d orders", len(matched), len(orders))

    return {"orders": matched}
