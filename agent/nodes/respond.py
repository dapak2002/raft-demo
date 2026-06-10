import logging

from agent.state import AgentState

logger = logging.getLogger(__name__)


def respond_node(state: AgentState) -> AgentState:
    status = state.get("status", "ok")

    if status == "error":
        error = state.get("error") or "An unknown error occurred."
        logger.info("Building error response: %s", error)
        return {"status": "error", "error": error}

    matched_orders = state.get("matched_orders") or []
    logger.info("Building success response for %d orders", len(matched_orders))
    return {"status": "ok"}
