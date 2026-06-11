"""Fixed order schema — single source of truth for parse and query."""

import re
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

CanonicalField = Literal["orderId", "buyer", "city", "state", "total", "items"]

_STATE_NAMES: dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}

_NAME_TO_CODE = {name.lower(): code for code, name in _STATE_NAMES.items()}


def normalize_state(value: str) -> str | None:
    """Map a state code or full name to a two-letter USPS code."""
    if not value or not str(value).strip():
        return None

    code = str(value).strip().upper()
    if code in _STATE_NAMES:
        return code

    name = re.sub(r"\s+", " ", str(value).strip().lower())
    return _NAME_TO_CODE.get(name)


def _parse_money_string(value: str) -> float | None:
    numeric = re.sub(r"[$,\s]", "", value.strip())
    if numeric and re.fullmatch(r"-?\d+(\.\d+)?", numeric):
        return float(numeric)
    return None


class Operator(str, Enum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS = "contains"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"


class Order(BaseModel):
    """Parsed order record — only the six canonical fields below."""

    orderId: str | None = Field(default=None, description="Order identifier")
    buyer: str | None = Field(default=None, description="Buyer or customer name")
    city: str | None = Field(default=None, description="City name")
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

    @field_validator("orderId", "buyer", "city", mode="before")
    @classmethod
    def _strip_optional_str(cls, value: Any) -> str | None:
        if value is None:
            return None
        stripped = str(value).strip()
        return stripped or None

    @field_validator("state", mode="before")
    @classmethod
    def _normalize_state(cls, value: Any) -> str | None:
        if value is None:
            return None
        return normalize_state(str(value))

    @field_validator("total", mode="before")
    @classmethod
    def _coerce_total(cls, value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            return _parse_money_string(value)
        return None

    @field_validator("items", mode="before")
    @classmethod
    def _coerce_items(cls, value: Any) -> list[str] | None:
        if value is None:
            return None
        if isinstance(value, str):
            value = [part.strip() for part in value.split(",")]
        if not isinstance(value, list):
            return None
        items = [str(item).strip() for item in value if str(item).strip()]
        return items or None

    def populated_fields(self) -> list[str]:
        return [name for name in CANONICAL_FIELDS if getattr(self, name) is not None]

    def data_score(self) -> int:
        """Higher score means more populated canonical fields."""
        score = 0
        for name in CANONICAL_FIELDS:
            value = getattr(self, name)
            if value is None:
                continue
            if name == "items":
                score += 1 + len(value)
            else:
                score += 1
        return score

    def to_json(self) -> dict:
        return self.model_dump(mode="json", exclude_none=True)

    def sort_key(self) -> str:
        if self.orderId is not None:
            return str(self.orderId)
        return str(self.to_json())


class ParseExtraction(Order):
    """LLM parse output — canonical fields plus unmapped source labels."""

    additional_fields: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Labeled fields from the source text that do not map to the six "
            "canonical fields — e.g. Warehouse, Ship-from. Empty if none."
        ),
    )


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
    "orderId": "order identifier (map Order ID, order_id, etc.)",
    "buyer": "buyer or customer name (map Customer, Purchaser, etc.)",
    "city": "city name (map Location, Ship-To city, etc.)",
    "state": "two-letter USPS code — map Ohio → OH, Texas → TX",
    "total": "order total as a plain number — map Total, Grand Total, Amount, etc.",
    "items": "list of product names, one entry per product",
}


def is_allowed_field(field: str) -> bool:
    return field in FIELD_SPECS


def operators_for(field: str) -> frozenset[Operator]:
    spec = FIELD_SPECS.get(field)  # type: ignore[arg-type]
    return spec[1] if spec else frozenset()


def parse_prompt() -> str:
    lines = [
        "Map source labels onto these six canonical fields:",
        *[f"- {name}: {_PARSE_FIELD_LINES[name]}" for name in CANONICAL_FIELDS],
        "",
        "Also set additional_fields to any other labeled key-value pairs in the "
        "source that do not fit above (use an empty object if none).",
        "",
        "Only use information explicitly in the text. Leave missing canonical fields "
        "null (do not guess or invent values).",
    ]
    return "\n".join(lines)


def filter_field_catalog() -> str:
    lines: list[str] = []
    for name in CANONICAL_FIELDS:
        type_label, ops, description = FIELD_SPECS[name]
        op_str = ", ".join(op.value for op in sorted(ops))
        lines.append(f"- {name} ({type_label}): {op_str} — {description}")
    return "\n".join(lines)
