import logging

from agent.state import AgentState

logger = logging.getLogger(__name__)


def respond_node(state: AgentState) -> AgentState:
    orders = state.get("orders") or []
    logger.info("Building response for %d orders", len(orders))

    return {
        "orders": [order.model_dump() for order in orders],
    }
