import logging

from agent.services.filter_engine import plan_has_filters
from agent.state import AgentState, QueryPlan

logger = logging.getLogger(__name__)


def _feedback_implies_match_all(feedback: str | None) -> bool:
    if not feedback:
        return False
    lower = feedback.lower()
    return any(
        phrase in lower
        for phrase in ("match_all", "all order", "no filter", "every order", "no filtering")
    )


def validate_plan_node(state: AgentState) -> AgentState:
    data_query = state.get("data_query") or QueryPlan()

    if state.get("match_all") or _feedback_implies_match_all(state.get("plan_feedback")):
        if plan_has_filters(data_query):
            logger.warning("Clearing filters for match-all query")
        else:
            logger.info("Match-all query validated with no filters")
        return {"data_query": QueryPlan(), "match_all": True}

    if plan_has_filters(data_query):
        logger.info("Query plan validated with %d groups", len(data_query.groups))
        return {}

    logger.warning("No filters produced for query: %s", state["user_query"])
    return {
        "status": "error",
        "error": "Could not determine any filter conditions from the request.",
    }
