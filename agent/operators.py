from enum import Enum


class Operator(str, Enum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS = "contains"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"


FIELD_OPERATORS: dict[str, frozenset[Operator]] = {
    "orderID": frozenset({Operator.EQUALS, Operator.NOT_EQUALS, Operator.CONTAINS}),
    "buyer": frozenset({Operator.EQUALS, Operator.NOT_EQUALS, Operator.CONTAINS}),
    "state": frozenset({Operator.EQUALS, Operator.NOT_EQUALS}),
    "total": frozenset(
        {
            Operator.EQUALS,
            Operator.NOT_EQUALS,
            Operator.GT,
            Operator.GTE,
            Operator.LT,
            Operator.LTE,
        }
    ),
}
