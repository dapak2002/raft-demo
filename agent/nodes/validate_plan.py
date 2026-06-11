import logging

from agent.services.filter_engine import plan_has_filters
from agent.state import AgentState, QueryPlan

logger = logging.getLogger(__name__)


def validate_plan_node(state: AgentState) -> AgentState:
    if not state.get("plan_complete"):
        feedback = state.get("plan_feedback") or "Plan is incomplete."
        logger.warning("Rejecting incomplete plan: %s", feedback)
        return {
            "status": "error",
            "error": f"Could not build a complete filter plan: {feedback}",
        }

    plan = state.get("plan") or QueryPlan()

    if plan_has_filters(plan):
        logger.info("Query plan validated with filter tree")
        return {}

    if state.get("plan_complete"):
        logger.info("Query plan validated with no filters")
        return {}

    logger.warning("No filters produced for query: %s", state["user_query"])
    return {
        "status": "error",
        "error": "Could not determine any filter conditions from the request.",
    }
