import logging
import re
from typing import Any

from agent.schema import Record
from agent.state import AgentState

logger = logging.getLogger(__name__)

_JSON_TYPES = (str, int, float, bool)


def _value_in_source(value: Any, source: str) -> bool:
    if value is None or value == "" or value == []:
        return True
    if isinstance(value, bool):
        return str(value).lower() in source.lower()
    if isinstance(value, (int, float)):
        num = f"{float(value):.2f}".rstrip("0").rstrip(".")
        return bool(re.search(rf"\$?\s*{re.escape(num)}", source, re.IGNORECASE))
    if isinstance(value, list):
        return all(_value_in_source(item, source) for item in value)
    return str(value).lower() in source.lower()


def _to_json_value(value: Any) -> Any | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else round(value, 2)
    if isinstance(value, list):
        items = [str(item).strip() for item in value if item is not None and str(item).strip()]
        return items or None
    if isinstance(value, str):
        return value.strip() or None
    return None


def _format_record(record: Record) -> dict[str, Any] | None:
    source = record.raw_text
    output: dict[str, Any] = {}

    for key, value in record.fields.items():
        clean_key = Record.normalize_key(key)
        if not clean_key:
            continue

        formatted = _to_json_value(value)
        if formatted is None or not _value_in_source(formatted, source):
            return None

        if not isinstance(formatted, (*_JSON_TYPES, list)):
            return None
        if isinstance(formatted, list) and not all(isinstance(item, str) for item in formatted):
            return None

        output[clean_key] = formatted

    return output or None


def validate_node(state: AgentState) -> dict[str, Any]:
    records = state["matched"]
    logger.info("Node: validate")

    orders: list[dict[str, Any]] = []
    for record in records:
        for key, value in record.fields.items():
            if not _value_in_source(value, record.raw_text):
                logger.warning("Rejected record %s: field %r not in source", record.identifier(), key)
                break
        else:
            if payload := _format_record(record):
                orders.append(payload)

    logger.info("Validated %d/%d records", len(orders), len(records))
    return {"result": {"orders": orders}}
