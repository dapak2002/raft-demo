#!/usr/bin/env python3
"""Tests for plan canonicalization when the LLM emits flat + nested filters."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from agent.schema import Operator
from agent.services.filter_engine import build_query_plan, execute_plan
from agent.state import Filter, FilterGroup
from agent.schema import Order


def _leaf(field: str, op: Operator, value) -> Filter:
    return Filter(field=field, operator=op, value=value)


def test_prefers_nested_and_group_over_flat_duplicates() -> None:
    """Reproduces OH-or-TX + between-500-1000 with redundant flat filters."""
    flat = [
        _leaf("total", Operator.GTE, 500),
        _leaf("total", Operator.LTE, 1000),
        _leaf("state", Operator.EQUALS, "OH"),
        _leaf("state", Operator.EQUALS, "TX"),
    ]
    nested = FilterGroup(
        operator="and",
        filters=[
            _leaf("total", Operator.GTE, 500),
            _leaf("total", Operator.LTE, 1000),
            FilterGroup(
                operator="or",
                filters=[
                    _leaf("state", Operator.EQUALS, "OH"),
                    _leaf("state", Operator.EQUALS, "TX"),
                ],
            ),
        ],
    )
    plan = build_query_plan([*flat, nested])
    assert plan.filter == nested


def test_merges_partial_group_with_extra_flat_filters() -> None:
    state_or = FilterGroup(
        operator="or",
        filters=[
            _leaf("state", Operator.EQUALS, "OH"),
            _leaf("state", Operator.EQUALS, "TX"),
        ],
    )
    plan = build_query_plan(
        [
            state_or,
            _leaf("total", Operator.GTE, 500),
            _leaf("total", Operator.LTE, 1000),
        ]
    )
    assert plan.filter is not None
    assert plan.filter.operator == "and"
    assert len(plan.filter.filters) == 3


def test_execute_between_oh_or_tx() -> None:
    plan = build_query_plan(
        [
            _leaf("total", Operator.GTE, 500),
            _leaf("total", Operator.LTE, 1000),
            _leaf("state", Operator.EQUALS, "OH"),
            _leaf("state", Operator.EQUALS, "TX"),
            FilterGroup(
                operator="and",
                filters=[
                    _leaf("total", Operator.GTE, 500),
                    _leaf("total", Operator.LTE, 1000),
                    FilterGroup(
                        operator="or",
                        filters=[
                            _leaf("state", Operator.EQUALS, "OH"),
                            _leaf("state", Operator.EQUALS, "TX"),
                        ],
                    ),
                ],
            ),
        ]
    )
    orders = [
        Order(
            orderId="1001",
            buyer="John",
            city="Columbus",
            state="OH",
            total=742.1,
        ),
        Order(
            orderId="1002",
            buyer="Sarah",
            city="Austin",
            state="TX",
            total=156.55,
        ),
        Order(
            orderId="1003",
            buyer="Mike",
            city="Cleveland",
            state="OH",
            total=1299.99,
        ),
    ]
    matched = execute_plan(orders, plan)
    assert [o.orderId for o in matched] == ["1001"]


if __name__ == "__main__":
    test_prefers_nested_and_group_over_flat_duplicates()
    test_merges_partial_group_with_extra_flat_filters()
    test_execute_between_oh_or_tx()
    print("All build_query_plan tests passed.")
