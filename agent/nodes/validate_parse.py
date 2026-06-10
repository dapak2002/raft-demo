import logging

from agent.state import AgentState

logger = logging.getLogger(__name__)


def validate_parse_node(state: AgentState) -> AgentState:
    parsed_orders = state.get("parsed_orders") or []
    logger.info("Validating parse result: %d orders", len(parsed_orders))

    if parsed_orders:
        return {}

    return {
        "status": "error",
        "error": "No orders could be parsed from the API response.",
    }
