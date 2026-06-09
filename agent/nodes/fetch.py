import logging
from typing import Any

from agent.state import AgentState
from agent.tools.fetch import invoke_fetch_orders

logger = logging.getLogger(__name__)


def fetch_node(state: AgentState) -> dict[str, Any]:
    logger.info("Node: fetch")
    return {"raw_orders": invoke_fetch_orders(limit=state.get("limit"))}
