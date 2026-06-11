"""LangGraph fault-tolerance policies and error handlers."""

import logging

import requests
from langgraph.errors import NodeError, NodeTimeoutError
from langgraph.types import Command, RetryPolicy, TimeoutPolicy, default_retry_on

from agent.state import AgentState
from agent.tools.fetch_orders import FetchError
from config import CUSTOMER_API_URL

logger = logging.getLogger(__name__)


def transient_retry_on(exc: BaseException) -> bool:
    """Retry transient failures; skip deterministic customer-API errors."""
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
    return default_retry_on(exc)


def log_node_attempt(node: str, runtime) -> None:
    """Log LangGraph RetryPolicy re-attempts (attempt 1 is the initial run)."""
    from config import NODE_MAX_RETRIES

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


def _user_error_message(error: NodeError) -> str:
    """Map internal exceptions to short, user-facing messages."""
    exc = error.error
    node = error.node

    if node == "fetch":
        if isinstance(exc, FetchError):
            return str(exc)
        if isinstance(exc, requests.RequestException):
            base = CUSTOMER_API_URL.rstrip("/")
            if isinstance(exc, requests.ConnectionError):
                return (
                    f"Failed to reach customer API at {base}. "
                    "Check that the server is running."
                )
            if isinstance(exc, requests.Timeout):
                return f"Customer API at {base} timed out after {exc}."
            return f"Customer API request to {base} failed."

    if isinstance(exc, NodeTimeoutError):
        return f"{node} timed out after {exc.elapsed:.0f}s."

    return f"{node} failed: {exc}"


def node_error_handler(state: AgentState, error: NodeError) -> Command:
    """Route retry-exhausted node failures to respond with an error payload."""
    message = _user_error_message(error)
    # Recovered via Command(goto=...) — log the message only, no traceback.
    logger.warning("%s failed after retries: %s", error.node, message)
    return Command(
        update={"status": "error", "error": message},
        goto="respond",
    )
