import logging

from agent.operators import FIELD_OPERATORS, Operator
from agent.state import AgentState, Filter, Order, QueryPlan, normalize_buyer

logger = logging.getLogger(__name__)


def _apply_string(actual: str, expected: str, operator: Operator) -> bool:
    if operator == Operator.EQUALS:
        return actual == expected
    if operator == Operator.NOT_EQUALS:
        return actual != expected
    if operator == Operator.CONTAINS:
        return expected in actual
    return False


def _apply_numeric(actual: float, expected: float, operator: Operator) -> bool:
    if operator == Operator.EQUALS:
        return actual == expected
    if operator == Operator.NOT_EQUALS:
        return actual != expected
    if operator == Operator.GT:
        return actual > expected
    if operator == Operator.GTE:
        return actual >= expected
    if operator == Operator.LT:
        return actual < expected
    if operator == Operator.LTE:
        return actual <= expected
    return False


def _apply_filter(order: Order, filt: Filter) -> bool:
    allowed = FIELD_OPERATORS.get(filt.field, frozenset())
    if filt.operator not in allowed:
        return False

    if filt.field == "total":
        return _apply_numeric(order.total, float(filt.value), filt.operator)

    if filt.field == "buyer":
        actual = normalize_buyer(order.buyer)
        expected = normalize_buyer(str(filt.value))
        return _apply_string(actual, expected, filt.operator)

    actual = str(getattr(order, filt.field))
    return _apply_string(actual, str(filt.value), filt.operator)


def execute_data_query_node(state: AgentState) -> AgentState:
    orders = state.get("orders") or []
    data_query = state.get("data_query") or QueryPlan()
    filters = data_query.filters

    logger.info("Applying %d filters to %d orders", len(filters), len(orders))

    if not filters:
        matched = sorted(orders, key=lambda o: o.orderID)
    else:
        matched = sorted(
            [order for order in orders if all(_apply_filter(order, filt) for filt in filters)],
            key=lambda o: o.orderID,
        )

    logger.info("Matched %d/%d orders", len(matched), len(orders))
    return {"orders": matched}
