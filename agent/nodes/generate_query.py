import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from agent.schema import QueryPlan
from agent.state import AgentState
from config import MODEL, OPENROUTER_API_KEY, OPENROUTER_BASE_URL

logger = logging.getLogger(__name__)

QUERY_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "Convert the user's order query into filters.\n\n"
     "Fields and sample values from the parsed data:\n{field_samples}\n\n"
     "Each filter has field, operator, and values (a list).\n"
     "A record matches a filter if ANY value in the list satisfies the operator.\n"
     "The field MUST be one of the field names above.\n\n"
     "Expand conceptual terms into concrete values that can appear in the data:\n"
     "- Categories (e.g. 'peripherals') → specific item names like mouse, monitor, headphones\n"
     "- Regions (e.g. 'midwest') → state codes or names that appear in location (OH, IL, IN, ...)\n"
     "- Use sample values to pick realistic terms. Prefer contains for partial text matches.\n"
     "Return an empty list if no filters apply."),
    ("human", "{query}"),
])


def _build_llm() -> ChatOpenAI:
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set. Add it to .env")
    return ChatOpenAI(
        model=MODEL,
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        temperature=0,
    )


def generate_query_node(state: AgentState) -> dict[str, Any]:
    field_samples = state["field_samples"]
    logger.info("Node: generate_query")

    if not field_samples:
        logger.warning("No field samples — returning empty query plan")
        return {"plan": QueryPlan()}

    chain = QUERY_PROMPT | _build_llm().with_structured_output(QueryPlan)
    plan = chain.invoke({"query": state["query"], "field_samples": field_samples})
    logger.info("Query plan: %s", [f.model_dump() for f in plan.filters])
    return {"plan": plan}
