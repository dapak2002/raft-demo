import logging

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from agent.llm import get_llm
from agent.services.filter_engine import plan_has_filters
from agent.state import AgentState, QueryPlan

logger = logging.getLogger(__name__)

REVIEW_PROMPT = """\
Decide if the filter plan satisfies the user's request.

User request: {user_query}

Current plan (groups of filters only):
{plan_json}

Rules:
- Available fields: orderID, buyer, state, total
- "show all orders" / "list all" / no criteria → empty plan is correct; set match_all=true, complete=true
- Filtered requests → plan must include every condition; set match_all=false
- complete=true means the plan is ready to execute
- match_all is YOUR output flag, not a field in the plan JSON"""


class PlanReview(BaseModel):
    complete: bool = Field(description="True when the plan is ready to execute")
    match_all: bool = Field(
        default=False,
        description="True when the user wants every order with no filtering",
    )
    missing: str | None = Field(
        default=None,
        description="What is wrong with the plan when complete is false",
    )


def _infer_match_all(review: PlanReview, empty_plan: bool) -> bool:
    if review.match_all:
        return True
    if not empty_plan:
        return False

    missing = (review.missing or "").lower()
    if any(
        phrase in missing
        for phrase in ("match_all", "all order", "no filter", "every order", "no filtering")
    ):
        return True
    return False


def review_plan_node(state: AgentState) -> AgentState:
    user_query = state["user_query"]
    data_query = state.get("data_query") or QueryPlan()
    attempts = state.get("plan_attempts", 0)
    empty_plan = not plan_has_filters(data_query)

    chain = get_llm().with_structured_output(PlanReview)
    review = chain.invoke(
        REVIEW_PROMPT.format(
            user_query=user_query,
            plan_json=data_query.model_dump_json(indent=2),
        )
    )

    match_all = _infer_match_all(review, empty_plan)
    accepted = review.complete or (match_all and empty_plan)

    if accepted:
        logger.info("Plan review passed (match_all=%s)", match_all)
        updates: AgentState = {
            "plan_reviewed": True,
            "match_all": match_all,
        }
        if match_all:
            updates["data_query"] = QueryPlan()
        return updates

    logger.warning("Plan review incomplete: %s", review.missing)

    updates = {
        "plan_reviewed": False,
        "plan_attempts": attempts + 1,
        "match_all": match_all,
        "plan_feedback": review.missing,
    }

    if match_all:
        updates["data_query"] = QueryPlan()
        updates["messages"] = [
            HumanMessage(content="User wants all orders. Do not call any tools.")
        ]
    else:
        updates["messages"] = [
            HumanMessage(
                content=(
                    f"The plan is incomplete: {review.missing}. "
                    "Call the required filter tools in one turn."
                )
            )
        ]

    return updates
