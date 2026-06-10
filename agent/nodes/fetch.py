import logging

from agent.state import AgentState
from agent.tools.fetch_orders import FetchError, fetch_orders

logger = logging.getLogger(__name__)


def fetch_node(state: AgentState) -> AgentState:
    logger.info("Node: fetch")

    try:
        raw_orders = fetch_orders.invoke({})
    except FetchError as exc:
        logger.error("Fetch failed: %s", exc)
        return {"error": str(exc), "status": "error"}

    if not raw_orders:
        logger.warning("Customer API returned no orders")
        return {
            "raw_orders": [],
            "status": "error",
            "error": "Customer API returned no orders.",
        }

    return {"raw_orders": raw_orders, "status": "ok"}
