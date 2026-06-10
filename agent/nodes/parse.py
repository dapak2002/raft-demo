import logging

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from agent.llm import get_llm
from agent.state import AgentState, Order
from config import PARSE_CHUNK_OVERLAP, PARSE_MAX_CHARS

logger = logging.getLogger(__name__)

PARSE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Extract order fields from this text excerpt. "
            "The excerpt may be partial — only set fields that appear here.\n\n"
            "Fields: orderID, buyer, state (2-letter code), total (number, no $).",
        ),
        ("human", "{text}"),
    ]
)


class PartialOrder(BaseModel):
    orderID: str | None = None
    buyer: str | None = None
    state: str | None = None
    total: float | None = None


def _windows(text: str) -> list[str]:
    if len(text) <= PARSE_MAX_CHARS:
        return [text]

    step = max(1, PARSE_MAX_CHARS - PARSE_CHUNK_OVERLAP)
    return [text[i : i + PARSE_MAX_CHARS] for i in range(0, len(text), step)]


def parse_node(state: AgentState) -> AgentState:
    raw_orders = state.get("raw_orders") or []
    logger.info("Parsing %d raw orders", len(raw_orders))

    if not raw_orders:
        return {"orders": []}

    chain = PARSE_PROMPT | get_llm().with_structured_output(PartialOrder)
    orders: list[Order] = []

    for text in raw_orders:
        text = text.strip()
        if not text:
            continue

        fields: dict[str, str | float] = {}
        for window in _windows(text):
            try:
                partial = chain.invoke({"text": window})
                fields.update(partial.model_dump(exclude_none=True))
            except Exception as exc:
                logger.warning("Parse window failed: %s", exc)

        if all(k in fields for k in ("orderID", "buyer", "state", "total")):
            orders.append(Order(**fields))
            logger.info("Parsed order %s", fields["orderID"])
        else:
            logger.warning("Incomplete order: %s", fields)

    logger.info("Parsed %d/%d orders", len(orders), len(raw_orders))
    return {"orders": orders}
