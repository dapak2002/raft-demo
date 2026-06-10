import logging

from agent.state import AgentState
from agent.tools.fetch_orders import fetch_orders

logger = logging.getLogger(__name__)


def fetch_node(state: AgentState) -> AgentState:
    logger.info("Node: fetch")
    raw_orders = fetch_orders.invoke({})
    return {"raw_orders": raw_orders}
