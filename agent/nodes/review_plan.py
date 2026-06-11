import logging

from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from agent.fault_tolerance import log_node_attempt
from agent.llm import get_llm
from agent.llm_limits import prepare_plan_json
from agent.schema import filter_field_catalog
from agent.state import AgentState, QueryPlan

logger = logging.getLogger(__name__)

REVIEW_PROMPT = """\
Decide if the filter plan satisfies the user's request.

User request: {user_query}

Allowed fields:
{fields}

Current plan (filter tree):
{plan_json}

Rules:
- Match-all requests with no criteria → empty plan is correct; set complete=true
- Filtered requests → identify every condition in the request, then verify each is
  represented in the filter tree (including nested and/or groups). If ANY condition
  is missing, set complete=false and name it in 'missing'
- Disjunctive conditions on the same field must appear under an or group, not as
  conflicting top-level equals filters
- Use only the allowed fields listed above
- state filters should use two-letter codes
- complete=true means the plan is ready to execute"""


class PlanReview(BaseModel):
    complete: bool = Field(description="True when the plan is ready to execute")
    missing: str | None = Field(
        default=None,
        description="What is wrong with the plan when complete is false",
    )


async def review_plan_node(state: AgentState, runtime: Runtime) -> AgentState:
    log_node_attempt("review_plan", runtime)
    user_query = state["user_query"]
    data_query = state.get("plan") or QueryPlan()
    attempts = state.get("plan_attempts", 0)
    field_catalog = filter_field_catalog()

    plan_json = prepare_plan_json(data_query.model_dump_json(indent=2))
    chain = get_llm().with_structured_output(PlanReview)
    review = await chain.ainvoke(
        REVIEW_PROMPT.format(
            user_query=user_query,
            fields=field_catalog,
            plan_json=plan_json,
        )
    )

    if review.complete:
        logger.info("Plan review passed")
        return {"plan_complete": True}

    feedback = review.missing or "Plan is incomplete."
    logger.warning("Plan review incomplete: %s", feedback)

    return {
        "plan_complete": False,
        "plan_attempts": attempts + 1,
        "plan_feedback": feedback,
    }
