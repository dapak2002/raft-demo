"""Verify parsed order fields appear in the source text."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from agent.schema import CANONICAL_FIELDS, Order, _STATE_NAMES, _parse_money_string

logger = logging.getLogger(__name__)

_MONEY_PATTERN = re.compile(r"\$?\s*[\d,]+(?:\.\d+)?")


@dataclass(frozen=True)
class GroundingResult:
    order: Order
    dropped_fields: dict[str, Any] = field(default_factory=dict)
    dropped_items: list[str] = field(default_factory=list)

    @property
    def had_hallucination(self) -> bool:
        return bool(self.dropped_fields or self.dropped_items)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _contains_substring(text: str, value: str) -> bool:
    return _normalize_text(value) in _normalize_text(text)


def _order_id_grounded(order_id: str, text: str) -> bool:
    return bool(re.search(r"\b" + re.escape(order_id) + r"\b", text, re.IGNORECASE))


def _state_grounded(code: str, text: str) -> bool:
    if re.search(r"\b" + re.escape(code) + r"\b", text, re.IGNORECASE):
        return True
    full_name = _STATE_NAMES.get(code.upper())
    if full_name and _contains_substring(text, full_name):
        return True
    return False


def _total_grounded(total: float, text: str) -> bool:
    for match in _MONEY_PATTERN.finditer(text):
        parsed = _parse_money_string(match.group())
        if parsed is not None and abs(parsed - total) < 0.005:
            return True
    return False


def _is_field_grounded(field: str, value: Any, text: str) -> bool:
    if field == "orderId":
        return _order_id_grounded(str(value), text)
    if field == "state":
        return _state_grounded(str(value), text)
    if field == "total":
        return _total_grounded(float(value), text)
    return _contains_substring(text, str(value))


def log_parse_hallucination(
    result: GroundingResult,
    *,
    attempt: int,
    max_attempts: int,
) -> None:
    if not result.had_hallucination:
        return
    logger.warning(
        "Parse hallucination (attempt %d/%d, orderId=%s): dropped fields=%s dropped items=%s",
        attempt,
        max_attempts,
        result.order.orderId or "unknown",
        result.dropped_fields,
        result.dropped_items,
    )


def format_hallucination_feedback(result: GroundingResult) -> str:
    parts = [f"{name}={value!r}" for name, value in result.dropped_fields.items()]
    parts.extend(f"item {item!r}" for item in result.dropped_items)
    return ", ".join(parts)


def apply_grounding(order: Order, source_text: str) -> GroundingResult:
    """Return a grounded order and any values removed as ungrounded."""
    if not source_text.strip():
        return GroundingResult(order=order)

    updates: dict[str, Any] = {}
    dropped_fields: dict[str, Any] = {}
    dropped_items: list[str] = []

    for name in CANONICAL_FIELDS:
        value = getattr(order, name)
        if value is None:
            continue

        if name == "items":
            grounded_items = [
                item for item in value if _contains_substring(source_text, item)
            ]
            removed = [item for item in value if item not in grounded_items]
            dropped_items.extend(removed)
            if not grounded_items:
                updates["items"] = None
            elif len(grounded_items) != len(value):
                updates["items"] = grounded_items
            continue

        if not _is_field_grounded(name, value, source_text):
            dropped_fields[name] = value
            updates[name] = None

    if not updates:
        return GroundingResult(order=order)

    grounded = order.model_copy(update=updates)
    return GroundingResult(
        order=grounded,
        dropped_fields=dropped_fields,
        dropped_items=dropped_items,
    )


def ground_order(order: Order, source_text: str) -> Order:
    """Return a copy with values removed when they are absent from source_text."""
    return apply_grounding(order, source_text).order
