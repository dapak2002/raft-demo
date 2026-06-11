import logging

from langgraph.runtime import Runtime

from agent.fault_tolerance import log_node_attempt
from agent.state import AgentState
from agent.tools.fetch_orders import fetch_orders

logger = logging.getLogger(__name__)


async def fetch_node(state: AgentState, runtime: Runtime) -> AgentState:
    # Bulk fetch only — no per-orderId tool. The dummy API's GET /api/order/<id>
    # has a substring lookup bug; single-order requests are handled by filtering
    # on orderId after parse instead.
    log_node_attempt("fetch", runtime)
    logger.info("Node: fetch (bulk /api/orders)")

    raw_orders = fetch_orders()

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
