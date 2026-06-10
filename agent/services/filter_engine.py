from agent.operators import FIELD_OPERATORS, Operator
from agent.state import Filter, FilterGroup, Order, QueryPlan, normalize_buyer

_STATE_ALIASES = {
    "texas": "TX",
    "ohio": "OH",
    "washington": "WA",
}


def _normalize_state(value: str) -> str:
    key = value.strip().lower()
    if key in _STATE_ALIASES:
        return _STATE_ALIASES[key]
    if len(value.strip()) == 2:
        return value.strip().upper()
    return value.strip()


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


def apply_filter(order: Order, filt: Filter) -> bool:
    allowed = FIELD_OPERATORS.get(filt.field, frozenset())
    if filt.operator not in allowed:
        return False

    if filt.field == "total":
        return _apply_numeric(order.total, float(filt.value), filt.operator)

    if filt.field == "buyer":
        actual = normalize_buyer(order.buyer)
        expected = normalize_buyer(str(filt.value))
        return _apply_string(actual, expected, filt.operator)

    if filt.field == "state":
        actual = _normalize_state(str(getattr(order, filt.field)))
        expected = _normalize_state(str(filt.value))
        return _apply_string(actual, expected, filt.operator)

    actual = str(getattr(order, filt.field))
    return _apply_string(actual, str(filt.value), filt.operator)


def group_matches(order: Order, group: FilterGroup) -> bool:
    if not group.filters:
        return False

    results = [apply_filter(order, filt) for filt in group.filters]
    if group.logic == "or":
        return any(results)
    return all(results)


def active_groups(plan: QueryPlan) -> list[FilterGroup]:
    return [group for group in plan.groups if group.filters]


def plan_matches(order: Order, plan: QueryPlan) -> bool:
    groups = active_groups(plan)
    if not groups:
        return False
    return all(group_matches(order, group) for group in groups)


def execute_plan(orders: list[Order], plan: QueryPlan) -> list[Order]:
    matched = [order for order in orders if plan_matches(order, plan)]
    return sorted(matched, key=lambda order: order.orderID)


def plan_has_filters(plan: QueryPlan) -> bool:
    return bool(active_groups(plan))
