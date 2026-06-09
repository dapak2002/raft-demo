import logging

from langchain_core.prompts import ChatPromptTemplate

from agent.llm import get_llm
from agent.state import AgentState, Order

logger = logging.getLogger(__name__)

PARSE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Extract structured fields from unstructured order text.\n\n"
            "Return:\n"
            "- orderID: the order identifier\n"
            "- buyer: the buyer name\n"
            "- state: 2-letter US state code from the location\n"
            "- total: order total as a number (no currency symbol)\n\n"
            "Only use information explicitly present in the text.",
        ),
        ("human", "{text}"),
    ]
)


def parse_node(state: AgentState) -> AgentState:
    raw_orders = state.get("raw_orders") or []
    logger.info("Parsing %d raw orders", len(raw_orders))

    if not raw_orders:
        return {"orders": []}

    chain = PARSE_PROMPT | get_llm().with_structured_output(Order)
    orders: list[Order] = []

    for text in raw_orders:
        try:
            order = chain.invoke({"text": text})
            orders.append(order)
            logger.info("Parsed order %s", order.orderID)
        except Exception as exc:
            logger.warning("Failed to parse order: %s", exc)

    logger.info("Parsed %d/%d orders", len(orders), len(raw_orders))
    return {"orders": orders}
