from typing import Any

from agent.schema import Operator, Order, operators_for
from agent.state import Filter, FilterGroup, QueryPlan


def _apply_string(actual: str, expected: str, operator: Operator) -> bool:
    actual_lower = actual.lower()
    expected_lower = expected.lower()

    if operator == Operator.EQUALS:
        return actual_lower == expected_lower
    if operator == Operator.NOT_EQUALS:
        return actual_lower != expected_lower
    if operator == Operator.CONTAINS:
        return expected_lower in actual_lower
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


def _apply_list(actual: list[Any], expected: str, operator: Operator) -> bool:
    items = [str(item).lower() for item in actual]
    needle = expected.lower()

    if operator == Operator.CONTAINS:
        return any(needle in item for item in items)
    if operator == Operator.EQUALS:
        return needle in items
    if operator == Operator.NOT_EQUALS:
        return needle not in items
    return False


def apply_filter(order: Order, filt: Filter) -> bool:
    actual = getattr(order, filt.field, None)
    if actual is None:
        return False

    if filt.operator not in operators_for(filt.field):
        return False

    if isinstance(actual, list):
        return _apply_list(actual, str(filt.value), filt.operator)

    if isinstance(actual, bool):
        return _apply_string(str(actual), str(filt.value), filt.operator)

    if isinstance(actual, (int, float)):
        return _apply_numeric(float(actual), float(filt.value), filt.operator)

    return _apply_string(str(actual), str(filt.value), filt.operator)


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
    return sorted(matched, key=Order.sort_key)


def plan_has_filters(plan: QueryPlan) -> bool:
    return bool(active_groups(plan))


def plan_from_groups(groups: list[FilterGroup]) -> QueryPlan:
    """Build a plan from accumulated tool-call groups, deduplicating repeats."""
    seen: set[str] = set()
    unique: list[FilterGroup] = []
    for group in groups:
        if not group.filters:
            continue
        key = group.model_dump_json()
        if key in seen:
            continue
        seen.add(key)
        unique.append(group)
    return QueryPlan(groups=unique)
