import re
from typing import Any

from agent.schema import Order
from agent.services.field_normalize import state_in_source

_DOLLAR_RE = re.compile(r"\$[\d,]+\.?\d*")


def is_grounded(order: Order, raw_text: str) -> bool:
    """Return True when every extracted field is supported by the source text."""
    text = raw_text.strip()
    fields = order.to_json()
    if not text or not fields:
        return False

    return all(_field_grounded(field, value, text) for field, value in fields.items())


def _field_grounded(field: str, value: Any, text: str) -> bool:
    # State codes are normalized (Texas -> TX), so match against either form.
    if field == "state" and isinstance(value, str):
        return state_in_source(value, text)

    return _value_grounded(value, text)


def _value_grounded(value: Any, text: str) -> bool:
    if isinstance(value, list):
        return bool(value) and all(_value_grounded(item, text) for item in value)

    if isinstance(value, bool):
        return str(value).lower() in text.lower()

    if isinstance(value, (int, float)):
        return _number_in_text(float(value), text)

    stripped = str(value).strip()
    if not stripped:
        return False

    lower_text = text.lower()
    if stripped.lower() in lower_text:
        return True

    # Values like buyer names may be assembled from labeled parts
    # (e.g. "buyer_first=Alex buyer_last=Kim" -> "Alex Kim"), so accept
    # the value when every token appears somewhere in the source.
    tokens = stripped.lower().split()
    return len(tokens) > 1 and all(token in lower_text for token in tokens)


def _number_in_text(total: float, text: str) -> bool:
    for match in _DOLLAR_RE.finditer(text):
        amount_str = match.group()[1:].replace(",", "")
        try:
            amount = float(amount_str)
        except ValueError:
            continue
        if abs(amount - total) < 0.02:
            return True

    candidates = [f"{total:.2f}", f"{total:g}"]
    if total == int(total):
        candidates.append(str(int(total)))

    return any(candidate in text for candidate in candidates)
