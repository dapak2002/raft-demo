import logging
import re
from typing import Any

from agent.schema import CANONICAL_FIELDS, Order

JsonValue = str | int | float | bool | list[str]

logger = logging.getLogger(__name__)

VALID_US_STATES = frozenset({
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
})

_STATE_NAMES: dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}

_STATE_ALIASES: dict[str, str] = {
    "ala": "AL", "alaska": "AK", "ariz": "AZ", "arizona": "AZ", "ark": "AR",
    "cal": "CA", "calif": "CA", "california": "CA", "colo": "CO", "colorado": "CO",
    "conn": "CT", "connecticut": "CT", "del": "DE", "delaware": "DE", "fla": "FL",
    "florida": "FL", "ga": "GA", "georgia": "GA", "hawaii": "HI", "ida": "ID",
    "idaho": "ID", "ill": "IL", "illinois": "IL", "ind": "IN", "indiana": "IN",
    "iowa": "IA", "kan": "KS", "kans": "KS", "kansas": "KS", "ken": "KY",
    "kentucky": "KY", "la": "LA", "louisiana": "LA", "maine": "ME", "md": "MD",
    "maryland": "MD", "mass": "MA", "massachusetts": "MA", "mich": "MI",
    "michigan": "MI", "minn": "MN", "minnesota": "MN", "miss": "MS",
    "mississippi": "MS", "mo": "MO", "missouri": "MO", "mont": "MT",
    "montana": "MT", "neb": "NE", "nebr": "NE", "nebraska": "NE", "nev": "NV",
    "nevada": "NV", "nh": "NH", "new hampshire": "NH", "nj": "NJ",
    "new jersey": "NJ", "nm": "NM", "new mexico": "NM", "ny": "NY",
    "new york": "NY", "nc": "NC", "north carolina": "NC", "nd": "ND",
    "north dakota": "ND", "oh": "OH", "ohio": "OH", "ok": "OK", "okla": "OK",
    "oklahoma": "OK", "ore": "OR", "oregon": "OR", "pa": "PA",
    "penn": "PA", "pennsylvania": "PA", "ri": "RI", "rhode island": "RI",
    "sc": "SC", "south carolina": "SC", "sd": "SD", "south dakota": "SD",
    "tenn": "TN", "tennessee": "TN", "tex": "TX", "texas": "TX", "ut": "UT",
    "utah": "UT", "vt": "VT", "vermont": "VT", "va": "VA", "virginia": "VA",
    "wash": "WA", "washington": "WA", "w va": "WV", "west virginia": "WV",
    "wis": "WI", "wisc": "WI", "wisconsin": "WI", "wyo": "WY", "wyoming": "WY",
    "dc": "DC", "district of columbia": "DC",
}

_TOTAL_ALIASES = frozenset({
    "total",
    "ordertotal",
    "order_total",
    "grandtotal",
    "grand_total",
    "subtotal",
    "invoiceamt",
    "invoice_amt",
    "amount",
    "amountpaid",
    "amount_paid",
    "paymenttotal",
    "payment_total",
    "value",
    "price",
    "charge",
    "amt",
    "tot",
})

_CANONICAL_LOWER = {name.lower() for name in CANONICAL_FIELDS}

for code, name in _STATE_NAMES.items():
    _STATE_ALIASES.setdefault(code.lower(), code)
    _STATE_ALIASES.setdefault(name.lower(), code)


def log_schema_drift(
    field: str,
    value: Any,
    *,
    order_id: str | None = None,
    raw_text: str | None = None,
) -> None:
    preview = str(raw_text)[:120] + "..." if raw_text and len(raw_text) > 120 else raw_text
    logger.warning(
        "Schema drift: orderId=%s field=%r value=%r source=%r",
        order_id or "unknown",
        field,
        value,
        preview,
    )


def _clean_token(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower().rstrip("."))


def _normalize_field_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.lower())


def _is_total_alias(key: str) -> bool:
    return _normalize_field_key(key) in _TOTAL_ALIASES


def normalize_state(value: str) -> str | None:
    if not value or not str(value).strip():
        return None

    token = _clean_token(str(value))
    upper = token.upper()
    if upper in VALID_US_STATES:
        return upper

    if code := _STATE_ALIASES.get(token):
        return code

    compact = re.sub(r"[^a-z]", "", token)
    if code := _STATE_ALIASES.get(compact):
        return code

    return None


def state_in_source(code: str, source: str) -> bool:
    normalized = code.strip().upper()
    if normalized not in VALID_US_STATES:
        return False

    if re.search(rf"\b{re.escape(normalized)}\b", source, re.IGNORECASE):
        return True

    name = _STATE_NAMES.get(normalized, "")
    if name and re.search(rf"\b{re.escape(name)}\b", source, re.IGNORECASE):
        return True

    return False


def _state_from_segment(segment: str) -> str | None:
    if "," in segment:
        tail = segment.rsplit(",", 1)[-1].strip()
        if code := normalize_state(tail):
            return code

    if code := normalize_state(segment):
        return code

    for match in re.finditer(r"\b([A-Z]{2})\b", segment):
        if code := normalize_state(match.group(1)):
            return code

    return None


def extract_state_from_text(text: str) -> str | None:
    if not text or not str(text).strip():
        return None

    raw = str(text).strip()

    location_pattern = re.compile(
        r"(?:location|state|ship[\s-]?to|addr(?:ess)?|delivery|destination)"
        r"[\s=:|-]+([^|\n;]+)",
        re.IGNORECASE,
    )
    for match in location_pattern.finditer(raw):
        if code := _state_from_segment(match.group(1)):
            return code

    for match in re.finditer(r",\s*([A-Za-z]{2,})\b", raw):
        if code := normalize_state(match.group(1)):
            return code

    lower = raw.lower()
    for alias in sorted(_STATE_ALIASES, key=len, reverse=True):
        if len(alias) < 3 and " " not in alias:
            continue
        if re.search(rf"\b{re.escape(alias)}\b", lower):
            return _STATE_ALIASES[alias]

    for match in re.finditer(r"\b([A-Z]{2})\b", raw):
        if code := normalize_state(match.group(1)):
            return code

    return None


def _coerce_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        numeric = re.sub(r"[$,\s]", "", value.strip())
        if numeric and re.fullmatch(r"-?\d+(\.\d+)?", numeric):
            return float(numeric)
    return None


def _normalize_items(value: Any) -> list[str]:
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _extract_total(fields: dict[str, JsonValue]) -> float | None:
    total = _coerce_number(fields.get("total"))
    if total is not None:
        return total

    for key, value in fields.items():
        if key == "total":
            continue
        if _is_total_alias(key):
            if amount := _coerce_number(value):
                return amount
    return None


def order_data_score(order: Order) -> int:
    """Higher score means more populated canonical fields."""
    score = 0
    for name in CANONICAL_FIELDS:
        value = getattr(order, name)
        if value is None:
            continue
        if name == "items":
            score += 1 + len(value)
        else:
            score += 1
    return score


def normalize_order(fields: dict[str, JsonValue], raw_text: str) -> Order | None:
    """Map parsed fields to the fixed schema; log drift for anything else."""
    order_id = fields.get("orderId")
    order_id_str = str(order_id).strip() if order_id is not None else None

    canonical_lower = _CANONICAL_LOWER
    for key, value in fields.items():
        name = key.strip()
        if not name:
            continue
        lower = name.lower()
        if lower in canonical_lower or _is_total_alias(name):
            continue
        log_schema_drift(name, value, order_id=order_id_str, raw_text=raw_text)

    data: dict[str, str | float | list[str]] = {}

    for name in ("orderId", "buyer", "city"):
        value = fields.get(name)
        if value is not None and str(value).strip():
            data[name] = str(value).strip()

    state_value = fields.get("state")
    state_code: str | None = None
    if isinstance(state_value, str) and state_value.strip():
        state_code = normalize_state(state_value)
        if state_code and not state_in_source(state_code, raw_text):
            state_code = None

    if state_code is None:
        state_code = extract_state_from_text(raw_text)

    if state_code and state_in_source(state_code, raw_text):
        data["state"] = state_code

    items = _normalize_items(fields.get("items"))
    if items:
        data["items"] = items

    if total := _extract_total(fields):
        data["total"] = total

    if not data:
        return None

    return Order(**data)
