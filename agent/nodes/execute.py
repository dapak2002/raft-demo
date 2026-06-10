import logging

from agent.services.filter_engine import execute_plan, plan_has_filters
from agent.state import AgentState, QueryPlan

logger = logging.getLogger(__name__)


def execute_node(state: AgentState) -> AgentState:
    parsed_orders = state.get("parsed_orders") or []
    data_query = state.get("data_query") or QueryPlan()

    if not plan_has_filters(data_query):
        logger.info("No filters; returning all %d orders", len(parsed_orders))
        matched_orders = sorted(parsed_orders, key=lambda order: order.orderID)
        return {"matched_orders": matched_orders, "status": "ok"}

    logger.info(
        "Applying %d filter groups to %d orders",
        len(data_query.groups),
        len(parsed_orders),
    )

    matched_orders = execute_plan(parsed_orders, data_query)
    logger.info("Matched %d/%d orders", len(matched_orders), len(parsed_orders))

    return {"matched_orders": matched_orders, "status": "ok"}
