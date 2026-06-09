import logging

from langchain_core.prompts import ChatPromptTemplate

from agent.llm import get_llm
from agent.state import AgentState, QueryPlan

logger = logging.getLogger(__name__)

QUERY_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Convert the user's request into filters over order data.\n\n"
            "For each condition in the request, choose:\n"
            "- field: one of orderID, buyer, state, total\n"
            "- operator: one of equals, contains, over, under, at_least, at_most, not\n"
            "- value: the concrete value to compare against\n\n"
            "Field guide:\n"
            "- orderID: order identifier\n"
            "- buyer: buyer name (use contains for partial names)\n"
            "- state: 2-letter US state code\n"
            "- total: numeric order total\n\n"
            "Operator guide:\n"
            "- equals / not: exact match\n"
            "- contains: substring match\n"
            "- over / under / at_least / at_most: numeric comparisons on total\n\n"
            "Expand conceptual terms (e.g. 'midwest' → OH, 'more than 500' → over 500).\n"
            "Return an empty filter list if no filters apply.",
        ),
        ("human", "{user_query}"),
    ]
)


def generate_data_query_node(state: AgentState) -> AgentState:
    logger.info("Generating data query for: %s", state["user_query"])

    chain = QUERY_PROMPT | get_llm().with_structured_output(QueryPlan)
    data_query = chain.invoke({"user_query": state["user_query"]})
    logger.info("Data query: %s", [f.model_dump() for f in data_query.filters])

    return {"data_query": data_query}
