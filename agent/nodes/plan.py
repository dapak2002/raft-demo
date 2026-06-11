import logging

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.runtime import Runtime

from agent.fault_tolerance import log_node_attempt
from agent.llm import get_llm
from agent.llm_limits import plan_tool_turn_limit, prepare_plan_feedback
from agent.schema import filter_field_catalog
from agent.services.filter_engine import build_query_plan
from agent.state import AgentState, Filter, FilterGroup, FilterNode
from agent.tools.create_filter import PLAN_TOOLS, execute_plan_tool

logger = logging.getLogger(__name__)

SYSTEM = """\
Convert the user's request into data filters using the provided tools.

Call all required tool calls in a single turn before finishing.
A filter is field + comparison operator + value.
Use add_filter for single conditions.
Use combine_filters to group filters with and/or (supports nesting).

Allowed fields (with the operators each supports):
{fields}

Use only the field names listed above with their listed operators.

Guidance:
- Translate EVERY condition in the request into a filter when applicable
- Total range constraints → pair gte/lte (or gt/lt) on total
- For multi-condition queries, prefer ONE combine_filters(operator="and", ...) with the full tree
- Same-field OR → combine_filters(operator="or", filters=[...])
- Cross-field OR → combine_filters(operator="or", filters=[...])
- Do NOT emit separate add_filter calls for conditions already inside combine_filters
- Simple single-condition queries may use add_filter alone; multiple add_filter calls are combined with AND
- Map comparative language to operators: more than/over → gt, at least → gte, less than → lt, at most → lte
- state values must be two-letter USPS codes
- orderId: use equals for exact match
- buyer / city: use contains for partial matches
- items: use contains for partial match, equals for exact item
- If no filters apply, do not call any tools
- Match-all requests with no criteria → no tools (empty plan returns every record)"""


def _describe_filter(filter_part: Filter | FilterGroup) -> str:
    if isinstance(filter_part, Filter):
        return f"{filter_part.field} {filter_part.operator.value} {filter_part.value!r}"
    child_count = len(filter_part.filters)
    label = "conditions" if child_count != 1 else "condition"
    return f"{filter_part.operator.upper()} group with {child_count} {label}"


def _run_plan_tool(name: str, args: dict) -> tuple[FilterNode | None, str]:
    """Run one filter tool; return (filter, success message) or (None, error)."""
    result = execute_plan_tool(name, args)
    if isinstance(result, (Filter, FilterGroup)):
        return result, f"OK — added filter: {_describe_filter(result)}"
    return None, f"Error — {result}"


async def plan_node(state: AgentState, runtime: Runtime) -> AgentState:
    """Run the full tool-calling loop in one node (LLM → tools → LLM until done)."""
    log_node_attempt("plan", runtime)
    user_query = state["user_query"]
    feedback = state.get("plan_feedback")
    if feedback:
        logger.warning(
            "Re-planning after review feedback (graph attempt %d): %s",
            state.get("plan_attempts", 0),
            feedback,
        )

    messages: list = [
        SystemMessage(content=SYSTEM.format(fields=filter_field_catalog())),
        HumanMessage(content=user_query),
    ]
    if feedback:
        feedback = prepare_plan_feedback(feedback)
        messages.append(
            HumanMessage(
                content=(
                    f"The plan is incomplete: {feedback} "
                    "Call the required filter tools in one turn."
                )
            )
        )

    llm = get_llm().bind_tools(PLAN_TOOLS)
    accumulated_filters: list[FilterNode] = []
    max_turns = plan_tool_turn_limit()

    logger.info("Starting query plan for: %s", user_query)

    for _ in range(max_turns):
        response = await llm.ainvoke(messages)
        messages.append(response)

        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            break

        for call in tool_calls:
            filter_part, tool_message = _run_plan_tool(call["name"], call["args"])
            if filter_part is not None:
                accumulated_filters.append(filter_part)
            messages.append(ToolMessage(content=tool_message, tool_call_id=call["id"]))
    else:
        logger.warning(
            "Plan tool loop hit max turns (%d); using %d filter(s) collected so far",
            max_turns,
            len(accumulated_filters),
        )

    plan = build_query_plan(accumulated_filters)
    top_level_count = len(plan.filter.filters) if plan.filter else 0
    logger.info("Query plan built with %d top-level filter(s)", top_level_count)

    return {"plan": plan, "plan_complete": False, "plan_feedback": None}
