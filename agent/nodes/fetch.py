import logging

import requests

from agent.state import AgentState
from config import CUSTOMER_API_URL, FETCH_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


class FetchError(Exception):
    pass


def _fetch_orders(limit: int | None = None) -> list[str]:
    url = f"{CUSTOMER_API_URL.rstrip('/')}/api/orders"
    params = {"limit": limit} if limit is not None else None

    logger.info("Fetching orders from %s params=%s", url, params)

    try:
        response = requests.get(url, params=params, timeout=FETCH_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise FetchError(f"Failed to reach customer API at {url}: {exc}") from exc

    if response.status_code != 200:
        raise FetchError(f"Customer API returned {response.status_code}: {response.text[:500]}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise FetchError("Customer API response is not valid JSON") from exc

    raw_orders = payload.get("raw_orders") or []
    if not isinstance(raw_orders, list):
        raise FetchError(f"Expected raw_orders list, got {type(raw_orders).__name__}")

    return [str(order) for order in raw_orders if order]


def fetch_node(state: AgentState) -> AgentState:
    return {"raw_orders": _fetch_orders()}
