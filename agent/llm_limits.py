"""Shared bounds for LLM prompts — truncation and window caps."""

import logging

from config import (
    PARSE_MAX_CHARS,
    PARSE_MAX_WINDOWS,
    PLAN_FEEDBACK_MAX_CHARS,
    PLAN_MAX_TOOL_TURNS,
    REVIEW_PLAN_MAX_JSON_CHARS,
    USER_QUERY_MAX_CHARS,
)

logger = logging.getLogger(__name__)


def truncate_text(text: str, max_chars: int, *, label: str) -> str:
    if len(text) <= max_chars:
        return text
    logger.warning(
        "Truncating %s from %d to %d characters",
        label,
        len(text),
        max_chars,
    )
    return text[:max_chars]


def prepare_user_query(user_query: str) -> str:
    return truncate_text(user_query.strip(), USER_QUERY_MAX_CHARS, label="user_query")


def parse_windows(text: str, overlap: int) -> list[str]:
    """Split order text into overlapping windows, capped at PARSE_MAX_WINDOWS."""
    if len(text) <= PARSE_MAX_CHARS:
        return [text]

    step = max(1, PARSE_MAX_CHARS - overlap)
    windows = [text[i : i + PARSE_MAX_CHARS] for i in range(0, len(text), step)]
    if len(windows) > PARSE_MAX_WINDOWS:
        logger.warning(
            "Record needs %d parse windows; using first %d (%d chars each)",
            len(windows),
            PARSE_MAX_WINDOWS,
            PARSE_MAX_CHARS,
        )
        windows = windows[:PARSE_MAX_WINDOWS]
    return windows


def prepare_plan_feedback(feedback: str) -> str:
    return truncate_text(
        feedback.strip(), PLAN_FEEDBACK_MAX_CHARS, label="plan_feedback"
    )


def prepare_plan_json(plan_json: str) -> str:
    return truncate_text(plan_json, REVIEW_PLAN_MAX_JSON_CHARS, label="plan_json")


def plan_tool_turn_limit() -> int:
    return PLAN_MAX_TOOL_TURNS
