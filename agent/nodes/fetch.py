import logging

from agent.state import AgentState
from agent.tools.fetch_orders import FetchError, fetch_orders

logger = logging.getLogger(__name__)


def fetch_node(state: AgentState) -> AgentState:
    # Bulk fetch only — no per-orderId tool. The dummy API's GET /api/order/<id>
    # has a substring lookup bug; single-order requests are handled by filtering
    # on orderId after parse instead.
    logger.info("Node: fetch (bulk /api/orders)")

    try:
        raw_orders = fetch_orders()
    except FetchError as exc:
        logger.error("Fetch failed: %s", exc)
        return {"error": str(exc), "status": "error"}

    # Blank records would become empty Send tasks downstream.
    raw_orders = [text for text in raw_orders if text.strip()]

    if not raw_orders:
        logger.warning("Customer API returned no orders")
        return {
            "raw_orders": [],
            "status": "error",
            "error": "Customer API returned no orders.",
        }

    return {"raw_orders": raw_orders, "status": "ok"}
