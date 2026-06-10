import logging

from agent.services.filter_engine import plan_has_filters
from agent.state import AgentState, QueryPlan

logger = logging.getLogger(__name__)


def validate_plan_node(state: AgentState) -> AgentState:
    plan = state.get("plan") or QueryPlan()

    if state.get("match_all"):
        if plan_has_filters(plan):
            logger.warning("Ignoring %d filter groups for match-all query", len(plan.groups))
            return {"plan": QueryPlan(), "match_all": True}
        logger.info("Match-all query validated with no filters")
        return {"match_all": True}

    if plan_has_filters(plan):
        logger.info("Query plan validated with %d groups", len(plan.groups))
        return {}

    logger.warning("No filters produced for query: %s", state["user_query"])
    return {
        "status": "error",
        "error": "Could not determine any filter conditions from the request.",
    }
