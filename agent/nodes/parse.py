"""Per-record extraction node, fanned out from fetch via LangGraph Send."""

import logging

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from agent.llm import get_llm
from agent.schema import Order, parse_prompt
from agent.services.field_normalize import JsonValue
from agent.services.field_normalize import normalize_order
from agent.services.parse_grounding import is_grounded
from agent.state import ParseRecordState
from config import PARSE_CHUNK_OVERLAP, PARSE_MAX_CHARS

logger = logging.getLogger(__name__)

PARSE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Extract structured order data from the provided text excerpt. "
            "The excerpt may be partial — only set fields visible in this chunk.\n\n"
            f"{parse_prompt()}",
        ),
        ("human", "{text}"),
    ]
)

_chain: Runnable | None = None


def _get_chain() -> Runnable:
    global _chain
    if _chain is None:
        _chain = PARSE_PROMPT | get_llm().with_structured_output(Order)
    return _chain


def _windows(text: str) -> list[str]:
    if len(text) <= PARSE_MAX_CHARS:
        return [text]

    step = max(1, PARSE_MAX_CHARS - PARSE_CHUNK_OVERLAP)
    return [text[i : i + PARSE_MAX_CHARS] for i in range(0, len(text), step)]


def _parse_text(text: str, chain: Runnable) -> Order | None:
    fields: dict[str, JsonValue] = {}

    for window in _windows(text):
        try:
            partial: Order = chain.invoke({"text": window})
            for key, value in partial.model_dump(exclude_none=True).items():
                fields[key] = value
        except Exception as exc:
            logger.warning("Parse window failed: %s", exc)

    if not fields:
        logger.warning("No fields extracted from record")
        return None

    order = normalize_order(fields, text)
    if order is None:
        logger.warning("No fields after normalization: %s", fields)
        return None

    if not is_grounded(order, text):
        logger.warning("Ungrounded record rejected: %s", order.to_json())
        return None

    return order


def parse_record_node(state: ParseRecordState) -> dict[str, list[Order]]:
    """Parse a single raw order record (one Send task)."""
    text = state["text"].strip()
    if not text:
        return {"parsed_orders": []}

    order = _parse_text(text, _get_chain())
    if order is None:
        return {"parsed_orders": []}

    logger.info(
        "Parsed record %s with fields: %s",
        order.sort_key(),
        order.populated_fields(),
    )
    return {"parsed_orders": [order]}
