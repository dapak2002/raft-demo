import logging

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from agent.llm import get_llm
from agent.schema import filter_field_catalog
from agent.services.filter_engine import plan_from_groups
from agent.state import AgentState, FilterGroup
from agent.tools.create_filter import PLAN_TOOLS, execute_plan_tool

logger = logging.getLogger(__name__)

SYSTEM = """\
Convert the user's request into data filters using the provided tools.

Call all required tool calls in a single turn before finishing.
For AND conditions, call add_filter once per condition.
For OR on the same field, call add_or_filter_group once.
For OR across different fields, call add_mixed_or_group once with all alternatives.

Allowed fields (with the operators each supports):
{fields}

Use only the field names listed above with their listed operators.

Guidance:
- Translate EVERY condition in the request into a filter when applicable
- Amount conditions like 'over $500' → total gt 500
- Different filter groups are combined with AND
- Map 'more than' / 'over' → gt, 'at least' → gte, 'less than' → lt, 'at most' → lte
- state values must be two-letter codes (Texas → TX, Ohio → OH)
- orderId: use equals (exact id match only)
- buyer / city: use contains for partial matches
- items: use contains for partial product name (e.g. laptop), equals for exact item
- If no filters apply, do not call any tools
- "show all orders" / "list all orders" → no tools (empty plan returns every record)"""


def plan_node(state: AgentState) -> AgentState:
    """Run the full tool-calling loop in one node (LLM → tools → LLM until done)."""
    user_query = state["user_query"]
    feedback = state.get("plan_feedback")

    messages: list = [
        SystemMessage(content=SYSTEM.format(fields=filter_field_catalog())),
        HumanMessage(content=user_query),
    ]
    if feedback:
        messages.append(
            HumanMessage(
                content=(
                    f"The plan is incomplete: {feedback} "
                    "Call the required filter tools in one turn."
                )
            )
        )

    llm = get_llm().bind_tools(PLAN_TOOLS)
    groups: list[FilterGroup] = []

    logger.info("Starting query plan for: %s", user_query)

    while True:
        response = llm.invoke(messages)
        messages.append(response)

        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            break

        for call in tool_calls:
            result = execute_plan_tool(call["name"], call["args"])
            if isinstance(result, FilterGroup):
                groups.append(result)
                content = f"Added {result.logic} group with {len(result.filters)} filter(s)"
            else:
                content = result
            messages.append(ToolMessage(content=content, tool_call_id=call["id"]))

    plan = plan_from_groups(groups)
    logger.info("Plan built with %d groups", len(plan.groups))

    return {"plan": plan, "plan_complete": False, "plan_feedback": None}
