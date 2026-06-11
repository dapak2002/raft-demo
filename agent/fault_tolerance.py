"""LangGraph fault-tolerance policies and error handlers."""

import asyncio
import logging

import httpx
import requests
from langgraph.errors import NodeError, NodeTimeoutError
from langgraph.types import Command, RetryPolicy, TimeoutPolicy, default_retry_on
from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

from agent.state import AgentState
from agent.tools.fetch_orders import FetchError
from config import CUSTOMER_API_URL, NODE_MAX_RETRIES

logger = logging.getLogger(__name__)


def _request_url(exc: requests.RequestException) -> str:
    if exc.request is not None and exc.request.url:
        return exc.request.url
    return f"{CUSTOMER_API_URL.rstrip('/')}/api/orders"


def is_transient_error(exc: BaseException) -> bool:
    """Whether an exception is worth retrying (shared by RetryPolicy and parse windows)."""
    if isinstance(exc, FetchError):
        return False
    # requests.ConnectionError subclasses OSError, which default_retry_on skips.
    if isinstance(exc, requests.RequestException):
        if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
            return True
        if isinstance(exc, requests.HTTPError):
            return exc.response is not None and 500 <= exc.response.status_code < 600
        return False
    if isinstance(exc, NodeTimeoutError):
        return True
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        return True
    if isinstance(exc, (APIConnectionError, APITimeoutError, RateLimitError)):
        return True
    if isinstance(exc, APIStatusError) and exc.status_code is not None:
        return 500 <= exc.status_code < 600
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return 500 <= exc.response.status_code < 600
    return default_retry_on(exc)


def transient_retry_on(exc: BaseException) -> bool:
    """Retry transient failures; skip deterministic customer-API errors."""
    return is_transient_error(exc)


def log_node_attempt(node: str, runtime) -> None:
    """Log LangGraph RetryPolicy re-attempts (attempt 1 is the initial run)."""
    info = getattr(runtime, "execution_info", None)
    if info is None or info.node_attempt <= 1:
        return
    logger.warning(
        "Retrying %s (attempt %d of %d)",
        node,
        info.node_attempt,
        NODE_MAX_RETRIES,
    )


def build_retry_policy(
    *,
    max_attempts: int,
    initial_interval: float = 0.5,
    backoff_factor: float = 2.0,
) -> RetryPolicy:
    return RetryPolicy(
        max_attempts=max_attempts,
        initial_interval=initial_interval,
        backoff_factor=backoff_factor,
        jitter=True,
        retry_on=transient_retry_on,
    )


def build_timeout_policy(run_timeout: float) -> TimeoutPolicy:
    return TimeoutPolicy(run_timeout=run_timeout)

# for the frontend to display the node names in the trace
_NODE_LABELS = {
    "fetch": "Fetch orders",
    "parse_record": "Parse records",
    "merge_parse": "Merge parsed data",
    "plan": "Build filter plan",
    "review_plan": "Review plan",
    "validate_plan": "Validate plan",
    "execute": "Apply filters",
    "respond": "Complete",
}


def _user_error_message(error: NodeError) -> str:
    """Map internal exceptions to short, user-facing messages."""
    exc = error.error
    node = error.node

    if node == "fetch":
        if isinstance(exc, FetchError):
            return str(exc)
        if isinstance(exc, requests.RequestException):
            url = _request_url(exc)
            if isinstance(exc, requests.ConnectionError):
                return (
                    "Couldn't reach the order data service "
                    f"(expected at {url})."
                )
            if isinstance(exc, requests.Timeout):
                return f"The order data service timed out ({url})."
            return f"The order data service returned an error ({url})."

    if isinstance(exc, NodeTimeoutError):
        label = _NODE_LABELS.get(node, node.replace("_", " "))
        return f"{label} timed out after {exc.elapsed:.0f}s."

    label = _NODE_LABELS.get(node, node.replace("_", " "))
    return f"{label} failed: {exc}"


def node_error_handler(state: AgentState, error: NodeError) -> Command:
    """Route retry-exhausted node failures to respond with an error payload."""
    message = _user_error_message(error)
    # Recovered via Command(goto=...) — log the message only, no traceback.
    logger.warning("%s failed after retries: %s", error.node, message)
    return Command(
        update={
            "status": "error",
            "error": message,
            "failed_node": error.node,
        },
        goto="respond",
    )
