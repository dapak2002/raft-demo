"""Per-record extraction node, fanned out from fetch via LangGraph Send."""

import logging

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from langgraph.runtime import Runtime

from agent.fault_tolerance import is_transient_error, log_node_attempt
from agent.llm import get_llm
from agent.llm_limits import parse_windows
from agent.schema import Order, ParseExtraction, parse_prompt
from agent.services.schema_drift import log_parse_drift
from agent.state import ParseRecordState
from config import PARSE_CHUNK_OVERLAP

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
        _chain = PARSE_PROMPT | get_llm().with_structured_output(ParseExtraction)
    return _chain


def _merge_partials(
    partials: list[ParseExtraction | Order],
) -> tuple[Order | None, dict[str, str]]:
    merged: dict = {}
    extras: dict[str, str] = {}

    for partial in partials:
        merged.update(
            partial.model_dump(exclude_none=True, exclude={"additional_fields"})
        )
        extras.update(getattr(partial, "additional_fields", None) or {})

    if not merged:
        return None, extras

    return Order.model_validate(merged), extras


async def _parse_text(
    text: str, chain: Runnable
) -> tuple[Order | None, dict[str, str]]:
    partials: list[ParseExtraction | Order] = []

    for window in parse_windows(text, PARSE_CHUNK_OVERLAP):
        try:
            partial = await chain.ainvoke({"text": window})
        except Exception as exc:
            if is_transient_error(exc):
                raise
            logger.warning("Parse window failed: %s", exc)
            continue
        if partial is None:
            logger.warning("Parse window returned no structured output")
            continue
        partials.append(partial)

    order, extras = _merge_partials(partials)
    if order is None or not order.populated_fields():
        logger.warning("No fields extracted from record")
        return None, extras

    return order, extras


async def parse_record_node(
    state: ParseRecordState,
    runtime: Runtime,
) -> dict[str, list[Order]]:
    """Parse a single raw order record (one Send task)."""
    log_node_attempt("parse_record", runtime)
    text = state["text"].strip()
    if not text:
        return {"parsed_orders": []}

    order, extras = await _parse_text(text, _get_chain())
    if order is None:
        log_parse_drift(extras)
        return {"parsed_orders": []}

    log_parse_drift(extras, order_id=order.orderId)
    logger.info(
        "Parsed record %s with fields: %s",
        order.sort_key(),
        order.populated_fields(),
    )
    return {"parsed_orders": [order]}
