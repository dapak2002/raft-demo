"""Log schema drift from API payloads and parse extraction."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_EXPECTED_FIELDS = frozenset({"status", "raw_orders"})


def log_payload_drift(payload: dict[str, Any]) -> None:
    additional_fields = sorted(set(payload.keys()) - _EXPECTED_FIELDS)
    if additional_fields:
        logger.warning(
            "Schema drift: additional fields %s (expected fields: %s)",
            additional_fields,
            sorted(_EXPECTED_FIELDS),
        )


def log_parse_drift(
    additional_fields: dict[str, str],
    *,
    order_id: str | None = None,
) -> None:
    if not additional_fields:
        return
    logger.warning(
        "Schema drift: orderId=%s additional fields %s",
        order_id or "unknown",
        additional_fields,
    )
