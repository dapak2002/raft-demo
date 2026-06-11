import logging

import requests

from agent.services.schema_drift import log_payload_drift
from config import CUSTOMER_API_URL, FETCH_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


class FetchError(Exception):
    pass


def fetch_orders(limit: int | None = None) -> list[str]:
    """Fetch unstructured order text from the customer orders API."""
    url = f"{CUSTOMER_API_URL.rstrip('/')}/api/orders"
    params = {"limit": limit} if limit is not None else None

    logger.info("Fetching orders from %s params=%s", url, params)

    # Let connection/timeout errors propagate for LangGraph RetryPolicy.
    response = requests.get(url, params=params, timeout=FETCH_TIMEOUT_SECONDS)

    if response.status_code >= 500:
        response.raise_for_status()

    if response.status_code != 200:
        raise FetchError(
            f"Customer API at {url} returned {response.status_code}: {response.text[:500]}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise FetchError(f"Customer API at {url} response is not valid JSON") from exc

    if isinstance(payload, dict):
        log_payload_drift(payload)
    else:
        logger.warning(
            "Schema drift: expected fields in a JSON object, got %s",
            type(payload).__name__,
        )

    raw_orders = payload.get("raw_orders") or []
    if not isinstance(raw_orders, list):
        raise FetchError(
            f"Customer API at {url} expected raw_orders list, "
            f"got {type(raw_orders).__name__}"
        )

    orders = [str(order) for order in raw_orders if order]
    logger.info("Fetched %d orders", len(orders))
    return orders
