import logging

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from agent.llm import get_llm
from agent.state import AgentState, Filter, QueryPlan
from agent.tools.create_filter import build_create_filter_tool

logger = logging.getLogger(__name__)

SYSTEM = """\
Convert the user's request into order data filters using the create_filter tool.

Call create_filter once for each condition in the request.
Do not respond with filters in plain text — use the tool only.

Fields: orderID, buyer, state, total

Allowed operators by field:
- orderID: equals, not_equals, contains
- buyer: equals, not_equals, contains
- state: equals, not_equals
- total: equals, not_equals, gt, gte, lt, lte

Guidance:
- Map 'more than' → gt, 'at least' → gte, 'less than' → lt, 'at most' → lte
- Use contains for partial buyer or orderID matches
- Map state names to 2-letter codes (Ohio → OH)
- If no filters apply, do not call the tool"""


def generate_data_query_node(state: AgentState) -> AgentState:
    user_query = state["user_query"]
    logger.info("Generating data query for: %s", user_query)

    filters: list[Filter] = []
    create_filter = build_create_filter_tool(filters)
    llm = get_llm().bind_tools([create_filter])

    messages = [
        SystemMessage(content=SYSTEM),
        HumanMessage(content=user_query),
    ]

    for _ in range(10):
        response = llm.invoke(messages)
        if not response.tool_calls:
            break

        messages.append(response)
        for call in response.tool_calls:
            if call["name"] != "create_filter":
                continue
            result = create_filter.invoke(call["args"])
            logger.info("Tool call: %s -> %s", call["args"], result)
            messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))

    data_query = QueryPlan(filters=filters)
    logger.info("Data query: %s", [f.model_dump() for f in data_query.filters])

    return {"data_query": data_query}
