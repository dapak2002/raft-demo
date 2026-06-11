from collections.abc import Callable
from typing import Any

from agent.schema import Operator, Order, operators_for
from agent.state import Filter, FilterGroup, FilterNode, QueryPlan

_STRING_OPS: dict[Operator, Callable[[str, str], bool]] = {
    Operator.EQUALS: lambda actual, expected: actual.lower() == expected.lower(),
    Operator.NOT_EQUALS: lambda actual, expected: actual.lower() != expected.lower(),
    Operator.CONTAINS: lambda actual, expected: expected.lower() in actual.lower(),
}

_NUMERIC_OPS: dict[Operator, Callable[[float, float], bool]] = {
    Operator.EQUALS: lambda actual, expected: actual == expected,
    Operator.NOT_EQUALS: lambda actual, expected: actual != expected,
    Operator.GT: lambda actual, expected: actual > expected,
    Operator.GTE: lambda actual, expected: actual >= expected,
    Operator.LT: lambda actual, expected: actual < expected,
    Operator.LTE: lambda actual, expected: actual <= expected,
}

_LIST_OPS: dict[Operator, Callable[[list[str], str], bool]] = {
    Operator.CONTAINS: lambda items, needle: any(needle in item for item in items),
    Operator.EQUALS: lambda items, needle: needle in items,
    Operator.NOT_EQUALS: lambda items, needle: needle not in items,
}


def _apply_string(actual: str, expected: str, operator: Operator) -> bool:
    fn = _STRING_OPS.get(operator)
    return fn(actual, expected) if fn else False


def _apply_numeric(actual: float, expected: float, operator: Operator) -> bool:
    fn = _NUMERIC_OPS.get(operator)
    return fn(actual, expected) if fn else False


def _apply_list(actual: list[Any], expected: str, operator: Operator) -> bool:
    items = [str(item).lower() for item in actual]
    needle = expected.lower()
    fn = _LIST_OPS.get(operator)
    return fn(items, needle) if fn else False


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


def node_matches(order: Order, node: FilterNode) -> bool:
    if isinstance(node, FilterGroup):
        if not node.filters:
            return False
        results = [node_matches(order, child) for child in node.filters]
        if node.operator == "or":
            return any(results)
        return all(results)
    return apply_filter(order, node)


def plan_matches(order: Order, plan: QueryPlan) -> bool:
    root = plan.filter
    if root is None or not root.filters:
        return False
    return node_matches(order, root)


def execute_plan(orders: list[Order], plan: QueryPlan) -> list[Order]:
    matched = [order for order in orders if plan_matches(order, plan)]
    return sorted(matched, key=Order.sort_key)


def plan_has_filters(plan: QueryPlan) -> bool:
    return bool(plan.filter and plan.filter.filters)


def _leaf_key(filt: Filter) -> tuple[str, str, str | float | int | bool]:
    return (filt.field, filt.operator.value, filt.value)


def _collect_leaves(node: FilterNode) -> list[Filter]:
    if isinstance(node, Filter):
        return [node]
    return [leaf for child in node.filters for leaf in _collect_leaves(child)]


def _group_depth(node: FilterNode) -> int:
    if isinstance(node, Filter):
        return 0
    if not node.filters:
        return 0
    return 1 + max(_group_depth(child) for child in node.filters)


def build_query_plan(filter_parts: list[FilterNode]) -> QueryPlan:
    """Build a QueryPlan from tool-call filters, preferring nested groups over flat duplicates."""
    seen: set[str] = set()
    unique: list[FilterNode] = []
    for part in filter_parts:
        key = part.model_dump_json()
        if key in seen:
            continue
        seen.add(key)
        unique.append(part)

    if not unique:
        return QueryPlan()

    groups = [part for part in unique if isinstance(part, FilterGroup)]
    leaves = [part for part in unique if isinstance(part, Filter)]
    all_leaf_keys = {
        _leaf_key(leaf) for leaf in _collect_leaves(part) for part in unique
    }
    flat_leaf_keys = {_leaf_key(leaf) for leaf in leaves}

    if groups:
        ranked = sorted(
            groups,
            key=lambda group: (_group_depth(group), len(_collect_leaves(group))),
            reverse=True,
        )
        for candidate in ranked:
            candidate_keys = {_leaf_key(leaf) for leaf in _collect_leaves(candidate)}
            if candidate_keys == all_leaf_keys:
                return QueryPlan(filter=candidate)
            if (
                candidate.operator == "and"
                and candidate_keys >= flat_leaf_keys
                and flat_leaf_keys
            ):
                return QueryPlan(filter=candidate)

        best = ranked[0]
        best_keys = {_leaf_key(leaf) for leaf in _collect_leaves(best)}
        extra = [leaf for leaf in leaves if _leaf_key(leaf) not in best_keys]
        if extra:
            return QueryPlan(filter=FilterGroup(operator="and", filters=[best, *extra]))
        return QueryPlan(filter=best)

    if len(unique) == 1:
        root = unique[0]
        if isinstance(root, Filter):
            root = FilterGroup(operator="and", filters=[root])
        return QueryPlan(filter=root)
    return QueryPlan(filter=FilterGroup(operator="and", filters=unique))
