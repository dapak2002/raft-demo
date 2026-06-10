"""Fixed order schema — single source of truth for parse, normalize, and query."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

CanonicalField = Literal["orderId", "buyer", "city", "state", "total", "items"]


class Operator(str, Enum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS = "contains"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"


class Order(BaseModel):
    """Parsed order record. All fields optional until normalize/merge completes."""

    orderId: str | None = Field(default=None, description="Order identifier")
    buyer: str | None = Field(default=None, description="Buyer or customer name in title case")
    city: str | None = Field(default=None, description="City in title case")
    state: str | None = Field(
        default=None,
        description="Two-letter uppercase USPS state code",
    )
    total: float | None = Field(
        default=None,
        description="Order total as a number without $ or commas",
    )
    items: list[str] | None = Field(
        default=None,
        description="Product names in the order, one entry per product",
    )

    def populated_fields(self) -> list[str]:
        return [name for name in CANONICAL_FIELDS if getattr(self, name) is not None]

    def to_json(self) -> dict:
        return self.model_dump(mode="json", exclude_none=True)

    def sort_key(self) -> str:
        if self.orderId is not None:
            return str(self.orderId)
        return str(self.to_json())


# name → (type label, allowed operators, description for planners)
FIELD_SPECS: dict[CanonicalField, tuple[str, frozenset[Operator], str]] = {
    "orderId": (
        "string",
        frozenset({Operator.EQUALS, Operator.NOT_EQUALS}),
        "Order identifier (unique per order)",
    ),
    "buyer": (
        "string",
        frozenset({Operator.EQUALS, Operator.NOT_EQUALS, Operator.CONTAINS}),
        "Buyer or customer name",
    ),
    "city": (
        "string",
        frozenset({Operator.EQUALS, Operator.NOT_EQUALS, Operator.CONTAINS}),
        "City the order ships to or was placed from",
    ),
    "state": (
        "string",
        frozenset({Operator.EQUALS, Operator.NOT_EQUALS}),
        "Two-letter USPS state code (Ohio → OH, Texas → TX)",
    ),
    "total": (
        "number",
        frozenset(
            {
                Operator.EQUALS,
                Operator.NOT_EQUALS,
                Operator.GT,
                Operator.GTE,
                Operator.LT,
                Operator.LTE,
            }
        ),
        "Order total as a number without $ or commas",
    ),
    "items": (
        "list of strings",
        frozenset({Operator.EQUALS, Operator.NOT_EQUALS, Operator.CONTAINS}),
        "Products — contains for partial name, equals/not_equals for exact item",
    ),
}

CANONICAL_FIELDS: tuple[CanonicalField, ...] = tuple(FIELD_SPECS.keys())

_PARSE_FIELD_LINES: dict[CanonicalField, str] = {
    "orderId": "order identifier as a string",
    "buyer": "buyer or customer name in title case",
    "city": "city name in title case (from Location=City, ST, ship-to lines, etc.)",
    "state": "two-letter uppercase USPS code (Ohio → OH, Texas → TX)",
    "total": (
        "order total as a plain number (no $ or commas); use Total, Grand Total, "
        "Order Total, Amount Paid, etc."
    ),
    "items": "list of product names in the order, one entry per product",
}


def is_allowed_field(field: str) -> bool:
    return field in FIELD_SPECS


def operators_for(field: str) -> frozenset[Operator]:
    spec = FIELD_SPECS.get(field)  # type: ignore[arg-type]
    return spec[1] if spec else frozenset()


def parse_prompt() -> str:
    lines = [
        "Extract order data into exactly these fields — no others:",
        *[f"- {name}: {_PARSE_FIELD_LINES[name]}" for name in CANONICAL_FIELDS],
        "",
        "Do not extract dates, zip codes, promo codes, warehouse codes, carriers, "
        "notes, or any other attributes. Unmappable values are logged as schema "
        "drift and dropped. Only use information explicitly in the text. Leave "
        "missing fields null.",
    ]
    return "\n".join(lines)


def filter_field_catalog() -> str:
    lines: list[str] = []
    for name in CANONICAL_FIELDS:
        type_label, ops, description = FIELD_SPECS[name]
        op_str = ", ".join(op.value for op in sorted(ops))
        lines.append(f"- {name} ({type_label}): {op_str} — {description}")
    return "\n".join(lines)
