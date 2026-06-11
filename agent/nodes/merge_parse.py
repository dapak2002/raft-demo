import logging

from agent.schema import Order
from agent.state import AgentState

logger = logging.getLogger(__name__)


def _dedupe_orders(orders: list[Order]) -> list[Order]:
    """Keep one record per orderId — prefer the version with the most data."""
    by_id: dict[str, Order] = {}
    unlabeled: list[Order] = []

    for order in orders:
        order_id = order.orderId
        if order_id is None:
            unlabeled.append(order)
            continue

        key = str(order_id)
        existing = by_id.get(key)
        if existing is None:
            by_id[key] = order
            continue

        if order.data_score() > existing.data_score():
            logger.warning(
                "Duplicate orderId %s from bulk fetch: keeping richer record "
                "(score %d > %d), dropping %s — single-order queries still resolve "
                "via orderId filter",
                key,
                order.data_score(),
                existing.data_score(),
                existing,
            )
            by_id[key] = order
        else:
            logger.warning(
                "Duplicate orderId %s from bulk fetch: keeping richer record "
                "(score %d >= %d), dropping %s — single-order queries still resolve "
                "via orderId filter",
                key,
                existing.data_score(),
                order.data_score(),
                order,
            )

    deduped = list(by_id.values()) + unlabeled
    return sorted(deduped, key=Order.sort_key)


def merge_parse_node(state: AgentState) -> AgentState:
    """Reduce step after Send fan-out: dedupe, sort, and replace parsed_orders."""
    raw_orders = state.get("raw_orders") or []
    parts = state.get("parsed_orders") or []
    merged = _dedupe_orders(parts)

    logger.info(
        "Merged %d parsed records from %d raw orders", len(merged), len(raw_orders)
    )

    if not merged:
        return {
            "parsed_orders": ("replace", []),
            "status": "error",
            "error": "No orders could be parsed from the API response.",
        }

    return {"parsed_orders": ("replace", merged)}
