import logging
import re
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from agent.schema import Record, RecordExtract
from agent.state import AgentState
from config import MODEL, OPENROUTER_API_KEY, OPENROUTER_BASE_URL, PARSE_CHUNK_SIZE

logger = logging.getLogger(__name__)

PARSE_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "Extract all fields from unstructured order text. "
     "Discover keys from labels in the text. Use snake_case keys and infer types. "
     "Field count and shape may vary — extract whatever is present. "
     "Only use information explicitly in the text. Do not invent values."),
    ("human", "{text}"),
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


def _coerce_fields(fields: dict[str, Any]) -> dict[str, Any]:
    coerced: dict[str, Any] = {}
    for key, value in fields.items():
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.lower() in {"true", "false"}:
                coerced[key] = stripped.lower() == "true"
                continue
            numeric = re.sub(r"[$,\s]", "", stripped)
            if numeric and re.fullmatch(r"-?\d+(\.\d+)?", numeric):
                coerced[key] = float(numeric) if "." in numeric else int(numeric)
                continue
        coerced[key] = value
    return coerced


def _parse_one(text: str, llm) -> Record | None:
    try:
        extracted: RecordExtract = (PARSE_PROMPT | llm).invoke({"text": text})
        fields = _coerce_fields(extracted.fields)
        if not fields:
            logger.warning("No fields extracted from record")
            return None
        return Record(fields=fields, raw_text=text)
    except Exception as exc:
        logger.warning("Parse failed: %s", exc)
        return None


def parse_node(state: AgentState) -> dict[str, Any]:
    raw_orders = state["raw_orders"]
    logger.info("Node: parse")

    if not raw_orders:
        return {"records": []}

    llm = _build_llm().with_structured_output(RecordExtract)
    parsed: list[Record] = []

    for i in range(0, len(raw_orders), PARSE_CHUNK_SIZE):
        chunk = raw_orders[i : i + PARSE_CHUNK_SIZE]
        logger.info("Parsing records %d-%d of %d", i + 1, i + len(chunk), len(raw_orders))
        for text in chunk:
            if record := _parse_one(text, llm):
                parsed.append(record)

    logger.info("Parsed %d/%d records", len(parsed), len(raw_orders))
    return {"records": parsed}
