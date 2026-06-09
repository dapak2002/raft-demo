import logging

import requests
from langchain_core.tools import tool

from config import CUSTOMER_API_URL, FETCH_PAGE_SIZE, FETCH_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


class FetchError(Exception):
    pass


def _fetch_page(offset: int = 0, page_size: int | None = None) -> tuple[list[str], bool]:
    """Fetch one page. Returns (orders, has_more).

    Omit page_size to request without a limit param (full fetch).
    """
    url = f"{CUSTOMER_API_URL.rstrip('/')}/api/orders"
    params: dict[str, int] = {}
    if page_size is not None:
        params["limit"] = page_size
    if offset > 0:
        params["offset"] = offset

    logger.info("Fetching from %s params=%s", url, params or None)

    try:
        response = requests.get(url, params=params or None, timeout=FETCH_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise FetchError(f"Failed to reach customer API at {url}: {exc}") from exc

    if response.status_code != 200:
        raise FetchError(f"Customer API returned {response.status_code}: {response.text[:500]}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise FetchError("Customer API response is not valid JSON") from exc

    raw_orders = payload.get("raw_orders") or payload.get("orders") or payload.get("data") or []
    if not isinstance(raw_orders, list):
        raise FetchError(f"Expected a list of orders, got {type(raw_orders).__name__}")

    orders = [str(item) for item in raw_orders if item]

    if "has_more" in payload:
        return orders, bool(payload["has_more"])

    if offset > 0:
        return [], False

    total = payload.get("total")
    if isinstance(total, int) and page_size is not None and offset + len(orders) < total:
        return orders, True

    return orders, False


def _paginated_fetch(page_size: int | None, max_total: int | None = None) -> list[str]:
    all_orders: list[str] = []
    offset = 0
    pages = 0

    while True:
        remaining = None if max_total is None else max_total - len(all_orders)
        if remaining is not None and remaining <= 0:
            break

        request_size = page_size
        if page_size is not None and remaining is not None:
            request_size = min(page_size, remaining)

        page, has_more = _fetch_page(offset=offset, page_size=request_size)
        pages += 1
        all_orders.extend(page)

        if not has_more or not page:
            break

        offset += len(page)

    logger.info("Fetched %d order(s) in %d page(s)", len(all_orders), pages)
    return all_orders


def _fetch_with_limit_backoff(
    *,
    try_without_limit: bool,
    initial_limit: int,
    max_total: int | None = None,
) -> list[str]:
    last_error: FetchError | None = None

    if try_without_limit:
        try:
            logger.info("Trying fetch without limit")
            return _paginated_fetch(page_size=None, max_total=max_total)
        except FetchError as exc:
            logger.warning("Fetch without limit failed (%s)", exc)
            last_error = exc

    limit = initial_limit
    while limit > 0:
        try:
            logger.info("Trying fetch with limit=%d", limit)
            return _paginated_fetch(page_size=limit, max_total=max_total)
        except FetchError as exc:
            logger.warning("Fetch with limit=%d failed (%s), lowering limit", limit, exc)
            last_error = exc
            limit //= 2

    raise FetchError(
        f"Fetch failed after lowering limit to 0. Last error: {last_error}"
    ) from last_error


def fetch_raw_orders(user_limit: int | None = None) -> list[str]:
    if user_limit is not None:
        return _fetch_with_limit_backoff(
            try_without_limit=False,
            initial_limit=user_limit,
            max_total=user_limit,
        )

    return _fetch_with_limit_backoff(
        try_without_limit=True,
        initial_limit=FETCH_PAGE_SIZE,
    )


@tool
def fetch_orders(limit: int | None = None) -> list[str]:
    """Fetch unstructured order text from the customer orders API.

    Tries a full fetch first; on failure retries with decreasing limits until
    success or limit reaches 0.
    """
    return fetch_raw_orders(limit=limit)


def invoke_fetch_orders(limit: int | None = None) -> list[str]:
    return fetch_orders.invoke({"limit": limit})
