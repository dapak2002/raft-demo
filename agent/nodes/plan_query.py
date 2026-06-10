import logging

from langchain_core.messages import HumanMessage, SystemMessage

from agent.llm import get_llm
from agent.state import AgentState
from agent.tools.create_filter import PLAN_TOOLS

logger = logging.getLogger(__name__)

SYSTEM = """\
Convert the user's request into order data filters using the provided tools.

Call all required tool calls in a single turn before finishing.
For AND conditions, call add_filter once per condition.
For OR on the same field, call add_or_filter_group once (e.g. Texas or Ohio).
For OR across different fields, call add_mixed_or_group once with all alternatives.

Fields: orderID, buyer, state, total

Allowed operators by field:
- orderID: equals, not_equals, contains
- buyer: equals, not_equals, contains
- state: equals, not_equals
- total: equals, not_equals, gt, gte, lt, lte

Guidance:
- Different filter groups are combined with AND
- State names and "from Texas" / "located in Ohio" → state field
- Person names (e.g. Chris, John) → buyer field with contains
- "from" means state when followed by a place; means buyer when followed by a person name
- Map 'more than' / 'over' → gt, 'at least' → gte, 'less than' → lt, 'at most' → lte
- Map state names to 2-letter codes (Ohio → OH, Texas → TX)
- If no filters apply, do not call any tools
- "show all orders" / "list all orders" → no tools (empty plan returns every order)

Examples:
- "show all orders" → no tool calls
- "Ohio and total over 500" → add_filter(state, equals, OH), add_filter(total, gt, 500)
- "Texas or Ohio" → add_or_filter_group(state, equals, [TX, OH])
- "Chris or Texas" → add_mixed_or_group([{buyer, contains, Chris}, {state, equals, TX}])"""


def plan_query_node(state: AgentState) -> AgentState:
    user_query = state["user_query"]
    messages = state.get("messages")

    if not messages:
        logger.info("Starting query plan for: %s", user_query)
        messages = [
            SystemMessage(content=SYSTEM),
            HumanMessage(content=user_query),
        ]
    else:
        messages = list(messages)

    llm = get_llm().bind_tools(PLAN_TOOLS)
    response = llm.invoke(messages)

    return {"messages": [response]}
