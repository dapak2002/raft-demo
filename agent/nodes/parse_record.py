"""Per-record extraction node, fanned out from fetch via LangGraph Send."""

import logging

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from langgraph.runtime import Runtime

from agent.fault_tolerance import is_transient_error, log_node_attempt
from agent.llm import get_llm
from agent.llm_limits import parse_windows
from agent.schema import Order, ParseExtraction, parse_prompt
from agent.services.parse_grounding import (
    GroundingResult,
    apply_grounding,
    format_hallucination_feedback,
    log_parse_hallucination,
)
from agent.services.schema_drift import log_parse_drift
from agent.state import ParseRecordState
from config import PARSE_CHUNK_OVERLAP, PARSE_HALLUCINATION_MAX_RETRIES

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

_RETRY_PREFIX = (
    "IMPORTANT: A prior parse included values not found in the source text: "
    "{feedback}. Only extract values that explicitly appear in the excerpt below.\n\n"
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


def _window_text(window: str, feedback: str | None) -> str:
    if not feedback:
        return window
    return _RETRY_PREFIX.format(feedback=feedback) + window


async def _invoke_parse_windows(
    text: str,
    chain: Runnable,
    *,
    feedback: str | None = None,
) -> list[ParseExtraction | Order]:
    partials: list[ParseExtraction | Order] = []

    for window in parse_windows(text, PARSE_CHUNK_OVERLAP):
        try:
            partial = await chain.ainvoke({"text": _window_text(window, feedback)})
        except Exception as exc:
            if is_transient_error(exc):
                raise
            logger.warning("Parse window failed: %s", exc)
            continue
        if partial is None:
            logger.warning("Parse window returned no structured output")
            continue
        partials.append(partial)

    return partials


async def _parse_text(
    text: str, chain: Runnable
) -> tuple[Order | None, dict[str, str]]:
    feedback: str | None = None
    last_grounding: GroundingResult | None = None

    for attempt in range(1, PARSE_HALLUCINATION_MAX_RETRIES + 1):
        partials = await _invoke_parse_windows(text, chain, feedback=feedback)
        order, extras = _merge_partials(partials)
        if order is None or not order.populated_fields():
            logger.warning("No fields extracted from record (attempt %d)", attempt)
            return None, extras

        grounding = apply_grounding(order, text)
        last_grounding = grounding
        log_parse_hallucination(
            grounding,
            attempt=attempt,
            max_attempts=PARSE_HALLUCINATION_MAX_RETRIES,
        )

        if not grounding.had_hallucination:
            return grounding.order, extras

        if attempt < PARSE_HALLUCINATION_MAX_RETRIES:
            feedback = format_hallucination_feedback(grounding)
            logger.info(
                "Retrying parse after hallucination (attempt %d/%d)",
                attempt + 1,
                PARSE_HALLUCINATION_MAX_RETRIES,
            )
            continue

        if not grounding.order.populated_fields():
            logger.warning("No grounded fields remained after parse retries")
            return None, extras

        logger.warning(
            "Using grounded parse after %d attempts with dropped hallucinations",
            PARSE_HALLUCINATION_MAX_RETRIES,
        )
        return grounding.order, extras

    if last_grounding and last_grounding.order.populated_fields():
        return last_grounding.order, {}
    return None, {}


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
