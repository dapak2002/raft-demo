import logging
import re
from typing import Any

from agent.schema import Filter, QueryPlan, Record
from agent.state import AgentState

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


def _operator_kind(operator: str) -> str:
    op = operator.lower().strip()
    if any(x in op for x in ("at least", "gte", ">=")):
        return "gte"
    if any(x in op for x in ("at most", "lte", "<=")):
        return "lte"
    if any(x in op for x in ("greater", "more than", "over", "above", "gt", ">")):
        return "gt"
    if any(x in op for x in ("less than", "under", "below", "lt", "<")):
        return "lt"
    if any(x in op for x in ("contain", "include", "has", "like", "with")):
        return "contains"
    if any(x in op for x in ("not", "!=", "neq", "<>")):
        return "neq"
    return "eq"


def _string_match(actual: Any, expected: Any) -> bool:
    actual_s = str(actual).strip()
    expected_s = str(expected).strip()
    if actual_s.lower() == expected_s.lower():
        return True
    if len(expected_s) == 2 and expected_s.isalpha():
        return bool(re.search(rf"\b{re.escape(expected_s.upper())}\b", actual_s, re.IGNORECASE))
    return expected_s.lower() in actual_s.lower()


def _contains_match(actual: Any, needle: str) -> bool:
    n = needle.strip()
    if isinstance(actual, list):
        return any(_contains_match(item, needle) for item in actual)
    text = str(actual)
    if len(n) == 2 and n.isalpha():
        return bool(re.search(rf"\b{re.escape(n)}\b", text, re.IGNORECASE))
    return n.lower() in text.lower()


def _matches_value(actual: Any, kind: str, expected: str | float | int | bool) -> bool:
    actual_num = _coerce_number(actual)
    expected_num = _coerce_number(expected)

    if kind in {"gt", "gte", "lt", "lte"}:
        if actual_num is None or expected_num is None:
            return False
        if kind == "gt":
            return actual_num > expected_num
        if kind == "gte":
            return actual_num >= expected_num
        if kind == "lt":
            return actual_num < expected_num
        return actual_num <= expected_num

    if kind == "contains":
        return _contains_match(actual, str(expected))

    matched = _string_match(actual, expected)
    return not matched if kind == "neq" else matched


def _matches_filter(record: Record, filt: Filter) -> bool:
    actual = record.get(filt.field)
    if actual is None or not filt.values:
        return False

    kind = _operator_kind(filt.operator)
    return any(_matches_value(actual, kind, value) for value in filt.values)


def execute_node(state: AgentState) -> dict[str, Any]:
    records = state["records"]
    plan: QueryPlan = state["plan"]
    logger.info("Node: execute")

    if not plan.filters:
        logger.info("No filters — returning all %d records", len(records))
        matched = sorted(records, key=lambda r: r.identifier())
    else:
        matched = [r for r in records if all(_matches_filter(r, f) for f in plan.filters)]
        logger.info("Matched %d/%d records", len(matched), len(records))
        matched = sorted(matched, key=lambda r: r.identifier())

    return {"matched": matched}
